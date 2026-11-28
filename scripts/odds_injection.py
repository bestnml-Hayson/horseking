#!/usr/bin/env python3
"""
scripts/odds_injection.py
Stage 2: Race-Day Odds Injection

Scrapes live odds from bet.hkjc.com and computes:
  1. P_market = (1/odds)^GAMMA normalised (takeout + favourite/longshot bias removed)
  2. P_final = MODEL_WEIGHT * P_model + MARKET_WEIGHT * P_market (see model_config.py)
  3. EV = P_final * odds - 1
  4. Kelly = max(0, EV/(odds-1)) * 0.25

CLI:
  python scripts/odds_injection.py --date 2026-10-04 --venue ST
  python scripts/odds_injection.py --date 2026-10-04 --venue ST --race 1,2,3
"""
import os
import sys
import argparse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

HKT = ZoneInfo('Asia/Hong_Kong')

sys.path.insert(0, os.path.dirname(__file__))
from common import get_supabase, retry_supabase
from model_config import market_probabilities, fuse_race

DRIFT_ID = 'odds_drift'
DRIFT_MAX_POINTS = 24
DRIFT_KEEP_DAYS = 3


def _load_drift(supabase) -> dict:
    try:
        resp = retry_supabase(
            lambda: supabase.table('pipeline_status').select('status_json').eq('id', DRIFT_ID).execute()
        )
        rows = resp.data or []
        return (rows[0].get('status_json') or {}) if rows else {}
    except Exception as e:
        print(f"    [WARN] drift state unreadable: {e}")
        return {}


def record_drift(supabase, race_id: str, race_date: str, runners: list):
    """Append this tick's prices to the drift series (opening price + latest + path).

    Stored in pipeline_status.odds_drift rather than a table of its own: this
    instance has no DDL path, and the payload is a few KB per meeting. The
    frontend reads it through /api/odds-drift.
    """
    priced = [r for r in runners if r.get('win_odds') and r['win_odds'] > 1.0]
    if not priced:
        return

    now = datetime.now(HKT)
    now_iso = now.isoformat()
    ts = int(now.timestamp())
    state = _load_drift(supabase)
    races = state.get('races') or {}
    entry = races.get(race_id) or {'race_date': race_date, 'runners': {}}
    entry['race_date'] = race_date
    bag = entry.setdefault('runners', {})

    for runner in priced:
        odds = float(runner['win_odds'])
        rid = runner['runner_id']
        current = bag.get(rid)
        if not current:
            bag[rid] = {'open': odds, 'open_at': now_iso, 'last': odds, 'last_at': now_iso,
                        'points': [[ts, odds]]}
            continue
        current['last'] = odds
        current['last_at'] = now_iso
        points = current.get('points') or []
        if not points or points[-1][1] != odds:
            points.append([ts, odds])
            current['points'] = points[-DRIFT_MAX_POINTS:]

    races[race_id] = entry
    cutoff = (now - timedelta(days=DRIFT_KEEP_DAYS)).strftime('%Y-%m-%d')
    races = {rid: v for rid, v in races.items() if str(v.get('race_date', ''))[:10] >= cutoff}

    retry_supabase(lambda: supabase.table('pipeline_status').upsert({
        'id': DRIFT_ID,
        'last_run': now_iso,
        'status_json': {'races': races, 'updated_at': now_iso},
    }, on_conflict='id').execute())
    print(f"    [Drift] {len(priced)} price points recorded")


def scrape_odds_for_race(page, date_str: str, venue: str, race_no: int) -> dict:
    """Scrape win odds for a single race from bet.hkjc.com"""
    odds_url = f"https://bet.hkjc.com/ch/racing/wp/{date_str}/{venue}/{race_no}"

    try:
        page.goto(odds_url, wait_until='domcontentloaded', timeout=20000)
        try:
            page.wait_for_selector('.rc-odds-row', timeout=8000)
        except Exception:
            page.wait_for_timeout(5000)

        odds_map = page.evaluate('''() => {
            const map = {};
            const rows = document.querySelectorAll('.rc-odds-row');
            rows.forEach(row => {
                const cells = row.querySelectorAll('td');
                if (cells.length >= 8) {
                    const horseNo = parseInt(cells[0].textContent.trim());
                    const winOdds = parseFloat(cells[7].textContent.trim()) || 0;
                    if (!isNaN(horseNo) && horseNo > 0 && winOdds > 1.0) {
                        map[horseNo] = winOdds;
                    }
                }
            });
            return map;
        }''')

        return {int(k): float(v) for k, v in odds_map.items() if v and v > 1.0}
    except Exception as e:
        print(f"    [FAIL] R{race_no} odds scrape: {e}")
        return {}


def compute_market_fusion(odds_list: list, p_models: list) -> list:
    """
    Compute P_market, P_final, EV, Kelly for each horse.
    P_market strips the takeout (model_config.MARKET_GAMMA); fusion weights live there too.
    """
    if not any(o and o > 1.0 for o in odds_list):
        return [{'p_market': None, 'p_final': None, 'ev': None, 'kelly': None} for _ in odds_list]

    p_markets = market_probabilities(odds_list)
    masked = [p_markets[i] if (odds_list[i] and odds_list[i] > 1.0) else None
              for i in range(len(odds_list))]
    p_finals = fuse_race(p_models, masked, odds_list)

    results = []
    for i, odds in enumerate(odds_list):
        if odds and odds > 1.0:
            p_market = p_markets[i]
            p_final = p_finals[i]
            ev = p_final * odds - 1
            kelly = max(0, ev / (odds - 1)) * 0.25
        else:
            p_market = None
            p_final = None
            ev = None
            kelly = None

        results.append({
            'p_market': round(p_market, 5) if p_market else None,
            'p_final': round(p_final, 5) if p_final else None,
            'ev': round(ev, 5) if ev is not None else None,
            'kelly': round(kelly, 5) if kelly is not None else None,
        })

    return results


