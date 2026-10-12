#!/usr/bin/env python3
"""
緊急修復：重新抓取 10/11 官方賽果，校正 finish_position 和 win_odds
使用精確的 HKJC 賽果頁面解析器
"""
import io, sys, os, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))
from common import get_supabase, retry_supabase

RACE_DATE = '2026-10-01'
VENUE = 'ST'
NUM_RACES = 11


def scrape_race_results(page, race_no: int) -> dict:
    """Scrape official HKJC results page with precise column mapping."""
    date_slash = RACE_DATE.replace('-', '/')
    url = f"https://racing.hkjc.com/racing/information/Chinese/Racing/LocalResults.aspx?RaceDate={date_slash}&Racecourse={VENUE}&RaceNo={race_no}"
    
    try:
        page.goto(url, wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(5000)
        
        # Use JavaScript to precisely parse the results table
        results = page.evaluate('''() => {
            const results = [];
            const tables = document.querySelectorAll('table');
            
            for (const table of tables) {
                const rows = table.querySelectorAll('tr');
                if (rows.length < 3) continue;
                
                // Find header row to map columns
                const headerRow = rows[0];
                const headers = Array.from(headerRow.querySelectorAll('td, th')).map(cell => cell.textContent.trim());
                
                // Look for the results table (has "名次" header)
                if (!headers.includes('名次')) continue;
                
                const colMap = {
                    pos: headers.indexOf('名次'),
                    horseNo: headers.indexOf('馬號'),
                    horseName: headers.indexOf('馬名'),
                    jockey: headers.indexOf('騎師'),
                    trainer: headers.indexOf('練馬師'),
                    actualWeight: headers.indexOf('實際負磅'),
                    draw: headers.indexOf('檔位'),
                    winOdds: headers.indexOf('獨贏賠率')
                };
                
                // Parse data rows
                for (let i = 1; i < rows.length; i++) {
                    const cells = rows[i].querySelectorAll('td');
                    if (cells.length < 5) continue;
                    
                    const pos = parseInt(cells[colMap.pos]?.textContent.trim());
                    if (isNaN(pos) || pos <= 0) continue;
                    
                    const horseNo = parseInt(cells[colMap.horseNo]?.textContent.trim());
                    const horseName = cells[colMap.horseName]?.textContent.trim() || '';
                    const jockey = cells[colMap.jockey]?.textContent.trim() || '';
                    const trainer = cells[colMap.trainer]?.textContent.trim() || '';
                    const actualWeight = parseFloat(cells[colMap.actualWeight]?.textContent.trim()) || 0;
                    const draw = parseInt(cells[colMap.draw]?.textContent.trim()) || 0;
                    const winOdds = parseFloat(cells[colMap.winOdds]?.textContent.trim()) || 0;
                    
                    // Clean horse name (remove horse code in parentheses)
                    const cleanName = horseName.replace(/\\s*\\(.*?\\)/g, '').trim();
                    
                    results.push({
                        pos,
                        horse_no: horseNo,
                        horse_name: cleanName,
                        jockey,
                        trainer,
                        actual_weight: actualWeight,
                        draw,
                        win_odds: winOdds
                    });
                }
                break;
            }
            
            return results;
        }''')
        
        return {'results': results, 'url': url}
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
    total_updated_runners = 0
    total_updated_results = 0
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-gpu'])
        page = browser.new_page()
        
        for race_no in range(1, NUM_RACES + 1):
            race_id = f'{VENUE}-{RACE_DATE.replace("-","")}-{race_no:02d}'
            print(f'\n--- R{race_no} ({race_id}) ---')
            
            scraped = scrape_race_results(page, race_no)
            if not scraped or not scraped.get('results'):
                print(f'  [WARN] No results scraped')
                continue
            
            results = scraped['results']
            print(f'  Scraped {len(results)} finishers')
            
            # Update race_runners: finish_position and win_odds
            for r in results:
                horse_no = r['horse_no']
                finish_pos = r['pos']
                win_odds = r['win_odds']
                
                # Find runner by race_id and horse_no
                resp = retry_supabase(lambda: supabase.table('race_runners').select('runner_id').eq('race_id', race_id).eq('horse_no', horse_no).execute())
                runners = resp.data or []
                
                if runners:
                    runner_id = runners[0]['runner_id']
                    retry_supabase(lambda: supabase.table('race_runners').update({
                        'finish_position': finish_pos,
                        'win_odds': win_odds
                    }).eq('runner_id', runner_id).execute())
                    total_updated_runners += 1
            
            # Update race_results: win_odds
            for r in results:
                horse_no = r['horse_no']
                win_odds = r['win_odds']
                
                retry_supabase(lambda: supabase.table('race_results').update({
                    'win_odds': win_odds
                }).eq('race_id', race_id).eq('horse_no', horse_no).execute())
                total_updated_results += 1
            
            # Show first 3 finishers for verification
            top3 = sorted(results, key=lambda x: x['pos'])[:3]
            for r in top3:
                print(f'  #{r["pos"]} #{r["horse_no"]} {r["horse_name"]} odds={r["win_odds"]}')
        
        browser.close()
    
    print(f'\n{"="*60}')
    print(f'修復完成')
    print(f'  race_runners 更新: {total_updated_runners} 筆')
    print(f'  race_results 更新: {total_updated_results} 筆')
    print(f'{"="*60}')


if __name__ == '__main__':
    main()
