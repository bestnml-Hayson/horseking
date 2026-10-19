#!/usr/bin/env python3
"""
scripts/auto_pilot.py
Auto-Pilot Pipeline: Daily race lifecycle management.

Phase 1 — Auto-Discovery & Stage 1 Pre-Scrape:
  Checks HKJC for upcoming race days (next 7 days).
  For any race day NOT yet in the database, auto-scrapes the full racecard
  and runs Benter P_model (Stage 1: pure ability, no odds).

Phase 1.5 — Live Odds Injection:
  For today's races that have runners but no win_odds yet,
  auto-scrapes live odds from HKJC and injects into race_runners.
  Triggers Benter model fusion (P_final = 50% P_model + 50% P_market).

Phase 2 — Auto-Archive & Post-Race Review:
  Finds races where is_finished=false but race_date < today.
  Scrapes official results from HKJC, updates finish_position/win_odds,
  marks is_finished=true, and triggers AI performance recalculation.

Phase 3 — Status Report:
  Writes pipeline status to Supabase 'pipeline_status' table for frontend display.

Usage:
  python scripts/auto_pilot.py                  # full run (discover + odds + archive)
  python scripts/auto_pilot.py --discover-only  # only auto-discover new race days
  python scripts/auto_pilot.py --odds-only      # only inject live odds for today's races
  python scripts/auto_pilot.py --archive-only   # only archive past races
  python scripts/auto_pilot.py --dry-run        # log what would happen, no writes
"""
import io, sys, os, time, subprocess, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timedelta
from typing import Optional, List, Dict
from zoneinfo import ZoneInfo
from common import get_supabase, retry_supabase

HKT = ZoneInfo('Asia/Hong_Kong')

# Venue priority by weekday (used as hint, not filter — both venues are always checked)
VENUE_WEEKDAYS = {
    'ST': [2, 5],       # Wed, Sat
    'HV': [1, 3, 6],    # Tue, Thu, Sun
}


def now_hkt() -> datetime:
    return datetime.now(HKT)