def inject_odds(supabase, date_str: str, venue: str, race_nos: list = None):
    """Main odds injection pipeline"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[FAIL] playwright not installed. Run: pip install playwright && playwright install chromium")
        sys.exit(1)

    date_path = date_str.replace('-', '')

    # Fetch races for this date/venue
    query = supabase.table('races').select('race_id,race_no').eq('race_date', date_str).eq('venue', venue)
    resp = query.execute()
    races = resp.data or []

    if not races:
        print(f"[FAIL] No races found for {date_str} {venue}")
        return

    # Filter by race numbers if specified
    if race_nos:
        races = [r for r in races if r['race_no'] in race_nos]

    print(f"=" * 60)
    print(f"Odds Injection - {date_str} {venue}")
    print(f"Races: {len(races)}")
    print(f"=" * 60)

    total_updated = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-gpu'])
        page = browser.new_page()

        for race in races:
            race_id = race['race_id']
            race_no = race['race_no']

            print(f"\n  Processing R{race_no} ({race_id})...")

            # Fetch runners with current P_model
            resp = supabase.table('race_runners').select('runner_id,horse_no,win_odds').eq('race_id', race_id).execute()
            runners = resp.data or []

            if not runners:
                print(f"    [WARN] No runners found")
                continue

            # Fetch current predictions (P_model)
            resp = supabase.table('model_predictions').select('runner_id,raw_model_prob').eq('race_id', race_id).execute()
            predictions = {p['runner_id']: p for p in (resp.data or [])}

            # Scrape live odds
            print(f"    Scraping odds...")
            odds_map = scrape_odds_for_race(page, date_str, venue, race_no)

            if not odds_map:
                print(f"    [WARN] No odds scraped, skipping")
                continue

            matched = 0
            for runner in runners:
                horse_no = runner['horse_no']
                if horse_no in odds_map:
                    runner['win_odds'] = odds_map[horse_no]
                    matched += 1

            print(f"    [OK] {matched}/{len(runners)} horses with odds")

            # Compute market fusion
            odds_list = [r.get('win_odds') for r in runners]
            p_models = [predictions.get(r['runner_id'], {}).get('raw_model_prob', 0) for r in runners]

            fusion_results = compute_market_fusion(odds_list, p_models)

            # Update model_predictions
            upsert_rows = []
            for i, runner in enumerate(runners):
                fusion = fusion_results[i]
                if fusion['p_final'] is not None:
                    upsert_rows.append({
                        'race_id': race_id,
                        'runner_id': runner['runner_id'],
                        'market_implied_prob': fusion['p_market'],
                        'final_prob': fusion['p_final'],
                        'expected_value': fusion['ev'],
                        'kelly_fraction': fusion['kelly'],
                    })

            if upsert_rows:
                retry_supabase(lambda: supabase.table('model_predictions').upsert(
                    upsert_rows, on_conflict='race_id,runner_id'
                ).execute())
                print(f"    [OK] Updated {len(upsert_rows)} predictions")
                total_updated += len(upsert_rows)

            # Update win_odds on race_runners
            for runner in runners:
                if runner.get('win_odds') and runner['win_odds'] > 0:
                    retry_supabase(lambda r=runner: supabase.table('race_runners').update(
                        {'win_odds': r['win_odds']}
                    ).eq('runner_id', r['runner_id']).execute())

            # Only this scrape's prices go into the drift series; stale DB values
            # would make a horse look like it never moved.
            record_drift(
                supabase, race_id, date_str,
                [r for r in runners if r['horse_no'] in odds_map],
            )

        browser.close()

    print(f"\n{'=' * 60}")
    print(f"SUMMARY")
    print(f"  Total predictions updated: {total_updated}")
    print(f"{'=' * 60}")


def main():
    parser = argparse.ArgumentParser(description='Race-Day Odds Injection')
    parser.add_argument('--date', help='Race date (YYYY-MM-DD). Defaults to today.')
    parser.add_argument('--venue', choices=['ST', 'HV'], help='Venue code')
    parser.add_argument('--race', help='Comma-separated race numbers (e.g., 1,2,3)')
    args = parser.parse_args()

    today = datetime.now(HKT)
    date_str = args.date or today.strftime('%Y-%m-%d')

    if not args.venue:
        # Auto-detect venue
        weekday = today.weekday()
        if weekday in [2, 5]:  # Wed, Sat
            venue = 'ST'
        elif weekday in [1, 3, 6]:  # Tue, Thu, Sun
            venue = 'HV'
        else:
            print("[FAIL] Cannot auto-detect venue. Specify --venue ST or HV")
            sys.exit(1)
    else:
        venue = args.venue

    race_nos = None
    if args.race:
        race_nos = [int(x) for x in args.race.split(',')]

    supabase = get_supabase()
    if not supabase:
        sys.exit(1)

    inject_odds(supabase, date_str, venue, race_nos)


if __name__ == '__main__':
    main()
