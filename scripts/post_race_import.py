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
from results_fields import parse_finish_time, parse_margin
from track_meta import normalize_going, normalize_track_course


def _horse_key(name_raw: str) -> str:
    match = re.search(r'\(([A-Z]{1,2}\d{1,4})\)', name_raw or '')
    return match.group(1) if match else (name_raw or '').strip()


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

        actual_url = page.url
        date_path = date_str.replace('-', '')
        if date_path not in actual_url and date_slash not in actual_url:
            print(f"    [SKIP] R{race_no}: HKJC redirected to {actual_url} (future date or invalid)")
            return None

        # Extract race metadata
        race_meta = page.evaluate('''() => {
            const text = document.body.innerText;
            const timeMatch = text.match(/時間\\s*[:：]\\s*(\\d{2}:\\d{2}:\\d{2})/);
            const goingMatch = text.match(/場地狀況\\s*[:：]\\s*([^\\s]+)/);
            const courseMatch = text.match(/賽道\\s*[:：]\\s*(全天候跑道|草地|泥地)/);
            return {
                winning_time: timeMatch ? timeMatch[1] : null,
                going: goingMatch ? goingMatch[1] : null,
                track_course: courseMatch ? courseMatch[1] : null
            };
        }''')

        # Extract results table by header labels so column order can never drift.
        results = page.evaluate('''() => {
            const results = [];
            const tables = document.querySelectorAll('table');

            for (const t of tables) {
                const rows = t.querySelectorAll('tr');
                if (rows.length < 3) continue;

                let headerRow = null;
                for (let ri = 0; ri < Math.min(rows.length, 4); ri++) {
                    const labels = Array.from(rows[ri].querySelectorAll('td, th'))
                        .map(c => c.textContent.trim());
                    if (labels.includes('名次') && labels.includes('馬名')) {
                        headerRow = {ri, labels};
                        break;
                    }
                }
                if (!headerRow) continue;

                const col = (name) => headerRow.labels.indexOf(name);
                const posIdx = col('名次') >= 0 ? col('名次') : col('排名');
                const horseNoIdx = col('馬號');
                const nameIdx = col('馬名');
                const jockeyIdx = col('騎師');
                const timeIdx = col('完成時間');
                const marginIdx = col('頭馬距離');

                for (let ri = headerRow.ri + 1; ri < rows.length; ri++) {
                    const cells = rows[ri].querySelectorAll('td');
                    if (cells.length < 3) continue;
                    const get = (i) => (i >= 0 && i < cells.length)
                        ? cells[i].textContent.trim() : '';

                    const pos = parseInt(get(posIdx));
                    if (isNaN(pos) || pos <= 0) continue;

                    let horseNo = parseInt(get(horseNoIdx));
                    if (isNaN(horseNo) || horseNo <= 0) {
                        for (const cell of cells) {
                            const num = parseInt(cell.textContent.trim());
                            if (!isNaN(num) && num > 0 && num <= 20) {
                                horseNo = num;
                                break;
                            }
                        }
                    }

                    results.push({
                        horse_no: horseNo,
                        horse_name: get(nameIdx),
                        jockey: get(jockeyIdx),
                        finish_position: pos,
                        finish_time: get(timeIdx),
                        margin: get(marginIdx)
                    });
                }
                break;
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
    query = supabase.table('races').select('race_id,race_no,race_date,venue').eq('race_date', date_str).eq('venue', venue)
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

            runners_resp = retry_supabase(
                lambda rid=race_id: supabase.table('race_runners')
                .select('runner_id,horse_no').eq('race_id', rid).execute())
            runner_by_no = {r['horse_no']: r['runner_id'] for r in (runners_resp.data or [])}

            times_written = margins_written = 0
            for finisher in results:
                horse_no = finisher['horse_no']
                finish_pos = finisher['finish_position']
                runner_id = runner_by_no.get(horse_no)
                if not runner_id:
                    continue

                patch = {'finish_position': finish_pos}
                finish_time = parse_finish_time(finisher.get('finish_time'))
                if finish_time is not None:
                    patch['finish_time'] = finish_time
                    times_written += 1
                margin = parse_margin(finisher.get('margin'), finish_pos)
                if margin is not None:
                    patch['margin'] = margin
                    margins_written += 1

                retry_supabase(
                    lambda p=patch, rid=runner_id: supabase.table('race_runners')
                    .update(p).eq('runner_id', rid).execute())
                total_updated += 1

            # Update race with is_finished = true plus going/course when the page has them
            race_patch = {'is_finished': True}
            going = normalize_going(race_results.get('going'))
            if going:
                race_patch['going'] = going
            course = normalize_track_course(race_results.get('track_course'))
            if course:
                race_patch['track_course'] = course
            retry_supabase(lambda rid=race_id, p=race_patch: supabase.table('races').update(
                p).eq('race_id', rid).execute())

            # Per-horse dividend/finish ledger (race_results has no time/margin columns).
            ledger = [{
                'race_id': race_id,
                'race_date': race.get('race_date') or date_str,
                'venue': race.get('venue') or venue,
                'race_no': race_no,
                'finish_position': finisher['finish_position'],
                'horse_no': finisher['horse_no'],
                'horse_name': _horse_key(finisher.get('horse_name', '')),
                'jockey': finisher.get('jockey'),
            } for finisher in results if finisher.get('horse_no')]
            if ledger:
                try:
                    retry_supabase(lambda rows=ledger: supabase.table('race_results').upsert(
                        rows, on_conflict='race_id,horse_no').execute())
                    print(f"    [OK] race_results ledger: {len(ledger)} rows")
                except Exception as e:
                    print(f"    [WARN] race_results write failed: {e}")

            print(f"    [OK] times={times_written} margins={margins_written}")

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
