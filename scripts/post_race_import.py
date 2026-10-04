#!/usr/bin/env python3
"""
scripts/post_race_import.py
Stage 3: Post-Race Result Import

Scrapes official race results from HKJC and:
  1. Populates finish_position on race_runners
  2. Marks races as is_finished = true
  3. Imports payouts (win/place/placeQ)
  4. Writes to race_results table

CLI:
  python scripts/post_race_import.py --date 2026-10-04 --venue ST
  python scripts/post_race_import.py --date 2026-10-04 --venue ST --race 1,2,3
  python scripts/post_race_import.py --date 2026-10-04 --venue ST --all
"""
import os
import sys
import re
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

HKT = ZoneInfo('Asia/Hong_Kong')

sys.path.insert(0, os.path.dirname(__file__))
from common import get_supabase, retry_supabase


def scrape_race_results(page, date_str: str, venue: str, race_no: int) -> dict:
    """
    Scrape race results from HKJC results page.
    Returns: {
        'race_id': str,
        'race_no': int,
        'winning_time': str,
        'going': str,
        'results': [{'horse_no': int, 'horse_name': str, 'jockey': str, 'finish_position': int, 'finish_time': str}],
        'payouts': {'win': float, 'place': [float], 'place_q': [float]}
    }
    """
    date_slash = date_str.replace('-', '/')
    venue_cn = '沙田' if venue == 'ST' else '跑馬地'

    results_url = f"https://racing.hkjc.com/racing/information/Chinese/Racing/LocalResults.aspx?RaceDate={date_slash}&Racecourse={venue}&RaceNo={race_no}"

    try:
        page.goto(results_url, wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(4000)

        # Extract race metadata
        race_meta = page.evaluate('''() => {
            const text = document.body.innerText;
            const timeMatch = text.match(/時間\\s*[:：]\\s*(\\d{2}:\\d{2}:\\d{2})/);
            const goingMatch = text.match(/好至黏快|好至快地|好至黏地|好地|快地|慢地|軟地|黏地/);
            return {
                winning_time: timeMatch ? timeMatch[1] : null,
                going: goingMatch ? goingMatch[0] : null
            };
        }''')

        # Extract results table
        results = page.evaluate('''() => {
            const results = [];
            const tables = document.querySelectorAll('table');

            for (const t of tables) {
                const rows = t.querySelectorAll('tr');
                if (rows.length < 3) continue;

                // Find the results table by looking for "名次" header
                const firstRow = rows[0].querySelectorAll('td, th');
                let hasPositionCol = false;
                let hasHorseCol = false;

                for (let i = 0; i < firstRow.length; i++) {
                    const txt = firstRow[i].textContent.trim();
                    if (txt === '名次' || txt === '排名') hasPositionCol = true;
                    if (txt === '馬名') hasHorseCol = true;
                }

                if (hasPositionCol && hasHorseCol) {
                    for (let ri = 1; ri < rows.length; ri++) {
                        const cells = rows[ri].querySelectorAll('td');
                        if (cells.length < 5) continue;

                        const posText = cells[0].textContent.trim();
                        const pos = parseInt(posText);
                        if (isNaN(pos) || pos <= 0) continue;

                        const horseName = cells[2].textContent.trim();
                        const jockey = cells[4].textContent.trim();

                        // Horse number is usually in a specific column
                        let horseNo = 0;
                        for (let ci = 0; ci < cells.length; ci++) {
                            const num = parseInt(cells[ci].textContent.trim());
                            if (!isNaN(num) && num > 0 && num <= 20) {
                                horseNo = num;
                                break;
                            }
                        }

                        results.push({
                            horse_no: horseNo,
                            horse_name: horseName,
                            jockey: jockey,
                            finish_position: pos
                        });
                    }
                    break;
                }
            }
            return results;
        }''')

        # Extract payouts
        payouts = page.evaluate('''() => {
            const text = document.body.innerText;
            const payouts = {};

            // Win payout
            const winMatch = text.match(/獨贏\\s*\\d+\\s*([\\d.]+)/);
            if (winMatch) payouts.win = parseFloat(winMatch[1]);

            // Place payouts
            const placeMatches = text.matchAll(/位置\\s*\\d+\\s*([\\d.]+)/g);
            payouts.place = [];
            for (const m of placeMatches) {
                payouts.place.push(parseFloat(m[1]));
            }

            // Place Q payouts
            const pqMatches = text.matchAll(/位置Q\\s*[\\d/]+\\s*([\\d.]+)/g);
            payouts.place_q = [];
            for (const m of pqMatches) {
                payouts.place_q.push(parseFloat(m[1]));
            }

            return payouts;
        }''')

        return {
            'race_no': race_no,
            'winning_time': race_meta.get('winning_time'),
            'going': race_meta.get('going'),
            'results': results,
            'payouts': payouts,
        }

    except Exception as e:
        print(f"    [FAIL] R{race_no} results scrape: {e}")
        return None


def import_results(supabase, date_str: str, venue: str, race_nos: list = None):
    """Main post-race import pipeline"""
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
    print(f"Post-Race Import - {date_str} {venue}")
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

            # Scrape results
            race_results = scrape_race_results(page, date_str, venue, race_no)

            if not race_results or not race_results['results']:
                print(f"    [WARN] No results scraped")
                continue

            results = race_results['results']
            print(f"    [OK] {len(results)} finishers")

            # Update race_runners with finish_position
            for finisher in results:
                horse_no = finisher['horse_no']
                finish_pos = finisher['finish_position']

                if horse_no > 0:
                    # Find runner by race_id and horse_no
                    resp = supabase.table('race_runners').select('runner_id').eq('race_id', race_id).eq('horse_no', horse_no).execute()
                    runners = resp.data or []

                    if runners:
                        runner_id = runners[0]['runner_id']
                        retry_supabase(lambda: supabase.table('race_runners').update({
                            'finish_position': finish_pos
                        }).eq('runner_id', runner_id).execute())
                        total_updated += 1

            # Update race with is_finished = true
            retry_supabase(lambda: supabase.table('races').update({
                'is_finished': True
            }).eq('race_id', race_id).execute())

            # Write to race_results table
            payouts = race_results.get('payouts', {})
            race_result_row = {
                'race_id': race_id,
                'winning_time': race_results.get('winning_time'),
                'winning_odds': payouts.get('win'),
                'race_status': 'finished',
            }

            # Add top finishers
            sorted_results = sorted(results, key=lambda x: x['finish_position'])
            if len(sorted_results) >= 1:
                race_result_row['first_horse_no'] = sorted_results[0]['horse_no']
            if len(sorted_results) >= 2:
                race_result_row['second_horse_no'] = sorted_results[1]['horse_no']
            if len(sorted_results) >= 3:
                race_result_row['third_horse_no'] = sorted_results[2]['horse_no']

            try:
                retry_supabase(lambda: supabase.table('race_results').upsert(
                    race_result_row, on_conflict='race_id'
                ).execute())
                print(f"    [OK] race_results updated")
            except Exception as e:
                print(f"    [WARN] race_results write failed: {e}")

        browser.close()

    print(f"\n{'=' * 60}")
    print(f"SUMMARY")
    print(f"  Total runners updated: {total_updated}")
    print(f"  Races marked finished: {len(races)}")
    print(f"{'=' * 60}")


def main():
    parser = argparse.ArgumentParser(description='Post-Race Result Import')
    parser.add_argument('--date', help='Race date (YYYY-MM-DD). Defaults to today.')
    parser.add_argument('--venue', choices=['ST', 'HV'], help='Venue code')
    parser.add_argument('--race', help='Comma-separated race numbers (e.g., 1,2,3)')
    parser.add_argument('--all', action='store_true', help='Import all races for the date')
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

    import_results(supabase, date_str, venue, race_nos)


if __name__ == '__main__':
    main()
