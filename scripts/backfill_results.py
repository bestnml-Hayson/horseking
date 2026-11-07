#!/usr/bin/env python3
"""
Backfill results from HKJC for past race days not in DB.
Scrapes results pages, creates races + race_runners + horses,
runs Benter model and AI review.

Usage:
  python scripts/backfill_results.py
  python scripts/backfill_results.py --dates 2026-10-28,2026-11-01,2026-11-04
"""
import sys, os, io, time, re, argparse, random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional

HKT = ZoneInfo('Asia/Hong_Kong')

from common import get_supabase, batch_upsert, retry_supabase


def scrape_results_page(page, date_str: str, venue: str, race_no: int) -> Optional[Dict]:
    """Scrape a single race result from HKJC results page."""
    date_slash = date_str.replace('-', '/')
    date_path = date_str.replace('-', '')
    url = f"https://racing.hkjc.com/zh-hk/local/information/localresults?racedate={date_slash}&Racecourse={venue}&RaceNo={race_no}"

    try:
        page.goto(url, wait_until='domcontentloaded', timeout=20000)
        time.sleep(random.uniform(3.0, 5.0))

        actual_url = page.url
        if date_slash not in actual_url and date_path not in actual_url:
            return None

        race_data = page.evaluate(r'''() => {
            const result = {horses: [], race_info: {}};

            // Extract race info (class, distance, going)
            const raceHeader = document.querySelector(".race_tab .current, [class*=raceHeader]");
            const bodyText = document.body.innerText;

            // Find the main results table
            const tables = document.querySelectorAll("table");
            for (const table of tables) {
                const rows = table.querySelectorAll("tr");
                if (rows.length < 5) continue;
                const headers = Array.from(rows[0].querySelectorAll("td, th")).map(c => c.textContent.trim());
                if (!headers.includes("名次") || !headers.includes("馬號")) continue;

                const colMap = {};
                headers.forEach((h, i) => { colMap[h] = i; });

                for (let i = 1; i < rows.length; i++) {
                    const cells = rows[i].querySelectorAll("td");
                    if (cells.length < 5) continue;

                    const get = (key) => {
                        const idx = colMap[key];
                        return idx !== undefined && idx < cells.length ? cells[idx].textContent.trim() : "";
                    };

                    const pos = parseInt(get("名次"));
                    if (isNaN(pos) || pos <= 0) continue;

                    const horseNo = parseInt(get("馬號"));
                    const horseNameRaw = get("馬名");
                    const horseName = horseNameRaw.replace(/\(.*\)/, '').trim();
                    const horseId = (horseNameRaw.match(/\((L\d+|S\d+|A\d+|C\d+|G\d+|H\d+|K\d+)\)/) || [])[1] || "";

                    const winOdds = parseFloat(get("獨贏賠率")) || 0;
                    const draw = parseInt(get("檔位")) || 0;
                    const jockey = get("騎師");
                    const trainer = get("練馬師");
                    const weightCarried = parseInt(get("實際負磅")) || 0;
                    const declaredWeight = parseInt(get("排位體重")) || 0;
                    const margin = get("頭馬距離");
                    const finishTime = get("完成時間");

                    result.horses.push({
                        pos, horse_no: horseNo, horse_name: horseName, horse_id: horseId,
                        jockey, trainer, draw, weight_carried: weightCarried,
                        declared_weight: declaredWeight, win_odds: winOdds,
                        margin, finish_time: finishTime
                    });
                }
                break;
            }

            // Extract race metadata from page text
            const raceTitle = document.querySelector("td.raceNumber, .race_tab .current, h1");
            if (raceTitle) result.race_info.title = raceTitle.textContent.trim();

            // Try to find class, distance, going from page
            const allText = document.body.innerText;
            const classMatch = allText.match(/(第一班|第二班|第三班|第四班|第五班|新馬賽|國際一級賽|國際二級賽|國際三級賽|小組讓賽|不設分級)/);
            if (classMatch) result.race_info.class = classMatch[1];

            const distMatch = allText.match(/(\d+)\s*米/);
            if (distMatch) result.race_info.distance = parseInt(distMatch[1]);

            const goingMatch = allText.match(/(好地|好快地|好黏地|黏地|濕慢地|大爛地)/);
            if (goingMatch) result.race_info.going = goingMatch[1];

            // Check for race course indicator (ST/HV)
            const isST = allText.includes("沙田");
            const isHV = allText.includes("跑馬地");

            return result;
        }''')

        if not race_data or not race_data.get('horses'):
            return None

        return race_data

    except Exception as e:
        print(f"    [FAIL] R{race_no}: {e}")
        return None