# =====================================================================
# Phase 1: Auto-Discovery — find upcoming race days from HKJC
# =====================================================================
def discover_upcoming_race_days(lookahead_days: int = 7) -> List[Dict]:
    """
    Check HKJC racecard pages for the next N days to find race days.
    For each date, tries BOTH ST and HV — no weekday filtering.
    Returns list of {'date': 'YYYY-MM-DD', 'venue': 'ST'|'HV'}
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[FAIL] playwright not installed")
        return []

    today = now_hkt()
    date_list = []

    for d in range(0, lookahead_days + 1):
        dt = today + timedelta(days=d)
        date_str = dt.strftime('%Y-%m-%d')
        wd = dt.weekday()

        # Pick primary venue by weekday as a hint, but we'll check both
        primary = 'ST'
        for v, weekdays in VENUE_WEEKDAYS.items():
            if wd in weekdays:
                primary = v
                break
        venues_to_try = [primary, 'HV' if primary == 'ST' else 'ST']

        date_list.append({'date': date_str, 'venues': venues_to_try})

    if not date_list:
        return []

    discovered = []
    total_checks = sum(len(dl['venues']) for dl in date_list)
    print(f"\n[Discover] Checking {len(date_list)} dates × 2 venues ({total_checks} checks) via HKJC...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-gpu'])
        page = browser.new_page()

        for dl in date_list:
            date_str = dl['date']
            date_slash = date_str.replace('-', '/')
            found = False

            for venue in dl['venues']:
                if found:
                    break

                url = f"https://racing.hkjc.com/zh-hk/local/information/racecard?racedate={date_slash}&Racecourse={venue}&RaceNo=1"
                try:
                    page.goto(url, wait_until='domcontentloaded', timeout=20000)
                    page.wait_for_timeout(3000)

                    actual_url = page.url
                    if date_str.replace('-', '/') not in actual_url and date_str not in actual_url:
                        print(f"  {date_str} {venue}: HKJC redirected → no racecard")
                        continue

                    horse_count = page.evaluate('''() => {
                        const tables = document.querySelectorAll('table');
                        for (const t of tables) {
                            const rows = t.querySelectorAll('tr');
                            if (rows.length >= 5) return rows.length - 1;
                        }
                        return 0;
                    }''')

                    if horse_count >= 4:
                        discovered.append({'date': date_str, 'venue': venue})
                        print(f"  {date_str} {venue}: CONFIRMED ({horse_count} horses in R1)")
                        found = True
                    else:
                        print(f"  {date_str} {venue}: no data yet ({horse_count} horses)")

                except Exception as e:
                    print(f"  {date_str} {venue}: error — {e}")

                time.sleep(1)

        browser.close()

    print(f"[Discover] Found {len(discovered)} race days")
    return discovered


def inject_odds_for_upcoming_races(supabase, dry_run: bool = False):
    """
    Phase 1.5: Auto-inject live odds for today's races that don't have odds yet.
    Checks race_runners where win_odds is null and race_date = today.
    """
    today_str = now_hkt().strftime('%Y-%m-%d')

    # Find races today that have runners but no odds
    resp = retry_supabase(
        lambda: supabase.table('races').select('race_id,race_date,venue,race_no').eq('race_date', today_str).eq('is_finished', False).execute()
    )
    today_races = resp.data or []

    if not today_races:
        print(f"\n[Odds Injection] No unfinished races today ({today_str})")
        return 0

    # Check which races already have odds
    race_ids = [r['race_id'] for r in today_races]
    odds_resp = retry_supabase(
        lambda: supabase.table('race_runners').select('race_id,win_odds').in('race_id', race_ids).not_.is_('win_odds', 'null').execute()
    )
    races_with_odds = set(r['race_id'] for r in (odds_resp.data or []))

    races_needing_odds = [r for r in today_races if r['race_id'] not in races_with_odds]

    if not races_needing_odds:
        print(f"\n[Odds Injection] All {len(today_races)} races today already have odds")
        return 0

    print(f"\n[Odds Injection] {len(races_needing_odds)} races need odds injection")

    date_venue_pairs = set((r['race_date'], r['venue']) for r in races_needing_odds)
    injected = 0

    for date_str, venue in sorted(date_venue_pairs):
        print(f"\n  [Odds] {date_str} {venue}: scraping live odds...")
        if dry_run:
            print(f"  [DRY-RUN] Would run: auto_scraper.py --date {date_str} --venue {venue} --odds-only")
            injected += 1
            continue

        try:
            result = subprocess.run(
                [sys.executable, os.path.join(os.path.dirname(__file__), 'auto_scraper.py'),
                 '--date', date_str, '--venue', venue, '--odds-only'],
                capture_output=False,
                timeout=180
            )
            if result.returncode == 0:
                injected += 1
                print(f"  [OK] {date_str} {venue}: odds injected")
            else:
                print(f"  [FAIL] {date_str} {venue}: exit code {result.returncode}")
        except subprocess.TimeoutExpired:
            print(f"  [TIMEOUT] {date_str} {venue}: exceeded 3 min")
        except Exception as e:
            print(f"  [ERROR] {date_str} {venue}: {e}")

        time.sleep(2)

    return injected


def scrape_new_race_days(supabase, race_days: List[Dict], dry_run: bool = False):
    """For each discovered race day, check if already in DB. If not, run auto_scraper."""
    if not race_days:
        return 0

    scraped = 0
    for rd in race_days:
        date_str = rd['date']
        venue = rd['venue']

        existing = retry_supabase(
            lambda: supabase.table('races').select('race_id').eq('race_date', date_str).eq('venue', venue).limit(1).execute()
        )
        if existing.data and len(existing.data) > 0:
            print(f"  {date_str} {venue}: already in DB ({len(existing.data)} races), skipping")
            continue

        print(f"\n  [Auto-Scrape] {date_str} {venue}: NEW race day, scraping racecard...")
        if dry_run:
            print(f"  [DRY-RUN] Would run: auto_scraper.py --date {date_str} --venue {venue} --pre-race")
            scraped += 1
            continue

        try:
            result = subprocess.run(
                [sys.executable, os.path.join(os.path.dirname(__file__), 'auto_scraper.py'),
                 '--date', date_str, '--venue', venue, '--pre-race'],
                capture_output=False,
                timeout=300
            )
            if result.returncode == 0:
                scraped += 1
                print(f"  [OK] {date_str} {venue}: scraped successfully")
            else:
                print(f"  [FAIL] {date_str} {venue}: exit code {result.returncode}")
        except subprocess.TimeoutExpired:
            print(f"  [TIMEOUT] {date_str} {venue}: exceeded 5 min")
        except Exception as e:
            print(f"  [ERROR] {date_str} {venue}: {e}")

        time.sleep(3)

    return scraped


# =====================================================================
# Phase 2: Auto-Archive — scrape results for past unfinished races
# =====================================================================
def find_unfinished_past_races(supabase) -> List[Dict]:
    """Find races where is_finished=false and race_date < today."""
    today_str = now_hkt().strftime('%Y-%m-%d')
    resp = retry_supabase(
        lambda: supabase.table('races').select('race_id,race_date,venue,race_no').eq('is_finished', False).lt('race_date', today_str).execute()
    )
    races = resp.data or []
    print(f"\n[Archive] Found {len(races)} unfinished past races")
    return races


def archive_past_races(supabase, races: List[Dict], dry_run: bool = False):
    """Scrape results for each unfinished past race and update DB."""
    if not races:
        return 0

    date_venue_pairs = set((r['race_date'], r['venue']) for r in races)
    print(f"[Archive] Processing {len(date_venue_pairs)} date/venue pairs...")

    archived = 0
    archived_race_ids = []
    for date_str, venue in sorted(date_venue_pairs):
        date_races = [r for r in races if r['race_date'] == date_str and r['venue'] == venue]
        race_nos = [r['race_no'] for r in date_races]
        print(f"\n  [Archive] {date_str} {venue}: {len(race_nos)} races ({race_nos})")

        if dry_run:
            print(f"  [DRY-RUN] Would run: fix_all_historical_results.py for {date_str} {venue}")
            archived += len(race_nos)
            continue

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-gpu'])
                page = browser.new_page()

                for race in date_races:
                    race_id = race['race_id']
                    race_no = race['race_no']
                    results = scrape_results_for_race(page, date_str, venue, race_no)

                    if not results:
                        print(f"    R{race_no}: no results scraped")
                        continue

                    updated = apply_results(supabase, race_id, results)
                    retry_supabase(
                        lambda rid=race_id: supabase.table('races').update({'is_finished': True}).eq('race_id', rid).execute()
                    )
                    archived += 1
                    archived_race_ids.append(race_id)
                    print(f"    R{race_no}: {updated} runners updated, marked finished")

                    time.sleep(2)

                browser.close()

        except Exception as e:
            print(f"  [ERROR] {date_str} {venue}: {e}")

    if archived_race_ids and not dry_run:
        print(f"\n  [AI Review] Generating reviews for {len(archived_race_ids)} races...")
        ai_reviewed = generate_ai_review(supabase, archived_race_ids)
        print(f"  [AI Review] {ai_reviewed} reviews generated")
    else:
        ai_reviewed = 0

    return archived, ai_reviewed


def scrape_results_for_race(page, date_str: str, venue: str, race_no: int) -> List[Dict]:
    """Scrape official results from HKJC for a single race."""
    date_slash = date_str.replace('-', '/')
    url = f"https://racing.hkjc.com/racing/information/Chinese/Racing/LocalResults.aspx?RaceDate={date_slash}&Racecourse={venue}&RaceNo={race_no}"

    try:
        page.goto(url, wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(4000)

        actual_url = page.url
        date_path = date_str.replace('-', '')
        if date_path not in actual_url and date_slash not in actual_url:
            print(f"    [SKIP] R{race_no}: HKJC redirected (date mismatch)")
            return []

        results = page.evaluate(r'''() => {
            const results = [];
            const tables = document.querySelectorAll('table');
            for (const table of tables) {
                const rows = table.querySelectorAll('tr');
                if (rows.length < 3) continue;
                const headers = Array.from(rows[0].querySelectorAll('td, th')).map(c => c.textContent.trim());
                if (!headers.includes('名次')) continue;

                const colMap = {
                    pos: headers.indexOf('名次'),
                    horseNo: headers.indexOf('馬號'),
                    horseName: headers.indexOf('馬名'),
                    jockey: headers.indexOf('騎師'),
                    trainer: headers.indexOf('練馬師'),
                    winOdds: headers.indexOf('獨贏賠率')
                };

                for (let i = 1; i < rows.length; i++) {
                    const cells = rows[i].querySelectorAll('td');
                    if (cells.length < 5) continue;
                    const pos = parseInt(cells[colMap.pos]?.textContent.trim());
                    if (isNaN(pos) || pos <= 0) continue;
                    const horseNo = parseInt(cells[colMap.horseNo]?.textContent.trim());
                    const winOdds = parseFloat(cells[colMap.winOdds]?.textContent.trim()) || 0;
                    results.push({ pos, horse_no: horseNo, win_odds: winOdds });
                }
                break;
            }
            return results;
        }''')

        return results
    except Exception as e:
        print(f"    [FAIL] R{race_no}: {e}")
        return []


def apply_results(supabase, race_id: str, results: List[Dict]) -> int:
    """Apply scraped results to race_runners table."""
    updated = 0
    for r in results:
        horse_no = r['horse_no']
        finish_pos = r['pos']
        win_odds = r['win_odds']

        if win_odds <= 1.0:
            continue

        resp = retry_supabase(
            lambda: supabase.table('race_runners').select('runner_id').eq('race_id', race_id).eq('horse_no', horse_no).execute()
        )
        runners = resp.data or []
        if runners:
            runner_id = runners[0]['runner_id']
            retry_supabase(
                lambda rid=runner_id, fp=finish_pos, wo=win_odds: supabase.table('race_runners').update({
                    'finish_position': fp,
                    'win_odds': wo
                }).eq('runner_id', rid).execute()
            )
            updated += 1
    return updated


def generate_ai_review(supabase, race_ids: List[str]) -> int:
    """Generate AI performance review records for finished races."""
    import json

    reviewed = 0
    for race_id in race_ids:
        race_resp = retry_supabase(
            lambda: supabase.table('races').select('race_date,venue,race_no').eq('race_id', race_id).single().execute()
        )
        race_meta = race_resp.data
        if not race_meta:
            continue

        runners_resp = retry_supabase(
            lambda: supabase.table('race_runners').select('*').eq('race_id', race_id).execute()
        )
        preds_resp = retry_supabase(
            lambda: supabase.table('model_predictions').select('*').eq('race_id', race_id).execute()
        )

        runners = runners_resp.data or []
        preds = preds.data or []

        finished = [r for r in runners if r.get('finish_position') is not None]
        if not finished or not preds:
            continue

        finished.sort(key=lambda r: r['finish_position'])
        runner_map = {r['runner_id']: r for r in runners}
        pred_map = {p['runner_id']: p for p in preds}

        sorted_preds = sorted(
            preds,
            key=lambda p: (p.get('final_prob') or p.get('raw_model_prob') or 0),
            reverse=True,
        )

        top1 = sorted_preds[0]
        top1_runner = runner_map.get(top1['runner_id'])
        top1_finish = top1_runner.get('finish_position') if top1_runner else None
        top1_hit = top1_finish == 1

        top3 = sorted_preds[:3]
        top3_hit = 0
        top3_info = []
        for p in top3:
            r = runner_map.get(p['runner_id'])
            fp = r.get('finish_position') if r else None
            hit = fp is not None and fp <= 3
            if hit:
                top3_hit += 1
            top3_info.append({
                'runner_id': p['runner_id'],
                'horse_no': r.get('horse_no') if r else None,
                'finish_pos': fp,
                'predicted_prob': p.get('final_prob') or p.get('raw_model_prob'),
                'hit': hit,
            })

        total_bets = 0
        total_returns = 0
        for p in sorted_preds:
            ev = p.get('expected_value') or 0
            if ev > 0.15:
                r = runner_map.get(p['runner_id'])
                if r and r.get('win_odds') and r.get('finish_position'):
                    total_bets += 100
                    if r['finish_position'] == 1:
                        total_returns += 100 * r['win_odds']
        roi = ((total_returns - total_bets) / total_bets * 100) if total_bets > 0 else 0

        winner = finished[0]
        winner_odds = winner.get('win_odds')
        winner_pred = pred_map.get(winner['runner_id'])
        winner_p = (winner_pred.get('raw_model_prob') or winner_pred.get('final_prob')) if winner_pred else None

        is_upset = winner_odds and winner_odds >= 12.0
        ai_under = is_upset and winner_p and winner_p < 0.10
        rno = race_meta['race_no']

        if ai_under:
            commentary = f'R{rno} 爆冷：#{winner_odds:.0f}x 大冷門跑出，AI 模型僅給 {winner_p*100:.0f}% 勝率，需檢討隱藏因素'
        elif is_upset:
            commentary = f'R{rno} 冷門：#{winner_odds:.0f}x 馬胜出，AI 有留意但賠率反映市場低估'
        elif top1_hit and roi > 0:
            commentary = f'R{rno} AI 首選命中，EV 策略回報 +{roi:.0f}%，模型判斷準確'
        elif top1_hit and roi <= 0:
            commentary = f'R{rno} AI 首選跑出，但 EV 策略虧損 {roi:.0f}%，需收緊入選門檻'
        elif top3_hit >= 2:
            commentary = f'R{rno} AI 前三膽命中 {top3_hit}/3，整體方向正確'
        elif top3_hit == 1:
            commentary = f'R{rno} AI 前三膽僅中 1/3，命中率偏低'
        elif total_bets > 0 and roi < -50:
            commentary = f'R{rno} AI 全數落空且重虧 {roi:.0f}%，本場存在模型未涵蓋因素'
        else:
            commentary = f'R{rno} AI 預測落空，前三膽全數未進前三，累積數據用於權重修正'

        row = {
            'race_id': race_id,
            'race_date': race_meta['race_date'],
            'venue': race_meta['venue'],
            'race_no': rno,
            'top1_pick_runner_id': top1['runner_id'],
            'top1_pick_finish_pos': top1_finish,
            'top1_hit': top1_hit,
            'top3_picks': json.dumps(top3_info, ensure_ascii=False),
            'top3_hit_count': top3_hit,
            'total_bets': total_bets,
            'total_returns': round(total_returns, 2),
            'roi_percent': round(roi, 2),
            'key_factors': json.dumps({'commentary': commentary}, ensure_ascii=False),
        }

        retry_supabase(
            lambda: supabase.table('ai_performance').upsert(row, on_conflict='race_id').execute()
        )
        reviewed += 1
        print(f"    [AI Review] R{rno}: top1_hit={top1_hit}, top3={top3_hit}/3, roi={roi:.1f}%")

    return reviewed


# =====================================================================
# Phase 3: Status Report
# =====================================================================
def write_pipeline_status(supabase, status: Dict):
    """Write pipeline status to Supabase for frontend display."""
    row = {
        'id': 'auto_pilot_latest',
        'last_run': now_hkt().isoformat(),
        'status_json': status,
    }
    try:
        retry_supabase(lambda: supabase.table('pipeline_status').upsert(row, on_conflict='id').execute())
        print(f"\n[Status] Pipeline status written to Supabase")
    except Exception as e:
        print(f"\n[Status] Could not write status (table may not exist): {e}")


# =====================================================================
# Main
# =====================================================================
def main():
    parser = argparse.ArgumentParser(description='Auto-Pilot Pipeline')
    parser.add_argument('--discover-only', action='store_true', help='Only discover and scrape new race days')
    parser.add_argument('--odds-only', action='store_true', help='Only inject live odds for today\'s races')
    parser.add_argument('--archive-only', action='store_true', help='Only archive past unfinished races')
    parser.add_argument('--dry-run', action='store_true', help='Log actions without writing')
    parser.add_argument('--lookahead', type=int, default=7, help='Days to look ahead for new races (default: 7)')
    args = parser.parse_args()

    start_time = now_hkt()
    print("=" * 70)
    print(f"AUTO-PILOT PIPELINE — {start_time.strftime('%Y-%m-%d %H:%M:%S')} HKT")
    print("=" * 70)

    supabase = get_supabase()
    status = {
        'last_run': start_time.isoformat(),
        'discovered': 0,
        'scraped': 0,
        'odds_injected': 0,
        'archived': 0,
        'ai_reviewed': 0,
        'errors': [],
    }

    do_discover = not args.archive_only and not args.odds_only
    do_odds = not args.discover_only and not args.archive_only
    do_archive = not args.discover_only and not args.odds_only

    # Phase 1: Auto-Discovery
    if do_discover:
        print("\n" + "=" * 50)
        print("PHASE 1: AUTO-DISCOVERY & STAGE 1 PRE-SCRAPE")
        print("=" * 50)
        try:
            upcoming = discover_upcoming_race_days(lookahead_days=args.lookahead)
            status['discovered'] = len(upcoming)
            scraped = scrape_new_race_days(supabase, upcoming, dry_run=args.dry_run)
            status['scraped'] = scraped
        except Exception as e:
            print(f"[ERROR] Phase 1 failed: {e}")
            status['errors'].append(f'Phase 1: {str(e)}')

    # Phase 1.5: Odds Injection for today's races
    if do_odds:
        print("\n" + "=" * 50)
        print("PHASE 1.5: LIVE ODDS INJECTION")
        print("=" * 50)
        try:
            injected = inject_odds_for_upcoming_races(supabase, dry_run=args.dry_run)
            status['odds_injected'] = injected
        except Exception as e:
            print(f"[ERROR] Phase 1.5 failed: {e}")
            status['errors'].append(f'Phase 1.5: {str(e)}')

    # Phase 2: Auto-Archive
    if do_archive:
        print("\n" + "=" * 50)
        print("PHASE 2: AUTO-ARCHIVE & POST-RACE REVIEW")
        print("=" * 50)
        try:
            unfinished = find_unfinished_past_races(supabase)
            archived, ai_reviewed = archive_past_races(supabase, unfinished, dry_run=args.dry_run)
            status['archived'] = archived
            status['ai_reviewed'] = ai_reviewed
        except Exception as e:
            print(f"[ERROR] Phase 2 failed: {e}")
            status['errors'].append(f'Phase 2: {str(e)}')

    # Phase 3: Status
    elapsed = (now_hkt() - start_time).total_seconds()
    status['elapsed_seconds'] = round(elapsed, 1)
    status['success'] = len(status['errors']) == 0

    print("\n" + "=" * 70)
    print("SUMMARY")
    print(f"  Discovered:    {status['discovered']} upcoming race days")
    print(f"  Scraped:       {status['scraped']} new race days")
    print(f"  Odds injected: {status['odds_injected']} race days")
    print(f"  Archived:      {status['archived']} past races")
    print(f"  AI reviewed:   {status['ai_reviewed']} races")
    print(f"  Errors:        {len(status['errors'])}")
    print(f"  Elapsed:       {status['elapsed_seconds']}s")
    print("=" * 70)

    if not args.dry_run:
        write_pipeline_status(supabase, status)


if __name__ == '__main__':
    main()
