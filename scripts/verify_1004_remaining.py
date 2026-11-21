#!/usr/bin/env python3
"""Verify remaining odds=10.0 horses by scraping HKJC with correct column detection."""
import asyncio
from playwright.async_api import async_playwright

DATESLASH = '2026/10/04'
VENUE = 'ST'

CHECKS = {
    1: [5],
    5: [12],
    7: [10],
    9: [8, 12],
    10: [12],
}

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for race_no, horse_nos in CHECKS.items():
            url = f'https://racing.hkjc.com/racing/information/Chinese/Racing/LocalResults.aspx?RaceDate={DATESLASH}&Racecourse={VENUE}&RaceNo={race_no}'
            print(f'\n--- R{race_no} ---')
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                await page.wait_for_timeout(4000)

                odds_map = await page.evaluate('''() => {
                    const oddsMap = {};
                    const tables = document.querySelectorAll('table');
                    for (const t of tables) {
                        const rows = t.querySelectorAll('tr');
                        if (rows.length < 3) continue;
                        const firstRow = rows[0].querySelectorAll('td, th');
                        let hasPositionCol = false;
                        let hasOddsCol = false;
                        let oddsColIdx = -1;
                        for (let i = 0; i < firstRow.length; i++) {
                            const txt = firstRow[i].textContent.trim();
                            if (txt === '名次' || txt === '排名') hasPositionCol = true;
                            if (txt === '獨贏賠率' || txt.includes('獨贏')) {
                                hasOddsCol = true;
                                oddsColIdx = i;
                            }
                        }
                        if (hasPositionCol && hasOddsCol && oddsColIdx >= 0) {
                            for (let ri = 1; ri < rows.length; ri++) {
                                const cells = rows[ri].querySelectorAll('td');
                                if (cells.length <= oddsColIdx) continue;
                                const posText = cells[0].textContent.trim();
                                const pos = parseInt(posText);
                                if (isNaN(pos) || pos <= 0) continue;
                                let horseNo = 0;
                                for (let ci = 0; ci < cells.length; ci++) {
                                    const num = parseInt(cells[ci].textContent.trim());
                                    if (!isNaN(num) && num > 0 && num <= 20) {
                                        horseNo = num;
                                        break;
                                    }
                                }
                                const oddsText = cells[oddsColIdx].textContent.trim();
                                const odds = parseFloat(oddsText);
                                if (!isNaN(odds) && odds > 0 && horseNo > 0) {
                                    oddsMap[horseNo] = odds;
                                }
                            }
                            break;
                        }
                    }
                    return oddsMap;
                }''')

                for hn in horse_nos:
                    hkjc_odds = odds_map.get(hn)
                    print(f'  #{hn}: HKJC odds = {hkjc_odds}')
            except Exception as e:
                print(f'  Error: {e}')

        await browser.close()

asyncio.run(main())
