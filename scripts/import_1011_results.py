#!/usr/bin/env python3
"""Import 10/11 ST race results into race_results table with full details."""
import io, sys, os, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))
from common import get_supabase, retry_supabase

RACE_DATE = '2026-10-11'
VENUE = 'ST'
NUM_RACES = 11


def scrape_results(page, race_no: int) -> dict:
    date_slash = RACE_DATE.replace('-', '/')
    url = f"https://racing.hkjc.com/racing/information/Chinese/Racing/LocalResults.aspx?RaceDate={date_slash}&Racecourse={VENUE}&RaceNo={race_no}"
    try:
        page.goto(url, wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(4000)

        data = page.evaluate('''() => {
            const text = document.body.innerText;
            const results = [];
            const tables = document.querySelectorAll('table');

            for (const t of tables) {
                const rows = t.querySelectorAll('tr');
                if (rows.length < 3) continue;

                const firstRow = rows[0].querySelectorAll('td, th');
                let colIdx = {};
                for (let i = 0; i < firstRow.length; i++) {
                    const txt = firstRow[i].textContent.trim();
                    if (txt === '名次' || txt === '排名') colIdx.pos = i;
                    if (txt === '馬號') colIdx.horseNo = i;
                    if (txt === '馬名') colIdx.horseName = i;
                    if (txt === '騎師') colIdx.jockey = i;
                    if (txt === '練馬師') colIdx.trainer = i;
                }

                if (colIdx.pos !== undefined && colIdx.horseName !== undefined) {
                    for (let ri = 1; ri < rows.length; ri++) {
                        const cells = rows[ri].querySelectorAll('td');
                        if (cells.length < 5) continue;

                        const pos = parseInt(cells[colIdx.pos].textContent.trim());
                        if (isNaN(pos) || pos <= 0) continue;

                        let horseNo = 0;
                        if (colIdx.horseNo !== undefined) {
                            horseNo = parseInt(cells[colIdx.horseNo].textContent.trim());
                        } else {
                            for (let ci = 0; ci < cells.length; ci++) {
                                if (ci === colIdx.pos) continue;
                                const n = parseInt(cells[ci].textContent.trim());
                                if (!isNaN(n) && n > 0 && n <= 20) { horseNo = n; break; }
                            }
                        }

                        const horseName = colIdx.horseName !== undefined ? cells[colIdx.horseName].textContent.trim() : '';
                        const jockey = colIdx.jockey !== undefined ? cells[colIdx.jockey].textContent.trim() : '';
                        const trainer = colIdx.trainer !== undefined ? cells[colIdx.trainer].textContent.trim() : '';

                        results.push({ pos, horse_no: horseNo, horse_name: horseName, jockey, trainer });
                    }
                    break;
                }
            }

            const payouts = {};
            const winMatch = text.match(/獨贏\s*(\d+)\s*\$?([\d.]+)/);
            if (winMatch) {
                payouts.win_horse = parseInt(winMatch[1]);
                payouts.win_div = parseFloat(winMatch[2]);
            }

            const placeMatches = [...text.matchAll(/位置\s*(\d+)\s*\$?([\d.]+)/g)];
            payouts.place = placeMatches.map(m => ({ horse: parseInt(m[1]), odds: parseFloat(m[2]) }));

            return { results, payouts };
        }''')

        return data
    except Exception as e:
        print(f"    [FAIL] R{race_no}: {e}")
        return None


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[FAIL] playwright not installed")
        sys.exit(1)

    supabase = get_supabase()
    total_results = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-gpu'])
        page = browser.new_page()

        for race_no in range(1, NUM_RACES + 1):
            race_id = f'{VENUE}-{RACE_DATE.replace("-","")}-{race_no:02d}'
            print(f'\n--- R{race_no} ({race_id}) ---')

            scraped = scrape_results(page, race_no)
            if not scraped or not scraped.get('results'):
                print(f'  [WARN] No results scraped')
                continue

            results = scraped['results']
            payouts = scraped.get('payouts', {})

            # Get win_odds from existing race_runners
            odds_resp = retry_supabase(lambda: supabase.table('race_runners').select(
                'horse_no,win_odds'
            ).eq('race_id', race_id).execute())
            odds_map = {}
            for row in (odds_resp.data or []):
                if row['win_odds'] and row['win_odds'] > 1.0:
                    odds_map[row['horse_no']] = row['win_odds']

            # Write per-runner results to race_results
            for r in results:
                horse_no = r['horse_no']
                win_odds = odds_map.get(horse_no, 0)

                result_row = {
                    'race_id': race_id,
                    'race_date': RACE_DATE,
                    'venue': VENUE,
                    'race_no': race_no,
                    'finish_position': r['pos'],
                    'horse_no': horse_no,
                    'horse_name': r['horse_name'],
                    'jockey': r['jockey'],
                    'trainer': r['trainer'],
                    'win_odds': win_odds,
                }
                try:
                    retry_supabase(lambda rr=result_row: supabase.table('race_results').upsert(
                        rr, on_conflict='race_id,horse_no'
                    ).execute())
                    total_results += 1
                except Exception as e:
                    print(f'  [WARN] #{horse_no} write failed: {e}')

            win_info = f"獨贏 #{payouts.get('win_horse','-')} ${payouts.get('win_div',0)}" if payouts.get('win_horse') else ""
            print(f'  [OK] {len(results)} runners written {win_info}')

        browser.close()

    print(f'\n{"="*60}')
    print(f'SUMMARY: {total_results} runner results written to race_results')
    print(f'{"="*60}')


if __name__ == '__main__':
    main()
