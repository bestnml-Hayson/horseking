"""
v5.51 整合 trackwork + formline 數據入 race_runners for 2026-10-11
"""
import os
import sys
import json
import re
from collections import defaultdict
from dotenv import load_dotenv
from supabase import create_client, Client

sys.stdout.reconfigure(encoding='utf-8')

load_dotenv('.env.local')

SUPABASE_URL = os.getenv('NEXT_PUBLIC_SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing Supabase credentials")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

RACE_DATE = '2026-10-11'


def parse_trackwork(tw_data):
    result = {}
    for row in tw_data:
        horse_no = int(row.get('編號', 0))
        if horse_no == 0:
            continue
        features = {'trial_count': 0, 'fast_work_count': 0, 'swim_count': 0}
        trial_text = row.get('試閘', '')
        if trial_text:
            features['trial_count'] = len(re.findall(r'\d{2}/\d{2}', trial_text))
        fast_work_text = row.get('快操', '')
        if fast_work_text:
            features['fast_work_count'] = len(re.findall(r'\d{2}/\d{2}', fast_work_text))
        swim_text = row.get('游泳', '')
        if swim_text:
            features['swim_count'] = len(re.findall(r'\d{2}/\d{2}', swim_text))
        result[horse_no] = features
    return result


def parse_formline(fl_data):
    if not fl_data:
        return {}
    horse_form = defaultdict(list)
    current_block_horses = []
    in_block = False
    for row in fl_data:
        keys = list(row.keys())
        if not keys:
            continue
        first_key = keys[0]
        first_val = row.get(first_key, '')
        is_date_sep = bool(re.match(r'\d{2}/\d{2}/\d{4}\s*\(\d+\)', first_val))
        is_header = (first_val == '馬名')
        if is_date_sep:
            if current_block_horses:
                for idx, name in enumerate(current_block_horses):
                    horse_form[name].append(idx + 1)
            current_block_horses = []
            in_block = True
            continue
        if is_header:
            continue
        if first_val and first_val != '馬名' and in_block:
            if re.search(r'[\u4e00-\u9fff]', first_val):
                current_block_horses.append(first_val)
    if current_block_horses:
        for idx, name in enumerate(current_block_horses):
            horse_form[name].append(idx + 1)
    return dict(horse_form)


def compute_fitness_score(trial_count, fast_work_count, swim_count):
    score = 0.0
    if trial_count > 0:
        score += 3.0
    if fast_work_count >= 3:
        score += 2.0
    elif fast_work_count >= 1:
        score += 1.0
    if swim_count >= 5:
        score += 1.0
    return score


def fitness_label(score):
    if score >= 5: return '極高'
    if score >= 4: return '很高'
    if score >= 3: return '高'
    if score >= 2: return '中高'
    if score >= 1: return '中'
    return '低'


def match_horse_name(scraped_name, db_horse_names):
    if not scraped_name or not db_horse_names:
        return None
    scraped_clean = scraped_name.strip()
    for db_name in db_horse_names:
        if db_name.strip() == scraped_clean:
            return db_name
    for db_name in db_horse_names:
        db_clean = db_name.strip()
        if scraped_clean in db_clean or db_clean in scraped_clean:
            return db_name
    return None


def integrate_race(race_no, race_data):
    tw_data = race_data.get('trackwork', [])
    fl_data = race_data.get('formline', [])

    if not tw_data and not fl_data:
        print(f"  R{race_no}: 無 trackwork/formline 數據，跳過")
        return 0

    tw_features = parse_trackwork(tw_data) if tw_data else {}
    fl_form = parse_formline(fl_data) if fl_data else {}

    races_resp = supabase.table('races').select('race_id') \
        .eq('race_date', RACE_DATE).eq('race_no', race_no).execute()
    if not races_resp.data:
        print(f"  R{race_no}: 找不到賽事")
        return 0

    race_id = races_resp.data[0]['race_id']
    runners_resp = supabase.table('race_runners').select('runner_id,horse_no,horse_id') \
        .eq('race_id', race_id).execute()
    runners = runners_resp.data or []

    horse_ids = list(set(r['horse_id'] for r in runners if r.get('horse_id')))
    horse_id_to_name = {}
    if horse_ids:
        horses_resp = supabase.table('horses').select('horse_id,horse_name') \
            .in_('horse_id', horse_ids).execute()
        for h in (horses_resp.data or []):
            horse_id_to_name[h['horse_id']] = h['horse_name']

    runner_horse_names = {}
    for r in runners:
        hid = r.get('horse_id')
        if hid and hid in horse_id_to_name:
            runner_horse_names[r['runner_id']] = horse_id_to_name[hid]

    db_horse_names = list(set(runner_horse_names.values()))

    scraped_to_db = {}
    for scraped_name in fl_form:
        db_name = match_horse_name(scraped_name, db_horse_names)
        if db_name:
            scraped_to_db[scraped_name] = db_name

    updated = 0
    for runner in runners:
        runner_id = runner['runner_id']
        horse_no = runner['horse_no']
        db_name = runner_horse_names.get(runner_id, '')

        update_data = {}

        if horse_no in tw_features:
            tw = tw_features[horse_no]
            fitness = compute_fitness_score(tw['trial_count'], tw['fast_work_count'], tw['swim_count'])
            if tw['trial_count'] > 0:
                update_data['trial_count'] = tw['trial_count']
            if tw['fast_work_count'] > 0:
                update_data['fast_work_count'] = tw['fast_work_count']
            if tw['swim_count'] > 0:
                update_data['swim_count'] = tw['swim_count']
            if fitness > 0:
                update_data['fitness_score'] = fitness
                update_data['fitness_label'] = fitness_label(fitness)

        if db_name:
            for scraped_name, matched_name in scraped_to_db.items():
                if matched_name == db_name:
                    positions = fl_form[scraped_name]
                    if positions:
                        update_data['form_positions'] = ','.join(str(p) for p in positions)
                        update_data['form_avg_finish'] = round(sum(positions) / len(positions), 2)
                        update_data['form_best_finish'] = min(positions)
                    break

        if update_data:
            try:
                supabase.table('race_runners').update(update_data) \
                    .eq('runner_id', runner_id).execute()
                updated += 1
                tw_str = ''
                if horse_no in tw_features:
                    tw = tw_features[horse_no]
                    tw_str = f" TW=[trial={tw['trial_count']},fast={tw['fast_work_count']},swim={tw['swim_count']}]"
                form_str = ''
                if db_name:
                    for sn, mn in scraped_to_db.items():
                        if mn == db_name and sn in fl_form:
                            form_str = f" Form={fl_form[sn]}"
                            break
                print(f"  馬{horse_no} {db_name}:{tw_str}{form_str}")
            except Exception as e:
                print(f"  ERROR 馬{horse_no} {db_name}: {e}")

    return updated


def main():
    print("=" * 60)
    print("v5.51 整合 Trackwork + Formline 數據")
    print(f"賽日: {RACE_DATE}")
    print("=" * 60)

    with open('data/1011_trackwork_formline.json', 'r', encoding='utf-8') as f:
        all_data = json.load(f)

    total_updated = 0
    for race_key in sorted(all_data.keys(), key=lambda x: int(x.replace('R', ''))):
        race_no = int(race_key.replace('R', ''))
        race_data = all_data[race_key]
        print(f"\n--- R{race_no} ---")
        updated = integrate_race(race_no, race_data)
        total_updated += updated

    print(f"\n{'=' * 60}")
    print(f"整合完成! 共更新 {total_updated} 匹馬")
    print("=" * 60)


if __name__ == '__main__':
    main()
