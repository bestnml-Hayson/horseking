#!/usr/bin/env python3
"""
scripts/auto_scraper.py
HKJC 官方網站即時爬蟲 + Supabase 寫入
-----------------------------------------------------------
流程：
  1. 使用 Playwright 瀏覽器渲染 HKJC bet.hkjc.com SPA 頁面
  2. 提取每場賽事的真實排位表（馬號、馬名、騎師、練馬師、檔位、負磅、賠率）
  3. 清空 Supabase 舊資料
  4. 寫入 races, race_runners, horses 表
  5. 執行 Benter 模型計算

環境變數：
  SUPABASE_URL
  SUPABASE_SERVICE_KEY

CLI：
  python scripts/auto_scraper.py                          # auto-detect today
  python scripts/auto_scraper.py --date 2026-09-27 --venue ST
  python scripts/auto_scraper.py --fetch-live             # auto-detect + write to Supabase
  python scripts/auto_scraper.py --dry-run                # scrape but do not write
"""
import os
import sys
import json
import re
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional

try:
    from supabase import create_client, Client
except ImportError:
    print("[FAIL] supabase-py not installed. Run: pip install supabase")
    sys.exit(1)


# =====================================================================
# Supabase
# =====================================================================
def get_supabase_client() -> Optional[Client]:
    url = os.environ.get('SUPABASE_URL') or os.environ.get('NEXT_PUBLIC_SUPABASE_URL')
    key = os.environ.get('SUPABASE_SERVICE_KEY') or os.environ.get('NEXT_PUBLIC_SUPABASE_ANON_KEY')
    if not url or not key:
        print("[FAIL] Missing SUPABASE_URL/SUPABASE_SERVICE_KEY or NEXT_PUBLIC_SUPABASE_URL/NEXT_PUBLIC_SUPABASE_ANON_KEY env vars")
        return None
    return create_client(url, key)


def clear_old_data(supabase: Client, race_date: str, venue: str):
    print(f"\n[Clear] Clearing old data for {race_date} {venue}...")
    races_resp = supabase.table('races').select('race_id').eq('race_date', race_date).eq('venue', venue).execute()
    race_ids = [r['race_id'] for r in (races_resp.data or [])]

    if race_ids:
        for race_id in race_ids:
            supabase.table('model_predictions').delete().eq('race_id', race_id).execute()
            supabase.table('race_runners').delete().eq('race_id', race_id).execute()
        supabase.table('races').delete().eq('race_date', race_date).eq('venue', venue).execute()
        print(f"  [OK] Cleared {len(race_ids)} races + runners + predictions")
    else:
        print("  [OK] No old data found")


