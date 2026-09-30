#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bill Benter 賽馬量化分析核心模型
Softmax Multinomial Logit + Market Odds Fusion + Kelly Criterion
"""

import json
import math
import os
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(__file__))
from common import get_supabase, batch_upsert

try:
    from supabase import create_client, Client
except ImportError:
    print("ERROR: supabase-py not installed. Run: pip install supabase")
    sys.exit(1)


# =====================================================================
# Benter 兩階段模型超參數
# 階段一（純實力 P_model）：完全不參考賠率，僅根據馬匹基礎能力
#   （往績走勢、檔位、騎練、配備變動、久休天數、體重變化等）算出獨立勝率
# 階段二（融合勝率 P_final）：結合開盤後的賠率算出 P_market，
#   透過對數加權融合生成 P_final
# =====================================================================
ALPHA = 0.25          # P_model 在融合中的權重 (1-ALPHA = P_market 權重)
FRACTIONAL_KELLY = 0.25  # 1/4 Kelly 降低方差
TEMPERATURE = 1.0     # Softmax 溫度參數

# 評分維度權重 (總和 = 1.0)
W_FORM = 0.25         # 近況評分
W_RATING = 0.18       # 往績評分 (past_rating)
W_JOCKEY = 0.17       # 騎師勝率
W_TRAINER = 0.13      # 練馬師勝率
W_DRAW = 0.12         # 檔位優勢
W_WEIGHT_CHANGE = 0.08  # 體重變化 (減磅為佳)
W_REST_DAYS = 0.07    # 休養天數 (適中為佳)


def get_supabase_client() -> Client:
    """Alias for backward compatibility."""
    return get_supabase()


# =====================================================================
# 1. 特徵標準化
# =====================================================================
def normalize_features(runners: List[Dict]) -> List[Dict]:
    """Min-Max 標準化各特徵到 [0, 1] 區間"""
    if not runners:
        return runners

    for r in runners:
        if r.get('official_rating') is not None:
            r['past_rating'] = r['official_rating']

    features = ['recent_form_score', 'past_rating', 'jockey_win_rate',
                'trainer_win_rate', 'draw']

    for feat in features:
        vals = [r.get(feat) for r in runners if r.get(feat) is not None]
        if not vals:
            continue
        mn, mx = min(vals), max(vals)
        rng = mx - mn if mx != mn else 1.0

        for r in runners:
            v = r.get(feat)
            if v is None:
                r[f'{feat}_norm'] = 0.5
                continue
            normed = (v - mn) / rng
            if feat == 'draw':
                n = len(runners)
                mid = (n + 1) / 2.0
                draw_pos = v
                draw_norm = 1.0 - abs(draw_pos - mid) / mid
                r[f'{feat}_norm'] = max(0.0, min(1.0, draw_norm))
            else:
                r[f'{feat}_norm'] = max(0.0, min(1.0, normed))

    # weight_change: negative (weight reduction) is better
    wc_vals = [r.get('weight_change') for r in runners if r.get('weight_change') is not None]
    if wc_vals:
        wc_min, wc_max = min(wc_vals), max(wc_vals)
        wc_rng = wc_max - wc_min if wc_max != wc_min else 1.0
        for r in runners:
            wc = r.get('weight_change')
            if wc is None:
                r['weight_change_norm'] = 0.5
            else:
                # Invert: lower weight_change = higher score
                r['weight_change_norm'] = max(0.0, min(1.0, 1.0 - (wc - wc_min) / wc_rng))

    # rest_days: moderate rest (14-45 days) is optimal, too short or too long is worse
    rd_vals = [r.get('rest_days') for r in runners if r.get('rest_days') is not None]
    if rd_vals:
        for r in runners:
            rd = r.get('rest_days')
            if rd is None:
                r['rest_days_norm'] = 0.5
            else:
                # Bell curve: peak at ~30 days, decline on both sides
                optimal = 30
                deviation = abs(rd - optimal)
                r['rest_days_norm'] = max(0.0, min(1.0, 1.0 - deviation / 90.0))

    # gear_change: binary - new gear (e.g., B1 first time) may indicate improvement
    for r in runners:
        gear = r.get('gear', '') or ''
        # Gear codes ending in 1 often indicate first-time use (B1, TT1, etc.)
        has_new_gear = any(gear.endswith('1') or gear.endswith('B1') for g in gear.split('/') if g.strip())
        r['gear_change_norm'] = 0.7 if has_new_gear else 0.5

    return runners


# =====================================================================
# 2. 基礎評分計算 (Linear Score)
# =====================================================================
def compute_raw_score(runner: Dict) -> float:
    """加權線性綜合評分"""
    score = (
        W_FORM          * runner.get('recent_form_score_norm', 0.5) +
        W_RATING        * runner.get('past_rating_norm', 0.5) +
        W_JOCKEY        * runner.get('jockey_win_rate_norm', 0.5) +
        W_TRAINER       * runner.get('trainer_win_rate_norm', 0.5) +
        W_DRAW          * runner.get('draw_norm', 0.5) +
        W_WEIGHT_CHANGE * runner.get('weight_change_norm', 0.5) +
        W_REST_DAYS     * runner.get('rest_days_norm', 0.5) +
        0.02            * runner.get('gear_change_norm', 0.5)
    )
    return score


# =====================================================================
# 3. Softmax 勝率計算 (Multinomial Logit)
# =====================================================================
def softmax_probabilities(scores: List[float], temperature: float = TEMPERATURE) -> List[float]:
    """
    Softmax: P_i = exp(score_i / T) / sum(exp(score_j / T))
    減去 max 避免 overflow
    """
    if not scores:
        return []

    scaled = [s / temperature for s in scores]
    max_s = max(scaled)
    exps = [math.exp(s - max_s) for s in scaled]
    total = sum(exps)

    if total == 0:
        n = len(scores)
        return [1.0 / n] * n

    return [e / total for e in exps]


# =====================================================================
# 4. 市場隱含勝率 (Odds Normalization)
# =====================================================================
def market_implied_probabilities(odds: List[float]) -> List[float]:
    """
    P_market_i = (1 / O_i) / sum(1 / O_j)
    去除過round (overround) 使總和 = 1
    """
    if not odds:
        return []

    reciprocals = []
    for o in odds:
        if o is not None and o > 1.0:
            reciprocals.append(1.0 / o)
        else:
            reciprocals.append(0.0)

    total = sum(reciprocals)
    if total == 0:
        n = len(odds)
        return [1.0 / n] * n

    return [r / total for r in reciprocals]


# =====================================================================
# 5. Benter 對數加權融合
# =====================================================================
def benter_fusion(p_model: float, p_market: float, alpha: float = ALPHA) -> float:
    """
    Benter 經典對數加權融合:
    P_final = exp(alpha * ln(P_model) + (1-alpha) * ln(P_market))

    alpha = 0.25 → 25% 模型, 75% 市場
    加 floor 避免 log(0)
    """
    eps = 1e-10
    p_m = max(p_model, eps)
    p_k = max(p_market, eps)

    log_blend = alpha * math.log(p_m) + (1 - alpha) * math.log(p_k)
    p_final = math.exp(log_blend)
    return max(0.0, min(1.0, p_final))


# =====================================================================
# 6. 期望值 (EV) 計算
# =====================================================================
def compute_ev(p_final: float, odds_win: float) -> float:
    """EV = P_final * O_win - 1 (期望回報率)"""
    if odds_win is None or odds_win <= 1.0:
        return 0.0
    return round(p_final * odds_win - 1.0, 4)


# =====================================================================
# 7. Kelly 凱利公式
# =====================================================================
def compute_kelly(p_final: float, odds_win: float, fraction: float = FRACTIONAL_KELLY) -> float:
    """
    f* = (P_final * O_win - 1) / (O_win - 1)
    若 EV <= 0 → f* = 0
    套用 Fractional Kelly (預設 1/4)
    """
    if odds_win is None or odds_win <= 1.0:
        return 0.0

    ev = p_final * odds_win - 1.0
    if ev <= 0:
        return 0.0

    full_kelly = (p_final * odds_win - 1.0) / (odds_win - 1.0)
    return round(max(0.0, full_kelly * fraction), 5)


# =====================================================================
# 8. 單場賽事完整計算流程
# =====================================================================
def analyze_race(runners: List[Dict]) -> List[Dict]:
    """
    兩階段完整計算流程：
      階段一：normalize → raw_score → softmax → P_model（純實力，不含賠率）
      階段二：market_implied → benter_fusion → P_final → EV → Kelly
    """
    runners = normalize_features(runners)

    raw_scores = [compute_raw_score(r) for r in runners]
    p_models = softmax_probabilities(raw_scores)

    odds_list = [r.get('win_odds') for r in runners]
    p_markets = market_implied_probabilities(odds_list)

    results = []
    for i, r in enumerate(runners):
        p_model = p_models[i]
        win_odds = r.get('win_odds')
        odds_available = win_odds is not None and win_odds > 1.0

        if odds_available:
            p_market = p_markets[i]
            p_final = benter_fusion(p_model, p_market)
            ev = compute_ev(p_final, win_odds)
            kelly = compute_kelly(p_final, win_odds)
        else:
            p_market = None
            p_final = None
            ev = None
            kelly = None

        is_value_bet = ev is not None and ev > 0.15

        results.append({
            'runner_id': r.get('runner_id'),
            'race_id': r.get('race_id'),
            'horse_no': r.get('horse_no'),
            'horse_id': r.get('horse_id'),
            'raw_model_prob': round(p_model, 5),
            'market_implied_prob': round(p_market, 5) if p_market is not None else None,
            'final_prob': round(p_final, 5) if p_final is not None else None,
            'expected_value': ev,
            'kelly_fraction': kelly,
            'is_value_bet': is_value_bet,
            'win_odds': r.get('win_odds'),
        })

    results.sort(key=lambda x: x['expected_value'] if x['expected_value'] is not None else -999, reverse=True)
    return results


# =====================================================================
# 9. 從 Supabase 讀取數據並批量分析
# =====================================================================
def fetch_races_with_runners(supabase: Client, race_ids: Optional[List[str]] = None) -> Dict[str, List[Dict]]:
    """從 Supabase 讀取 race_runners 並按 race_id 分組（分頁讀取全部）"""
    grouped = defaultdict(list)
    batch_size = 1000
    offset = 0

    while True:
        query = supabase.table('race_runners').select('*').range(offset, offset + batch_size - 1)
        if race_ids:
            query = query.in_('race_id', race_ids)
        response = query.execute()

        if not response.data:
            break

        for row in response.data:
            grouped[row['race_id']].append(row)

        if len(response.data) < batch_size:
            break
        offset += batch_size

    return dict(grouped)


def run_analysis(supabase: Client, race_ids: Optional[List[str]] = None,
                 dry_run: bool = False) -> List[Dict]:
    """主分析流程：讀取 → 計算 → (寫入) Supabase"""
    print("Fetching race_runners from Supabase...")
    races_data = fetch_races_with_runners(supabase, race_ids)
    print(f"  Found {len(races_data)} races")

    all_predictions = []
    for race_id, runners in races_data.items():
        predictions = analyze_race(runners)
        all_predictions.extend(predictions)

    print(f"  Computed predictions for {len(all_predictions)} runners")

    value_bets = [p for p in all_predictions if p['is_value_bet']]
    print(f"  Value bets (EV > 0.15): {len(value_bets)}")

    if dry_run:
        print("\n[DRY RUN] Skipping Supabase write.")
        return all_predictions

    print("\nWriting predictions to model_predictions table...")
    batch_size = 100
    for i in range(0, len(all_predictions), batch_size):
        batch = all_predictions[i:i + batch_size]
        upsert_rows = []
        for p in batch:
            upsert_rows.append({
                'race_id': p['race_id'],
                'runner_id': p['runner_id'],
                'raw_model_prob': p['raw_model_prob'],
                'market_implied_prob': p['market_implied_prob'],
                'final_prob': p['final_prob'],
                'expected_value': p['expected_value'],
                'kelly_fraction': p['kelly_fraction'],
            })

        try:
            supabase.table('model_predictions').upsert(
                upsert_rows, on_conflict='race_id,runner_id'
            ).execute()
            print(f"  Batch {i // batch_size + 1}: {len(upsert_rows)} rows upserted")
        except Exception as e:
            print(f"  ERROR batch {i // batch_size + 1}: {e}")

    print("\nDone. All predictions written to Supabase.")
    return all_predictions


# =====================================================================
# 10. 本地測試模式 (不連接 Supabase)
# =====================================================================
def run_local_test():
    """從本地 JSON 歷史檔案測試模型"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from process_horse_data import (
        load_history_files, compute_jockey_trainer_stats,
        build_horse_history, transform_race_data
    )

    print("=" * 70)
    print("Benter Model - Local Test Mode")
    print("=" * 70)

    raw_races = load_history_files()
    jockey_wr, trainer_wr = compute_jockey_trainer_stats(raw_races)
    horse_history = build_horse_history(raw_races)

    all_runners_by_race = defaultdict(list)

    for race in raw_races:
        _, runners, _ = transform_race_data(race, jockey_wr, trainer_wr, horse_history)
        race_id = race['race_info']['race_id']
        all_runners_by_race[race_id] = runners

    print(f"\nLoaded {len(all_runners_by_race)} races for analysis\n")

    total_value_bets = 0
    sample_shown = 0

    for race_id, runners in sorted(all_runners_by_race.items()):
        predictions = analyze_race(runners)
        value_bets = [p for p in predictions if p['is_value_bet']]
        total_value_bets += len(value_bets)

        if sample_shown < 3:
            print(f"--- {race_id} ---")
            print(f"  {'No':>3} {'P_model':>8} {'P_market':>9} {'P_final':>8} {'Odds':>6} {'EV':>7} {'Kelly':>7} {'Value?'}")
            for p in predictions[:5]:
                tag = " *** VALUE" if p['is_value_bet'] else ""
                pm = f"{p['market_implied_prob']:>9.4f}" if p['market_implied_prob'] is not None else "       N/A"
                pf = f"{p['final_prob']:>8.4f}" if p['final_prob'] is not None else "     N/A"
                ev = f"{p['expected_value']:>+7.4f}" if p['expected_value'] is not None else "    N/A"
                kl = f"{p['kelly_fraction']:>7.4f}" if p['kelly_fraction'] is not None else "    N/A"
                odds = f"{p['win_odds']:>6.1f}" if p['win_odds'] is not None else "   N/A"
                print(f"  {p['horse_no']:>3} {p['raw_model_prob']:>8.4f} "
                      f"{pm} {pf} "
                      f"{odds} {ev} "
                      f"{kl}{tag}")
            print()
            sample_shown += 1

    print("=" * 70)
    print(f"SUMMARY")
    print(f"  Total races analyzed:  {len(all_runners_by_race)}")
    print(f"  Total value bets:      {total_value_bets}")
    print(f"  Model alpha (weight):  {ALPHA}")
    print(f"  Fractional Kelly:      {FRACTIONAL_KELLY}")
    print("=" * 70)


# =====================================================================
# Main
# =====================================================================
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'local'

    if mode == 'local':
        run_local_test()

    elif mode == 'supabase':
        try:
            supabase = get_supabase_client()
            print("Supabase client connected")
        except Exception as e:
            print(f"ERROR: {e}")
            sys.exit(1)

        race_ids = None
        if len(sys.argv) > 2:
            race_ids = sys.argv[2].split(',')
            print(f"Analyzing specific races: {race_ids}")

        run_analysis(supabase, race_ids=race_ids, dry_run=False)

    elif mode == 'dry':
        try:
            supabase = get_supabase_client()
        except Exception as e:
            print(f"ERROR: {e}")
            sys.exit(1)

        run_analysis(supabase, dry_run=True)

    else:
        print("Usage: python benter_model.py [local|supabase|dry]")
        print("  local    - Test with local JSON files (no Supabase needed)")
        print("  supabase - Read from & write to Supabase")
        print("  dry      - Read from Supabase, compute, but don't write")
        sys.exit(1)


if __name__ == '__main__':
    main()
