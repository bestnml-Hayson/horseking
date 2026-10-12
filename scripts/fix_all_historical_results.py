#!/usr/bin/env python3
"""
全面修復：重新抓取所有歷史日期的官方賽果
從 HKJC 官方結果頁面重新解析 finish_position 和 win_odds
"""
import io, sys, os, json, time
from datetime import datetime, timedelta
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
sys.path.insert(0, os.path.dirname(__file__))
from common import get_supabase, retry_supabase

# 只修復最近 90 天的數據（用戶最常查看的範圍）
DAYS_BACK = 90


def scrape_race_results(page, date_str: str, venue: str, race_no: int) -> list:
    """Scrape official HKJC results page with precise column mapping."""
    date_slash = date_str.replace('-', '/')
    url = f"https://racing.hkjc.com/racing/information/Chinese/Racing/LocalResults.aspx?RaceDate={date_slash}&Racecourse={venue}&RaceNo={race_no}"
    
    try:
        page.goto(url, wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(4000)

        actual_url = page.url
        date_path = date_str.replace('-', '')
        if date_path not in actual_url and date_slash not in actual_url:
            print(f"    [SKIP] R{race_no}: HKJC redirected to {actual_url} (date mismatch)")
            return []

        results = page.evaluate('''() => {
            const results = [];
            const tables = document.querySelectorAll('table');
            
            for (const table of tables) {
                const rows = table.querySelectorAll('tr');
                if (rows.length < 3) continue;
                
                const headerRow = rows[0];
                const headers = Array.from(headerRow.querySelectorAll('td, th')).map(cell => cell.textContent.trim());
                
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
                    
                    const cleanName = horseName.replace(/\\s*\\(.*?\\)/g, '').trim();
                    
                    results.push({
                        pos, horse_no: horseNo, horse_name: cleanName,
                        jockey, trainer, actual_weight: actualWeight,
                        draw, win_odds: winOdds
                    });
                }
                break;
            }
            return results;
        }''')
        
        return results
    except Exception as e:
        print(f"    [FAIL] R{race_no}: {e}")
        return []


def fix_date(supabase, page, date_str: str, venue: str):
    """Fix all races for a specific date/venue."""
    # Get races for this date
    races = supabase.table('races').select('race_id,race_no').eq('race_date', date_str).eq('venue', venue).execute()
    race_list = races.data or []
    
    if not race_list:
        return 0, 0
    
    total_updated = 0
    total_errors = 0
    
    for race in race_list:
        race_id = race['race_id']
        race_no = race['race_no']
        
        # Scrape official results
        results = scrape_race_results(page, date_str, venue, race_no)
        if not results:
            total_errors += 1
            continue
        
        # Update race_runners
        for r in results:
            horse_no = r['horse_no']
            finish_pos = r['pos']
            win_odds = r['win_odds']
            
            # Validate: win_odds must be > 1.0 (real odds, not default)
            if win_odds <= 1.0:
                continue
            
            resp = retry_supabase(lambda: supabase.table('race_runners').select('runner_id').eq('race_id', race_id).eq('horse_no', horse_no).execute())
            runners = resp.data or []
            
            if runners:
                runner_id = runners[0]['runner_id']
                retry_supabase(lambda: supabase.table('race_runners').update({
                    'finish_position': finish_pos,
                    'win_odds': win_odds
                }).eq('runner_id', runner_id).execute())
                total_updated += 1
    
    return total_updated, total_errors


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[FAIL] playwright not installed")
        sys.exit(1)
    
    supabase = get_supabase()
    
    # Get all dates within the last 90 days
    cutoff_date = (datetime.now() - timedelta(days=DAYS_BACK)).strftime('%Y-%m-%d')
    
    races = supabase.table('races').select('race_date,venue').gte('race_date', cutoff_date).execute()
    date_venue_pairs = set((r['race_date'], r['venue']) for r in (races.data or []))
    
    print(f'全面修復：最近 {DAYS_BACK} 天的 {len(date_venue_pairs)} 個賽事日期')
    print('='*70)
    
    total_updated_all = 0
    total_errors_all = 0
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-gpu'])
        page = browser.new_page()
        
        for date_str, venue in sorted(date_venue_pairs, reverse=True):
            print(f'\n{date_str} {venue}...')
            updated, errors = fix_date(supabase, page, date_str, venue)
            total_updated_all += updated
            total_errors_all += errors
            print(f'  更新: {updated} 筆, 錯誤: {errors} 場')
            
            # Rate limiting to avoid overwhelming HKJC
            time.sleep(2)
        
        browser.close()
    
    print(f'\n{"="*70}')
    print(f'修復完成')
    print(f'  總更新: {total_updated_all} 筆')
    print(f'  總錯誤: {total_errors_all} 場')
    print(f'{"="*70}')


if __name__ == '__main__':
    main()
