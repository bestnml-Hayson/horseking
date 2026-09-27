#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bill Benter 賽馬量化分析系統 - 歷史數據特徵工程腳本
讀取 data/history/ JSON 檔案，計算 Benter 模型特徵，寫入 Supabase
"""

import json
import os
import sys
import glob
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

try:
    from supabase import create_client, Client
except ImportError:
    print("ERROR: supabase-py not installed. Run: pip install supabase")
    sys.exit(1)


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_DIR = os.path.join(BASE_DIR, 'data', 'history')


def get_supabase_client() -> Client:
    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_SERVICE_KEY')
    if not url or not key:
        raise EnvironmentError("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY environment variables")
    return create_client(url, key)


def load_history_files() -> List[Dict]:
    pattern = os.path.join(HISTORY_DIR, '*.json')
    files = glob.glob(pattern)
    print(f"Found {len(files)} history files in {HISTORY_DIR}")

    races = []
    for f in files:
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
                if 'race_info' in data and 'horses' in data:
                    races.append(data)
        except Exception as e:
            print(f"  WARNING: Failed to load {os.path.basename(f)}: {e}")
    print(f"Loaded {len(races)} valid race files")
    return races


def _extract_finish(entry) -> int:
    if isinstance(entry, dict):
        return entry.get('finish', 0) or 0
    return entry if isinstance(entry, int) else 0


def compute_recent_form_score(last_3: list) -> float:
    weights = [0.5, 0.3, 0.2]
    score = 0.0
    for i, entry in enumerate(last_3[:3]):
        pos = _extract_finish(entry)
        if pos > 0:
            rank_score = max(0, 100 - (pos - 1) * 8)
            score += rank_score * weights[i]
    return round(score, 2)


def compute_jockey_trainer_stats(races: List[Dict]) -> Tuple[Dict, Dict]:
    jockey_stats = defaultdict(lambda: {'starts': 0, 'wins': 0})
    trainer_stats = defaultdict(lambda: {'starts': 0, 'wins': 0})

    for race in races:
        for horse in race.get('horses', []):
            jockey = horse.get('jockey')
            trainer = horse.get('trainer')
            last_3 = horse.get('last_3', [])
            is_win = last_3 and _extract_finish(last_3[0]) == 1

            if jockey:
                jockey_stats[jockey]['starts'] += 1
                if is_win:
                    jockey_stats[jockey]['wins'] += 1
            if trainer:
                trainer_stats[trainer]['starts'] += 1
                if is_win:
                    trainer_stats[trainer]['wins'] += 1

    jockey_win_rates = {
        name: round(stats['wins'] / stats['starts'], 4) if stats['starts'] > 0 else 0.0
        for name, stats in jockey_stats.items()
    }
    trainer_win_rates = {
        name: round(stats['wins'] / stats['starts'], 4) if stats['starts'] > 0 else 0.0
        for name, stats in trainer_stats.items()
    }
    return jockey_win_rates, trainer_win_rates


def compute_rest_days(horse_id: str, race_date: str, horse_history: Dict) -> int:
    if horse_id not in horse_history:
        return 0
    dates = sorted(horse_history[horse_id], reverse=True)
    current = datetime.strptime(race_date, '%Y-%m-%d')
    for d in dates:
        prev = datetime.strptime(d, '%Y-%m-%d')
        if prev < current:
            return (current - prev).days
    return 0


def build_horse_history(races: List[Dict]) -> Dict[str, List[str]]:
    history = defaultdict(list)
    for race in races:
        race_date = race['race_info'].get('race_date')
        if not race_date:
            continue
        for horse in race.get('horses', []):
            horse_code = horse.get('code')
            if horse_code and race_date:
                history[horse_code].append(race_date)
    return history


def transform_race_data(race: Dict, jockey_win_rates: Dict, trainer_win_rates: Dict,
                        horse_history: Dict) -> Tuple[Dict, List[Dict], List[Dict]]:
    info = race['race_info']
    race_id = info.get('race_id')
    race_date = info.get('race_date')

    race_row = {
        'race_id': race_id,
        'race_date': race_date,
        'venue': info.get('venue', ''),
        'race_no': info.get('race_number'),
        'distance': info.get('distance_m'),
        'going': info.get('going'),
        'class_level': info.get('class'),
    }

    runners = []
    horses_seen = []

    for horse in race.get('horses', []):
        horse_code = horse.get('code')
        horse_name = horse.get('name', '')
        horse_no = horse.get('number')

        horses_seen.append({
            'horse_id': horse_code,
            'horse_name': horse_name,
            'country': None,
        })

        last_3 = horse.get('last_3', [])
        jockey = horse.get('jockey', '')
        trainer = horse.get('trainer', '')

        runner = {
            'runner_id': f"{race_id}_{horse_no}",
            'race_id': race_id,
            'horse_id': horse_code,
            'horse_no': horse_no,
            'jockey': jockey,
            'trainer': trainer,
            'actual_weight': horse.get('weight'),
            'draw': horse.get('draw'),
            'past_rating': horse.get('rating'),
            'recent_form_score': compute_recent_form_score(last_3),
            'weight_carried_diff': None,
            'jockey_win_rate': jockey_win_rates.get(jockey, 0.0),
            'trainer_win_rate': trainer_win_rates.get(trainer, 0.0),
            'rest_days': compute_rest_days(horse_code, race_date, horse_history),
            'win_odds': horse.get('odds_win'),
            'finish_position': None,
            'finish_time': horse.get('best_time_sec') if horse.get('best_time_sec', 0) > 0 else None,
        }

        official_result = info.get('official_result', [])
        for res in official_result:
            if res.get('number') == horse_no:
                runner['finish_position'] = res.get('position')
                break

        runners.append(runner)

    return race_row, runners, horses_seen


def upsert_data(supabase: Client, races: List[Dict], runners: List[Dict], horses: List[Dict]):
    print(f"\nUpserting {len(horses)} horses...")
    try:
        result = supabase.table('horses').upsert(horses, on_conflict='horse_id').execute()
        print(f"  OK: {len(result.data)} horses upserted")
    except Exception as e:
        print(f"  ERROR upserting horses: {e}")

    print(f"\nUpserting {len(races)} races...")
    try:
        result = supabase.table('races').upsert(races, on_conflict='race_id').execute()
        print(f"  OK: {len(result.data)} races upserted")
    except Exception as e:
        print(f"  ERROR upserting races: {e}")

    print(f"\nUpserting {len(runners)} race_runners...")
    try:
        result = supabase.table('race_runners').upsert(runners, on_conflict='runner_id').execute()
        print(f"  OK: {len(result.data)} race_runners upserted")
    except Exception as e:
        print(f"  ERROR upserting race_runners: {e}")


def main():
    print("=" * 70)
    print("Bill Benter 賽馬量化分析系統 - 歷史數據特徵工程")
    print("=" * 70)

    try:
        supabase = get_supabase_client()
        print("Supabase client initialized")
    except Exception as e:
        print(f"ERROR: Failed to initialize Supabase client: {e}")
        sys.exit(1)

    print("\nLoading history files...")
    raw_races = load_history_files()
    if not raw_races:
        print("No race data found. Exiting.")
        return

    print("\nComputing jockey/trainer win rates...")
    jockey_win_rates, trainer_win_rates = compute_jockey_trainer_stats(raw_races)
    print(f"  Jockeys: {len(jockey_win_rates)}, Trainers: {len(trainer_win_rates)}")

    print("\nBuilding horse race history...")
    horse_history = build_horse_history(raw_races)
    print(f"  Tracked {len(horse_history)} unique horses")

    all_races = []
    all_runners = []
    all_horses = {}

    print("\nTransforming race data with Benter features...")
    for i, race in enumerate(raw_races, 1):
        if i % 20 == 0:
            print(f"  Processing race {i}/{len(raw_races)}...")

        race_row, runners, horses_seen = transform_race_data(
            race, jockey_win_rates, trainer_win_rates, horse_history
        )
        all_races.append(race_row)
        all_runners.extend(runners)

        for h in horses_seen:
            if h['horse_id'] not in all_horses:
                all_horses[h['horse_id']] = h

    print(f"\nTransformation complete:")
    print(f"  Races: {len(all_races)}")
    print(f"  Runners: {len(all_runners)}")
    print(f"  Unique horses: {len(all_horses)}")

    upsert_data(supabase, all_races, all_runners, list(all_horses.values()))

    print("\n" + "=" * 70)
    print("DONE - All data upserted to Supabase")
    print("=" * 70)


if __name__ == '__main__':
    main()
