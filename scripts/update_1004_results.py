#!/usr/bin/env python3
"""
Scrape full results from HKJC for 2026-10-04 and update race_runners.
Updates: finish_position, win_odds, and any other result data.
"""
import asyncio
import sys
import os
from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import get_supabase

DATE_STR = '2026-10-04'
DATE_SLASH = '2026/10/04'
VENUE = 'ST'
TOTAL_RACES = 11


async def scrape_race_results(page, race_no: int) -> list[dict]:
    """Scrape full race results from HKJC."""
    url = f'https://racing.hkjc.com/racing/information/Chinese/Racing/LocalResults.aspx?RaceDate={DATE_SLASH}&Racecourse={VENUE}&RaceNo={race_no}'
    
    await page.goto(url, wait_until='domcontentloaded', timeout=30000)
    await page.wait_for_timeout(4000)
    
    results = await page.evaluate('''() => {
        const results = [];
        const tables = document.querySelectorAll('table');
        
        for (const t of tables) {
            const rows = t.querySelectorAll('tr');
            if (rows.length < 3) continue;
            
            const firstRow = rows[0].querySelectorAll('td, th');
            let hasPositionCol = false;
            let oddsColIdx = -1;
            
            for (let i = 0; i < firstRow.length; i++) {
                const txt = firstRow[i].textContent.trim();
                if (txt === '名次' || txt === '排名') hasPositionCol = true;
                if (txt === '獨贏賠率' || txt.includes('獨贏')) oddsColIdx = i;
            }
            
            if (hasPositionCol && oddsColIdx >= 0) {
                for (let ri = 1; ri < rows.length; ri++) {
                    const cells = rows[ri].querySelectorAll('td');
                    if (cells.length < 3) continue;
                    
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
                    
                    if (horseNo > 0) {
                        results.push({
                            horse_no: horseNo,
                            finish_position: pos,
                            win_odds: isNaN(odds) ? null : odds
                        });
                    }
                }
                break;
            }
        }
        return results;
    }''')
    
    return results


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        sb = get_supabase()
        total_updated = 0
        
        for race_no in range(1, TOTAL_RACES + 1):
            race_id = f'{VENUE}-{DATE_STR.replace("-", "")}-{race_no:02d}'
            print(f'\nR{race_no:02d} ({race_id}): ', end='', flush=True)
            
            try:
                results = await scrape_race_results(page, race_no)
                print(f'{len(results)} 匹馬', end='', flush=True)
                
                updated = 0
                for r in results:
                    horse_no = r['horse_no']
                    finish_pos = r['finish_position']
                    win_odds = r['win_odds']
                    
                    update_data = {'finish_position': finish_pos}
                    if win_odds is not None:
                        update_data['win_odds'] = win_odds
                    
                    resp = sb.table('race_runners').update(update_data).eq(
                        'race_id', race_id
                    ).eq('horse_no', horse_no).execute()
                    
                    if resp.data:
                        updated += 1
                
                print(f' -> 更新 {updated} 筆')
                total_updated += updated
                
            except Exception as e:
                print(f'錯誤: {e}')
        
        await browser.close()
        print(f'\n=== 總共更新 {total_updated} 筆資料 ===')


asyncio.run(main())
