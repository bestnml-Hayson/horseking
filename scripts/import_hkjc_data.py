#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/import_hkjc_data.py
匯入 HKJC 真實賽事資料至 Supabase
"""
import json
import os
import sys
from datetime import datetime

try:
    from supabase import create_client
except ImportError:
    print("ERROR: supabase-py not installed. Run: pip install supabase")
    sys.exit(1)


def get_supabase_client():
    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_SERVICE_KEY')
    if not url or not key:
        raise EnvironmentError("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY")
    return create_client(url, key)


def clear_old_data(client, race_date):
    """清除指定日期的舊資料"""
    print(f"清除 {race_date} 的舊資料...")

    # 先刪除 model_predictions (依賴 race_runners)
    try:
        client.table('model_predictions').delete().filter(
            'race_id', 'like', f'%{race_date.replace("-", "")}%'
        ).execute()
        print("  [OK] model_predictions cleared")
    except Exception as e:
        print(f"  [WARN] model_predictions clear failed: {e}")

    # 刪除 race_runners (依賴 races)
    try:
        client.table('race_runners').delete().filter(
            'race_id', 'like', f'%{race_date.replace("-", "")}%'
        ).execute()
        print("  [OK] race_runners cleared")
    except Exception as e:
        print(f"  [WARN] race_runners clear failed: {e}")

    # 刪除 races
    try:
        client.table('races').delete().filter(
            'race_date', 'eq', race_date
        ).execute()
        print("  [OK] races cleared")
    except Exception as e:
        print(f"  [WARN] races clear failed: {e}")


def import_races(client, races_data):
    """匯入賽事資料"""
    print(f"\n匯入 {len(races_data)} 場賽事...")

    races_rows = []
    horses_rows = []
    runners_rows = []

    horse_id_map = {}  # horse_name -> horse_id

    for race in races_data:
        race_id = race['race_id']
        race_no = race['race_no']
        race_date = '2026-09-27'
        venue = 'ST'

        # 賽事資料
        races_rows.append({
            'race_id': race_id,
            'race_date': race_date,
            'venue': venue,
            'race_no': race_no,
            'distance': race.get('distance'),
            'going': race.get('going'),
            'class_level': race.get('class_level'),
        })

        # 馬匹資料
        for horse in race['horses']:
            horse_name = horse['horse_name']
            if horse_name not in horse_id_map:
                horse_id = f"H{len(horse_id_map) + 1:04d}"
                horse_id_map[horse_name] = horse_id
                horses_rows.append({
                    'horse_id': horse_id,
                    'horse_name': horse_name,
                })

        # 出賽紀錄
        for horse in race['horses']:
            horse_no = horse['horse_no']
            horse_name = horse['horse_name']
            horse_id = horse_id_map[horse_name]
            runner_id = f"{race_id}_H{horse_no:02d}"

            # 解析騎師名稱（去除體重調整標記）
            jockey = horse.get('jockey', '')
            jockey = jockey.split('(')[0].strip() if '(' in jockey else jockey

            runners_rows.append({
                'runner_id': runner_id,
                'race_id': race_id,
                'horse_id': horse_id,
                'horse_no': horse_no,
                'jockey': jockey,
                'trainer': horse.get('trainer', ''),
                'actual_weight': horse.get('weight'),
                'draw': horse.get('draw'),
                'win_odds': horse.get('win_odds'),
                # 預設值（無歷史資料）
                'past_rating': 50.0,
                'recent_form_score': 50.0,
                'jockey_win_rate': 0.10,
                'trainer_win_rate': 0.10,
                'weight_carried_diff': 0.0,
                'rest_days': 0,
            })

    # 批次匯入
    print(f"  Importing {len(races_rows)} races...")
    try:
        client.table('races').upsert(races_rows, on_conflict='race_id').execute()
        print("    [OK] races imported")
    except Exception as e:
        print(f"    [FAIL] races import failed: {e}")
        return False

    print(f"  Importing {len(horses_rows)} horses...")
    try:
        client.table('horses').upsert(horses_rows, on_conflict='horse_id').execute()
        print("    [OK] horses imported")
    except Exception as e:
        print(f"    [FAIL] horses import failed: {e}")
        return False

    print(f"  Importing {len(runners_rows)} race runners...")
    try:
        client.table('race_runners').upsert(runners_rows, on_conflict='runner_id').execute()
        print("    [OK] race_runners imported")
    except Exception as e:
        print(f"    [FAIL] race_runners import failed: {e}")
        return False

    return True


def main():
    json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'hkjc_races_20260927.json')

    if not os.path.exists(json_path):
        print(f"ERROR: JSON file not found: {json_path}")
        return 1

    print(f"讀取 JSON: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    race_date = data['race_date']
    races = data['races']

    total_horses = sum(len(r['horses']) for r in races)
    print(f"賽事日期: {race_date}")
    print(f"場次: {len(races)} 場")
    print(f"馬匹總數: {total_horses} 匹")

    client = get_supabase_client()

    # 清除舊資料
    clear_old_data(client, race_date)

    # 匯入新資料
    success = import_races(client, races)

    if success:
        print("\n[SUCCESS] Import completed!")
        print("Next step: python scripts/benter_model.py supabase")
        return 0
    else:
        print("\n[FAIL] Import failed")
        return 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n中斷")
        sys.exit(130)
    except Exception as e:
        import traceback
        print(f"FATAL: {e}")
        traceback.print_exc()
        sys.exit(1)