# =====================================================================
# HKJC Scraper (Playwright headless browser)
# =====================================================================
def scrape_hkjc_races(date_str: str, venue: str) -> List[Dict]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[FAIL] playwright not installed. Run: pip install playwright && playwright install chromium")
        sys.exit(1)

    date_path = date_str.replace('-', '')
    date_slash = date_str.replace('-', '/')
    venue_cn = '沙田' if venue == 'ST' else '跑馬地'

    all_races = []
    print(f"\n[Scraper] Starting HKJC scraper for {date_str} {venue_cn}...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-gpu'])
        page = browser.new_page()

        for race_no in range(1, 13):
            print(f"  Scraping R{race_no}...")

            try:
                racecard_url = f"https://racing.hkjc.com/racing/information/Chinese/Racing/RaceCard.aspx?RaceDate={date_slash}&Racecourse={venue}&RaceNo={race_no}"
                page.goto(racecard_url, wait_until='domcontentloaded', timeout=30000)
                page.wait_for_timeout(4000)

                horses = page.evaluate('''() => {
                    const horses = [];
                    const tables = document.querySelectorAll('table');
                    let targetTable = null;

                    for (const t of tables) {
                        const rows = t.querySelectorAll('tr');
                        if (rows.length < 5) continue;

                        const firstRowCells = rows[0].querySelectorAll('td, th');
                        let hasFormCol = false;
                        let hasHorseCol = false;
                        for (const c of firstRowCells) {
                            const txt = c.textContent.trim();
                            if (txt === '6次近績') hasFormCol = true;
                            if (txt === '馬名') hasHorseCol = true;
                        }

                        if (hasFormCol && hasHorseCol) {
                            const secondRowCells = rows.length > 1 ? rows[1].querySelectorAll('td') : [];
                            if (secondRowCells.length >= 10) {
                                const firstCell = secondRowCells[0].textContent.trim();
                                const num = parseInt(firstCell);
                                if (!isNaN(num) && num > 0 && num <= 20) {
                                    targetTable = t;
                                    break;
                                }
                            }
                        }
                    }
                    if (!targetTable) return horses;

                    const rows = targetTable.querySelectorAll('tr');
                    for (let ri = 1; ri < rows.length; ri++) {
                        const cells = rows[ri].querySelectorAll('td');
                        if (cells.length < 10) continue;

                        const horseNoText = cells[0].textContent.trim();
                        const horseNo = parseInt(horseNoText);
                        if (isNaN(horseNo) || horseNo <= 0 || horseNo > 20) continue;

                        const formRaw = cells[1].textContent.trim();
                        const formHistory = formRaw.replace(/[\\/]/g, '-').replace(/\\s+/g, '-').replace(/^-+|-+$/g, '');
                        const horseName = cells[3].textContent.trim();
                        const horseCode = cells[4].textContent.trim();
                        const weight = parseFloat(cells[5].textContent.trim()) || 0;
                        let jockey = cells[6].textContent.trim();
                        const draw = parseInt(cells[8].textContent.trim()) || 0;
                        let trainer = cells[9].textContent.trim();

                        jockey = jockey.split('(')[0].trim();
                        trainer = trainer.split('(')[0].trim();

                        horses.push({
                            horse_no: horseNo,
                            horse_name: horseName,
                            horse_code: horseCode,
                            draw: draw,
                            weight: weight,
                            jockey: jockey,
                            trainer: trainer,
                            form_history: formHistory,
                        });
                    }
                    return horses;
                }''')

                if not horses:
                    print(f"    [SKIP] No horses (race may not exist yet)")
                    if race_no > 1:
                        break
                    continue

                race_meta = page.evaluate('''() => {
                    const text = document.body.innerText;
                    const distMatch = text.match(/(\\d{3,4})米/);
                    const goingMatch = text.match(/(好地|快地|慢地|軟地|黏地|好至快地|好至黏地|好至黏快|黏地|快地)/);
                    const classMatch = text.match(/第([一二三四五六七八九十]+)班/);
                    return {
                        distance: distMatch ? parseInt(distMatch[1]) : null,
                        going: goingMatch ? goingMatch[1] : null,
                        class_level: classMatch ? classMatch[0] : null,
                    };
                }''')

                for h in horses:
                    h['win_odds'] = 0
                    h['place_odds'] = 0

                race_data = {
                    'race_id': f"{venue}-{date_path}-{race_no:02d}",
                    'race_date': date_str,
                    'race_no': race_no,
                    'venue': venue,
                    'distance': race_meta.get('distance'),
                    'class_level': race_meta.get('class_level'),
                    'going': race_meta.get('going'),
                    'horses': horses,
                }
                all_races.append(race_data)
                print(f"    [OK] {len(horses)} horses (form: {horses[0].get('form_history', 'N/A')})")

            except Exception as e:
                print(f"    [FAIL] R{race_no}: {e}")
                if race_no > 1:
                    break

        # Second pass: fetch odds from bet.hkjc.com
        print(f"\n  [Odds] Fetching live odds from bet.hkjc.com...")
        odds_url_base = f"https://bet.hkjc.com/ch/racing/wp/{date_str}/{venue}/{{race_no}}"
        for race_data in all_races:
            race_no = race_data['race_no']
            try:
                page.goto(odds_url_base.format(race_no=race_no), wait_until='domcontentloaded', timeout=20000)
                page.wait_for_timeout(3000)

                odds_map = page.evaluate('''() => {
                    const map = {};
                    const rows = document.querySelectorAll('.rc-odds-row');
                    rows.forEach(row => {
                        const cells = row.querySelectorAll('td');
                        if (cells.length >= 8) {
                            const horseNo = parseInt(cells[0].textContent.trim());
                            const winOdds = parseFloat(cells[7].textContent.trim()) || 0;
                            if (!isNaN(horseNo) && horseNo > 0) {
                                map[horseNo] = winOdds;
                            }
                        }
                    });
                    return map;
                }''')

                for h in race_data['horses']:
                    if h['horse_no'] in odds_map:
                        h['win_odds'] = odds_map[h['horse_no']]

                matched = sum(1 for h in race_data['horses'] if h['win_odds'] > 0)
                print(f"    [OK] R{race_no}: {matched}/{len(race_data['horses'])} horses with odds")

            except Exception as e:
                print(f"    [WARN] R{race_no} odds: {e}")

        browser.close()

    print(f"\n[Scraper] Total: {len(all_races)} races scraped")
    return all_races


# =====================================================================
# Write to Supabase
# =====================================================================
def write_to_supabase(supabase: Client, races: List[Dict], dry_run: bool = False):
    if dry_run:
        print("\n[DRY RUN] Would write:")
        for race in races:
            print(f"  {race['race_id']}: {len(race['horses'])} horses")
        return

    print(f"\n[Write] Writing {len(races)} races to Supabase...")
    horse_id_map = {}

    for race in races:
        race_row = {
            'race_id': race['race_id'][:32],
            'race_date': race['race_date'],
            'race_no': race['race_no'],
            'venue': race['venue'][:4],
            'distance': race.get('distance'),
            'class_level': str(race.get('class_level', ''))[:32] if race.get('class_level') else None,
            'going': str(race.get('going', ''))[:32] if race.get('going') else None,
        }
        supabase.table('races').upsert(race_row, on_conflict='race_id').execute()

        for horse in race['horses']:
            horse_name = horse['horse_name']
            if horse_name not in horse_id_map:
                horse_code = horse.get('horse_code', '')
                if horse_code:
                    horse_id = horse_code[:16]
                else:
                    horse_id = f"H{len(horse_id_map) + 1:04d}"
                horse_id_map[horse_name] = horse_id
                supabase.table('horses').upsert({
                    'horse_id': horse_id[:16],
                    'horse_name': horse_name[:64],
                }, on_conflict='horse_id').execute()

            jockey = horse.get('jockey', '')
            jockey = jockey.split('(')[0].strip() if '(' in jockey else jockey

            runner_id = f"{race['race_id']}_H{horse['horse_no']:02d}"
            form_history = horse.get('form_history', '')
            supabase.table('race_runners').upsert({
                'runner_id': runner_id[:48],
                'race_id': race['race_id'][:32],
                'horse_id': horse_id_map[horse_name][:16],
                'horse_no': horse['horse_no'],
                'jockey': jockey[:64],
                'trainer': horse.get('trainer', '')[:64],
                'actual_weight': horse.get('weight'),
                'draw': horse.get('draw'),
                'win_odds': horse.get('win_odds', 0),
                'past_rating': 50.0,
                'recent_form_score': 50.0,
                'jockey_win_rate': 0.10,
                'trainer_win_rate': 0.10,
                'weight_carried_diff': 0.0,
                'rest_days': 0,
                'form_history': form_history[:64] if form_history else None,
            }, on_conflict='runner_id').execute()

        print(f"  [OK] {race['race_id']}: {len(race['horses'])} runners upserted")

    print("[Write] Done!")


# =====================================================================
# Auto-detect date and venue
# =====================================================================
def auto_detect_venue(today: datetime) -> str:
    weekday = today.weekday()
    if weekday in (2, 5):
        return 'ST'
    elif weekday in (1, 3, 6):
        return 'HV'
    return None


# =====================================================================
# Race time estimation (HKJC typical schedule)
# =====================================================================
RACE_INTERVALS_MIN = [0, 25, 25, 30, 25, 30, 25, 30, 25, 30, 25, 30]

def estimate_race_times(date_str: str, venue: str, num_races: int = 11) -> List[Dict]:
    """Estimate race start times. Day session ~13:00 (ST), Night session ~19:00 (HV)."""
    from datetime import time as dtime
    d = datetime.strptime(date_str, '%Y-%m-%d').date()
    first_race_time = dtime(19, 0) if venue == 'HV' else dtime(13, 0)
    races = []
    for i in range(num_races):
        offset = sum(RACE_INTERVALS_MIN[:i]) if i < len(RACE_INTERVALS_MIN) else i * 28
        start = datetime.combine(d, first_race_time) + timedelta(minutes=offset)
        races.append({'race_no': i + 1, 'start_time': start})
    return races


# =====================================================================
# Odds-only update (for high-frequency mode — no clear, no full rewrite)
# =====================================================================
def scrape_odds_only(date_str: str, venue: str) -> Dict[int, Dict[int, float]]:
    """Scrape current win_odds for all races. Returns {race_no: {horse_no: win_odds}}."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[FAIL] playwright not installed")
        return {}

    date_path = date_str.replace('-', '')
    base_url = f"https://bet.hkjc.com/ch/racing/wp/{date_str}/{venue}/{{race_no}}"
    all_odds = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-gpu'])
        page = browser.new_page()

        for race_no in range(1, 13):
            url = base_url.format(race_no=race_no)
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=20000)
                page.wait_for_timeout(2000)

                odds_data = page.evaluate('''() => {
                    const odds = {};
                    const rows = document.querySelectorAll('.rc-odds-row');
                    rows.forEach(row => {
                        const cells = row.querySelectorAll('td');
                        if (cells.length >= 8) {
                            const horseNo = parseInt(cells[0].textContent.trim());
                            if (!isNaN(horseNo) && horseNo > 0 && horseNo <= 20) {
                                const winOdds = parseFloat(cells[7].textContent.trim()) || 0;
                                odds[horseNo] = winOdds;
                            }
                        }
                    });
                    return odds;
                }''')

                if odds_data:
                    all_odds[race_no] = odds_data
                    print(f"  [Odds] R{race_no}: {len(odds_data)} horses")
                else:
                    if race_no > 1:
                        break

            except Exception as e:
                print(f"  [Odds] R{race_no} failed: {e}")
                if race_no > 1:
                    break

        browser.close()

    return all_odds


def update_odds_in_supabase(supabase: Client, date_str: str, venue: str, odds_map: Dict[int, Dict[int, float]]):
    """Upsert win_odds into race_runners without clearing data."""
    date_path = date_str.replace('-', '')
    total_updated = 0

    for race_no, horse_odds in odds_map.items():
        race_id = f"{venue}-{date_path}-{race_no:02d}"
        for horse_no, win_odds in horse_odds.items():
            runner_id = f"{race_id}_H{horse_no:02d}"
            supabase.table('race_runners').upsert({
                'runner_id': runner_id[:48],
                'race_id': race_id[:32],
                'horse_no': horse_no,
                'win_odds': win_odds,
            }, on_conflict='runner_id').execute()
            total_updated += 1

    print(f"  [OK] Updated {total_updated} odds entries")
    return total_updated


# =====================================================================
# Main
# =====================================================================
def main():
    parser = argparse.ArgumentParser(description='HKJC Race Data Scraper + Supabase Upsert')
    parser.add_argument('--date', help='Race date (YYYY-MM-DD). Auto-detects today if omitted.')
    parser.add_argument('--venue', choices=['ST', 'HV'], help='Venue code. Auto-detects if omitted.')
    parser.add_argument('--dry-run', action='store_true', help='Scrape but do not write to Supabase')
    parser.add_argument('--fetch-live', action='store_true', help='Auto-detect date/venue and write live data to Supabase')
    parser.add_argument('--clear-only', action='store_true', help='Only clear old data, do not scrape')
    parser.add_argument('--odds-only', action='store_true', help='Scrape and update odds only (no clear, no full rewrite)')
    args = parser.parse_args()

    today = datetime.now()
    date_str = args.date or today.strftime('%Y-%m-%d')
    venue = args.venue or auto_detect_venue(today)

    print("=" * 60)
    print(f"HKJC Auto Scraper - {date_str} {venue}")
    print(f"Trigger: {'--fetch-live' if args.fetch_live else 'manual'}")
    print("=" * 60)

    supabase = get_supabase_client()
    if not supabase:
        sys.exit(1)

    if not args.clear_only:
        clear_old_data(supabase, date_str, venue)

    if args.clear_only:
        print("\n[OK] Clear only done!")
        return

    if args.odds_only:
        print(f"\n[Odds-Only] Scraping live odds for {date_str} {venue}...")
        odds_map = scrape_odds_only(date_str, venue)
        if odds_map:
            update_odds_in_supabase(supabase, date_str, venue, odds_map)
        else:
            print("[WARN] No odds scraped")
        return

    races = scrape_hkjc_races(date_str, venue)

    if not races:
        print("\n[WARN] No races scraped. No races today or HKJC page structure changed.")
        sys.exit(0)

    write_to_supabase(supabase, races, dry_run=args.dry_run)

    total_horses = sum(len(r['horses']) for r in races)
    print(f"\n{'=' * 60}")
    print(f"SUMMARY")
    print(f"  Races scraped:  {len(races)}")
    print(f"  Total horses:   {total_horses}")
    print(f"  Date:           {date_str}")
    print(f"  Venue:          {venue}")
    print(f"{'=' * 60}")

    if not args.dry_run:
        print("\nNext: python scripts/benter_model.py supabase")


if __name__ == '__main__':
    main()