def extract_race_class(title_text: str, page_text: str = "") -> Optional[str]:
    """Extract race class from title or page text."""
    class_map = {
        '第一班': 'Class 1', '第二班': 'Class 2', '第三班': 'Class 3',
        '第四班': 'Class 4', '第五班': 'Class 5',
        '國際一級賽': 'Group 1', '國際二級賽': 'Group 2', '國際三級賽': 'Group 3',
    }
    for cn, en in class_map.items():
        if cn in title_text or cn in page_text:
            return en
    return None


def backfill_race_day(supabase, page, date_str: str, venue: str):
    """Scrape and write all races for a single race day."""
    date_path = date_str.replace('-', '')

    # Check if already in DB
    existing = retry_supabase(
        lambda: supabase.table('races').select('race_id').eq('race_date', date_str).eq('venue', venue).limit(1).execute()
    )
    if existing.data and len(existing.data) > 0:
        print(f"  {date_str} {venue}: already in DB, skipping")
        return 0

    print(f"\n{'='*50}")
    print(f"  Backfilling {date_str} {venue}")
    print(f"{'='*50}")

    races_data = []
    for race_no in range(1, 12):
        print(f"  Scraping R{race_no}...", end=' ', flush=True)
        result = scrape_results_page(page, date_str, venue, race_no)
        if not result or not result.get('horses'):
            print(f"no data (end of card)")
            break
        print(f"{len(result['horses'])} horses")
        races_data.append((race_no, result))
        time.sleep(random.uniform(1.0, 2.0))

    if not races_data:
        print(f"  [WARN] No races found for {date_str} {venue}")
        return 0

    # Build races and race_runners records
    races = []
    all_runners = []
    all_horses = []
    horse_set = set()

    for race_no, result in races_data:
        race_id = f"{venue}-{date_path}-{race_no:02d}"
        race_info = result.get('race_info', {})

        race_class = extract_race_class(race_info.get('title', ''), race_info.get('class', ''))

        race_record = {
            'race_id': race_id,
            'race_date': date_str,
            'venue': venue,
            'race_no': race_no,
            'class_level': race_class or race_info.get('class'),
            'distance': result.get('race_info', {}).get('distance'),
            'going': result.get('race_info', {}).get('going'),
            'is_finished': True,
        }
        races.append(race_record)

        for h in result['horses']:
            horse_name = h['horse_name']
            horse_id_str = h.get('horse_id', '')

            runner_id = f"{race_id}_H{h['horse_no']:02d}"
            runner = {
                'runner_id': runner_id,
                'race_id': race_id,
                'horse_no': h['horse_no'],
                'horse_id': horse_id_str or None,
                'jockey': h['jockey'],
                'trainer': h['trainer'],
                'draw': h['draw'],
                'actual_weight': h['weight_carried'],
                'declared_weight': h['declared_weight'],
                'win_odds': h['win_odds'] if h['win_odds'] > 1.0 else None,
                'finish_position': h['pos'],
            }
            all_runners.append(runner)

            horse_key = horse_id_str or horse_name
            if horse_key not in horse_set:
                horse_set.add(horse_key)
                horse_record = {
                    'horse_name': horse_name,
                    'horse_id': horse_id_str or horse_name,
                }
                all_horses.append(horse_record)

    # Write to Supabase
    print(f"\n  [Write] Writing {len(races)} races, {len(all_runners)} runners...")

    # Upsert horses first
    if all_horses:
        try:
            batch_upsert(supabase, 'horses', all_horses, 'horse_id')
            print(f"  [OK] {len(all_horses)} horses upserted")
        except Exception as e:
            print(f"  [WARN] horses upsert failed: {e}")

    # Upsert races
    try:
        batch_upsert(supabase, 'races', races, 'race_id')
        print(f"  [OK] {len(races)} races upserted")
    except Exception as e:
        print(f"  [FAIL] races upsert: {e}")
        return 0

    # Upsert race_runners
    try:
        batch_upsert(supabase, 'race_runners', all_runners, 'runner_id')
        print(f"  [OK] {len(all_runners)} runners upserted")
    except Exception as e:
        print(f"  [FAIL] race_runners upsert: {e}")
        return 0

    return len(races)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dates', default='2026-10-28,2026-11-01,2026-11-04',
                        help='Comma-separated dates to backfill')
    parser.add_argument('--skip-benter', action='store_true')
    parser.add_argument('--skip-review', action='store_true')
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv('.env.local')

    supabase = get_supabase()
    if not supabase:
        print("[FAIL] Cannot connect to Supabase")
        sys.exit(1)

    dates = [d.strip() for d in args.dates.split(',') if d.strip()]

    # Known venue mapping
    venue_map = {
        '2026-10-28': 'ST',
        '2026-11-01': 'HV',
        '2026-11-04': 'HV',
    }

    from playwright.sync_api import sync_playwright

    total_races = 0
    all_race_ids = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-gpu', '--disable-blink-features=AutomationControlled'])
        page = browser.new_page()
        page.set_extra_http_headers({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Referer': 'https://racing.hkjc.com/',
        })
        page.add_init_script('()=>{Object.defineProperty(navigator,"webdriver",{get:()=>undefined})}')

        for date_str in dates:
            venue = venue_map.get(date_str)
            if not venue:
                # Auto-detect venue
                for v in ['ST', 'HV']:
                    date_slash = date_str.replace('-', '/')
                    url = f'https://racing.hkjc.com/zh-hk/local/information/localresults?racedate={date_slash}&Racecourse={v}&RaceNo=1'
                    page.goto(url, wait_until='domcontentloaded', timeout=15000)
                    time.sleep(3)
                    if date_slash in page.url:
                        horses = page.evaluate('''() => {
                            const tables = document.querySelectorAll("table");
                            for (const t of tables) {
                                const rows = t.querySelectorAll("tr");
                                if (rows.length >= 5) {
                                    const headers = Array.from(rows[0].querySelectorAll("td, th")).map(c => c.textContent.trim());
                                    if (headers.includes("名次")) return rows.length - 1;
                                }
                            }
                            return 0;
                        }''')
                        if horses >= 4:
                            venue = v
                            break

            if not venue:
                print(f"[SKIP] {date_str}: cannot determine venue")
                continue

            races_count = backfill_race_day(supabase, page, date_str, venue)
            total_races += races_count

            # Collect race IDs for Benter/review
            date_path = date_str.replace('-', '')
            for rn in range(1, 12):
                race_id = f"{venue}-{date_path}-{rn:02d}"
                all_race_ids.append(race_id)

        browser.close()

    print(f"\n{'='*50}")
    print(f"Backfill complete: {total_races} races written")
    print(f"{'='*50}")

    # Run Benter model
    if total_races > 0 and not args.skip_benter:
        # Filter to only race IDs that actually exist
        existing = retry_supabase(
            lambda: supabase.table('races').select('race_id').in_('race_id', all_race_ids).execute()
        )
        actual_ids = [r['race_id'] for r in (existing.data or [])]

        if actual_ids:
            print(f"\n[Benter] Running model for {len(actual_ids)} races...")
            try:
                from benter_model import run_analysis
                run_analysis(supabase, race_ids=actual_ids, dry_run=False, pre_race=False)
                print(f"[OK] Benter model done")
            except Exception as e:
                print(f"[WARN] Benter model failed: {e}")

    # Run AI review
    if total_races > 0 and not args.skip_review:
        existing = retry_supabase(
            lambda: supabase.table('races').select('race_id').in_('race_id', all_race_ids).execute()
        )
        actual_ids = [r['race_id'] for r in (existing.data or [])]

        if actual_ids:
            print(f"\n[AI Review] Running review for {len(actual_ids)} races...")
            try:
                from ai_review import review_single_race
                reviewed = 0
                for race_id in actual_ids:
                    try:
                        summary = review_single_race(supabase, race_id)
                        if summary:
                            reviewed += 1
                    except Exception as e:
                        print(f"  {race_id}: {e}")
                print(f"[OK] AI review done: {reviewed}/{len(actual_ids)} races")
            except Exception as e:
                print(f"[WARN] AI review failed: {e}")


if __name__ == '__main__':
    main()
