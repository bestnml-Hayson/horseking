"""
歷史數據修復腳本 v5.43
修復所有 race_date < '2026-10-07' 的歷史賽事數據
嚴禁觸碰 2026-10-07 的數據

修復項目：
1. race_results.horse_name: 馬匹代碼 → 中文馬名
2. races.is_finished: 確保有賽果的場次標記為 true
"""

import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv('.env.local')

SUPABASE_URL = os.getenv('NEXT_PUBLIC_SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_KEY')
CUTOFF_DATE = '2026-10-07'

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing Supabase credentials in .env.local")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def fix_horse_names():
    """修正 race_results.horse_name: 馬匹代碼 → 中文馬名"""
    print("\n" + "="*60)
    print("步驟 1: 修正 race_results.horse_name (代碼 → 中文馬名)")
    print("="*60)

    # 1. 讀取所有馬匹映射 (horse_id → horse_name)
    print("讀取 horses 表...")
    horses_resp = supabase.table('horses').select('horse_id,horse_name').execute()
    horse_map = {h['horse_id']: h['horse_name'] for h in (horses_resp.data or [])}
    print(f"  找到 {len(horse_map)} 匹馬")

    # 2. 讀取所有歷史 race_results (race_date < cutoff)
    print(f"讀取 race_results (race_date < {CUTOFF_DATE})...")
    results_resp = supabase.table('race_results').select('*').lt('race_date', CUTOFF_DATE).execute()
    results = results_resp.data or []
    print(f"  找到 {len(results)} 筆歷史賽果")

    # 3. 找出需要修正的記錄 (horse_name 是馬匹代碼)
    to_fix = []
    for r in results:
        horse_name_in_result = r.get('horse_name', '')
        if horse_name_in_result in horse_map:
            # horse_name 是代碼，需要替換
            to_fix.append({
                'id': r['id'],
                'current_name': horse_name_in_result,
                'correct_name': horse_map[horse_name_in_result],
                'race_id': r['race_id'],
            })

    print(f"  需要修正: {len(to_fix)} 筆")

    if not to_fix:
        print("  [OK] 無需修正")
        return 0

    # 4. 批量更新
    fixed_count = 0
    batch_size = 100
    for i in range(0, len(to_fix), batch_size):
        batch = to_fix[i:i+batch_size]
        for item in batch:
            try:
                supabase.table('race_results').update({
                    'horse_name': item['correct_name']
                }).eq('id', item['id']).execute()
                fixed_count += 1
            except Exception as e:
                print(f"  ERROR updating id={item['id']}: {e}")

    print(f"  [OK] 已修正 {fixed_count} 筆")

    # 5. 顯示修正範例
    print("\n  修正範例 (前 10 筆):")
    for item in to_fix[:10]:
        print(f"    {item['current_name']} → {item['correct_name']}")

    return fixed_count


def fix_is_finished():
    """修正 races.is_finished: 確保有賽果的場次標記為 true"""
    print("\n" + "="*60)
    print("步驟 2: 修正 races.is_finished (有賽果 → true)")
    print("="*60)

    # 1. 找出所有有 race_results 的 race_id (歷史)
    print(f"查詢有賽果的歷史場次 (race_date < {CUTOFF_DATE})...")
    results_resp = supabase.table('race_results').select('race_id,race_date').lt('race_date', CUTOFF_DATE).execute()
    race_ids_with_results = set(r['race_id'] for r in (results_resp.data or []))
    print(f"  找到 {len(race_ids_with_results)} 個有賽果的場次")

    if not race_ids_with_results:
        print("  [OK] 無需修正")
        return 0

    # 2. 找出這些場次中 is_finished = false 或 NULL 的
    race_ids_list = list(race_ids_with_results)
    batch_size = 500
    to_fix = []

    for i in range(0, len(race_ids_list), batch_size):
        batch_ids = race_ids_list[i:i+batch_size]
        races_resp = supabase.table('races').select('race_id,is_finished').in_('race_id', batch_ids).execute()
        for r in (races_resp.data or []):
            if not r.get('is_finished'):
                to_fix.append(r['race_id'])

    print(f"  需要修正 is_finished: {len(to_fix)} 場")

    if not to_fix:
        print("  [OK] 無需修正")
        return 0

    # 3. 批量更新
    fixed_count = 0
    for i in range(0, len(to_fix), batch_size):
        batch_ids = to_fix[i:i+batch_size]
        try:
            supabase.table('races').update({'is_finished': True}).in_('race_id', batch_ids).execute()
            fixed_count += len(batch_ids)
        except Exception as e:
            print(f"  ERROR updating batch: {e}")

    print(f"  [OK] 已修正 {fixed_count} 場")
    return fixed_count


def verify_fixes():
    """驗證修復結果"""
    print("\n" + "="*60)
    print("驗證修復結果")
    print("="*60)

    # 1. 檢查 race_results 是否還有馬匹代碼
    results_resp = supabase.table('race_results').select('horse_name').lt('race_date', CUTOFF_DATE).execute()
    results = results_resp.data or []

    # 讀取 horse_id 列表
    horses_resp = supabase.table('horses').select('horse_id').execute()
    horse_codes = set(h['horse_id'] for h in (horses_resp.data or []))

    still_codes = [r for r in results if r.get('horse_name') in horse_codes]
    print(f"  race_results 中仍有馬匹代碼: {len(still_codes)} 筆")

    # 2. 檢查 is_finished
    races_resp = supabase.table('races').select('race_id,is_finished').lt('race_date', CUTOFF_DATE).execute()
    races = races_resp.data or []
    not_finished = [r for r in races if not r.get('is_finished')]
    print(f"  歷史場次 is_finished=false: {len(not_finished)} 場")

    # 3. 確認 10/7 數據未被觸碰
    oct7_resp = supabase.table('race_results').select('count').eq('race_date', '2026-10-07').execute()
    oct7_count = oct7_resp.data[0]['count'] if oct7_resp.data else 0
    print(f"  2026-10-07 race_results 筆數: {oct7_count} (應保持不變)")


def main():
    print("="*60)
    print("歷史數據修復腳本 v5.43")
    print(f"修復範圍: race_date < {CUTOFF_DATE}")
    print(f"嚴禁觸碰: {CUTOFF_DATE}")
    print("="*60)

    fixed_names = fix_horse_names()
    finished_fixed = fix_is_finished()

    verify_fixes()

    print("\n" + "="*60)
    print("修復完成!")
    print(f"  馬名修正: {fixed_names} 筆")
    print(f"  is_finished 修正: {finished_fixed} 場")
    print("="*60)


if __name__ == '__main__':
    main()
