"""
修復歷史賠率腳本 v5.43
從 HKJC 官方歷史賽果頁面抓取真實獨贏賠率
修復所有 win_odds = 10.0 的歷史記錄

嚴禁觸碰 2026-10-07 的數據
"""

import os
import sys
import time
import re
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

load_dotenv('.env.local')

SUPABASE_URL = os.getenv('NEXT_PUBLIC_SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_KEY')
CUTOFF_DATE = '2026-10-07'

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing Supabase credentials in .env.local")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def get_races_with_fake_odds():
    """找出所有 win_odds = 10.0 的歷史場次"""
    print("查詢 win_odds = 10.0 的記錄...")
    resp = supabase.table('race_runners').select('race_id,horse_no,win_odds').eq('win_odds', 10.0).execute()
    fake_odds = resp.data or []
    print(f"  找到 {len(fake_odds)} 筆 fake odds")

    # 分組 by race_id
    from collections import defaultdict
    by_race = defaultdict(list)
    for r in fake_odds:
        by_race[r['race_id']].append(r['horse_no'])

    # 獲取場次資訊
    race_ids = list(by_race.keys())
    races_resp = supabase.table('races').select('race_id,race_date,venue,race_no').in_('race_id', race_ids).execute()

    races_to_fix = []
    for r in (races_resp.data or []):
        if r['race_date'] < CUTOFF_DATE:
            races_to_fix.append({
                'race_id': r['race_id'],
                'race_date': r['race_date'],
                'venue': r['venue'],
                'race_no': r['race_no'],
                'horses_to_fix': by_race[r['race_id']]
            })

    print(f"  需要修復 {len(races_to_fix)} 場賽事")
    return races_to_fix


def scrape_hkjc_odds(playwright, race_date, venue, race_no):
    """從 HKJC 歷史賽果頁面抓取獨贏賠率"""
    date_str = race_date.replace('-', '/')
    url = f"https://racing.hkjc.com/racing/information/Chinese/Racing/LocalResults.aspx?RaceDate={date_str}&Racecourse={venue}&RaceNo={race_no}"

    browser = playwright.chromium.launch(headless=True)
    try:
        page = browser.new_page()
        page.goto(url, timeout=30000)
        page.wait_for_load_state('networkidle', timeout=15000)

        # 使用 JavaScript 解析賽果表
        odds_map = page.evaluate("""
            () => {
                const result = {};
                const tables = document.querySelectorAll('table');

                for (const table of tables) {
                    const text = table.textContent || '';
                    if (!text.includes('名次') || !text.includes('獨贏')) continue;

                    const rows = table.querySelectorAll('tr');
                    if (rows.length < 2) continue;

                    // 嘗試從 header 找到賠率列
                    const headerCells = rows[0].querySelectorAll('th, td');
                    const headers = Array.from(headerCells).map(c => c.textContent.trim());
                    let oddsColIdx = -1;

                    for (let i = 0; i < headers.length; i++) {
                        const h = headers[i];
                        if (h === '獨贏賠率' || h.includes('獨贏') || h.includes('賠率')) {
                            oddsColIdx = i;
                            break;
                        }
                    }

                    // Fallback: 使用位置 11
                    if (oddsColIdx === -1) oddsColIdx = 11;

                    // 讀取數據行
                    for (let i = 1; i < rows.length; i++) {
                        const cells = rows[i].querySelectorAll('td');
                        if (cells.length < 2) continue;

                        const texts = Array.from(cells).map(c => c.textContent.trim());

                        // 馬號通常在第 1 列 (index 1)
                        let horseNo = -1;
                        for (let j = 0; j < Math.min(5, texts.length); j++) {
                            const n = parseInt(texts[j]);
                            if (!isNaN(n) && n > 0 && n <= 20) {
                                horseNo = n;
                                break;
                            }
                        }

                        if (horseNo < 0) continue;

                        // 讀取賠率
                        if (oddsColIdx < texts.length) {
                            const oddsStr = texts[oddsColIdx].replace(/[^0-9.]/g, '');
                            const odds = parseFloat(oddsStr);
                            if (!isNaN(odds) && odds > 1.0) {
                                result[horseNo] = odds;
                            }
                        }
                    }

                    if (Object.keys(result).length > 0) break;
                }

                return result;
            }
        """)

        return odds_map
    except Exception as e:
        print(f"    ERROR scraping {race_date} {venue} R{race_no}: {e}")
        return {}
    finally:
        browser.close()


def fix_odds_for_race(race_info, playwright):
    """修復單場賽事的賠率"""
    race_id = race_info['race_id']
    race_date = race_info['race_date']
    venue = race_info['venue']
    race_no = race_info['race_no']
    horses_to_fix = race_info['horses_to_fix']

    print(f"  抓取 {race_date} {venue} R{race_no} (需修復馬號: {horses_to_fix})...")

    odds_map = scrape_hkjc_odds(playwright, race_date, venue, race_no)

    if not odds_map:
        print(f"    [FAIL] 無法抓取賠率")
        return 0

    fixed_count = 0
    for horse_no in horses_to_fix:
        if horse_no in odds_map:
            real_odds = odds_map[horse_no]
            # 更新 race_runners
            try:
                supabase.table('race_runners').update({
                    'win_odds': real_odds
                }).eq('race_id', race_id).eq('horse_no', horse_no).execute()
                fixed_count += 1
                print(f"    馬{horse_no}: 10.0 → {real_odds}")
            except Exception as e:
                print(f"    ERROR updating horse {horse_no}: {e}")
        else:
            print(f"    馬{horse_no}: 未在 HKJC 頁面找到")

    return fixed_count


def main():
    print("="*60)
    print("歷史賠率修復腳本 v5.43")
    print(f"修復範圍: race_date < {CUTOFF_DATE}")
    print(f"數據來源: HKJC 官方歷史賽果頁面")
    print("="*60)

    races_to_fix = get_races_with_fake_odds()

    if not races_to_fix:
        print("\n[OK] 無需修復")
        return

    print(f"\n開始抓取 HKJC 歷史賠率...")
    total_fixed = 0

    with sync_playwright() as playwright:
        for i, race in enumerate(races_to_fix, 1):
            print(f"\n[{i}/{len(races_to_fix)}]")
            fixed = fix_odds_for_race(race, playwright)
            total_fixed += fixed

            # 避免過度請求
            if i < len(races_to_fix):
                time.sleep(1.5)

    print("\n" + "="*60)
    print(f"修復完成!")
    print(f"  總共修復: {total_fixed} 筆")
    print("="*60)

    # 驗證
    print("\n驗證修復結果...")
    resp = supabase.table('race_runners').select('race_id').eq('win_odds', 10.0).execute()
    remaining = len(resp.data or [])
    print(f"  剩餘 win_odds=10.0: {remaining} 筆")


if __name__ == '__main__':
    main()
