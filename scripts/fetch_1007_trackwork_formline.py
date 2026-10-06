"""
抓取 HKJC trackwork + formline 數據 for 2026-10-07
"""
import sys
import json
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

DATE = '2026/10/07'
VENUE = 'HV'
RACES = list(range(1, 10))  # R1-R9


def scrape_trackwork(page, race_no):
    """抓取晨操/試閘數據"""
    url = f"https://racing.hkjc.com/zh-hk/local/information/localtrackwork?racedate={DATE}&Racecourse={VENUE}&RaceNo={race_no}"
    try:
        page.goto(url, timeout=20000)
        page.wait_for_load_state('networkidle', timeout=10000)

        data = page.evaluate("""
            () => {
                const result = [];
                const tables = document.querySelectorAll('table');
                for (const table of tables) {
                    const rows = table.querySelectorAll('tr');
                    if (rows.length < 2) continue;

                    // Get headers
                    const headerCells = rows[0].querySelectorAll('th, td');
                    const headers = Array.from(headerCells).map(c => c.textContent.trim());

                    for (let i = 1; i < rows.length; i++) {
                        const cells = rows[i].querySelectorAll('td');
                        if (cells.length < 3) continue;
                        const row = {};
                        for (let j = 0; j < cells.length && j < headers.length; j++) {
                            row[headers[j]] = cells[j].textContent.trim();
                        }
                        if (Object.keys(row).length > 0) result.push(row);
                    }
                    if (result.length > 0) break;
                }
                return result;
            }
        """)
        return data
    except Exception as e:
        print(f"  ERROR trackwork R{race_no}: {e}")
        return []


def scrape_formline(page, race_no):
    """抓取近績形勢線"""
    url = f"https://racing.hkjc.com/zh-hk/local/information/formline?racedate={DATE}&Racecourse={VENUE}&RaceNo={race_no}"
    try:
        page.goto(url, timeout=20000)
        page.wait_for_load_state('networkidle', timeout=10000)

        data = page.evaluate("""
            () => {
                const result = [];
                const tables = document.querySelectorAll('table');
                for (const table of tables) {
                    const rows = table.querySelectorAll('tr');
                    if (rows.length < 2) continue;

                    const headerCells = rows[0].querySelectorAll('th, td');
                    const headers = Array.from(headerCells).map(c => c.textContent.trim());

                    for (let i = 1; i < rows.length; i++) {
                        const cells = rows[i].querySelectorAll('td');
                        if (cells.length < 3) continue;
                        const row = {};
                        for (let j = 0; j < cells.length && j < headers.length; j++) {
                            row[headers[j]] = cells[j].textContent.trim();
                        }
                        if (Object.keys(row).length > 0) result.push(row);
                    }
                    if (result.length > 0) break;
                }
                return result;
            }
        """)
        return data
    except Exception as e:
        print(f"  ERROR formline R{race_no}: {e}")
        return []


def main():
    all_data = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        for race_no in RACES:
            print(f"R{race_no}:")

            # Trackwork
            tw = scrape_trackwork(page, race_no)
            print(f"  trackwork: {len(tw)} rows")
            if tw:
                print(f"    headers: {list(tw[0].keys())[:8]}")
                print(f"    sample: {tw[0]}")

            # Formline
            fl = scrape_formline(page, race_no)
            print(f"  formline: {len(fl)} rows")
            if fl:
                print(f"    headers: {list(fl[0].keys())[:8]}")
                print(f"    sample: {fl[0]}")

            all_data[f'R{race_no}'] = {
                'trackwork': tw,
                'formline': fl,
            }

        browser.close()

    # Save to JSON
    with open('data/1007_trackwork_formline.json', 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to data/1007_trackwork_formline.json")


if __name__ == '__main__':
    main()
