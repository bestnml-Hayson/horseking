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
W_FORM = 0.20         # 近況評分
W_RATING = 0.12       # 往績評分 (past_rating)
W_JOCKEY = 0.10       # 騎師勝率
W_TRAINER = 0.09      # 練馬師勝率
W_DRAW = 0.08         # 檔位優勢
W_WEIGHT_CHANGE = 0.05  # 體重變化 (減磅為佳)
W_REST_DAYS = 0.04    # 休養天數 (適中為佳)
W_BEST_TIME = 0.03    # 最佳時間 (越低越快)
W_SEASON_PRIZE = 0.02  # 本季獎金 (越高越好)
W_WEIGHT_CARRIED_DIFF = 0.02  # 負磅差異 (越低越佳)
W_CLASS_STRENGTH = 0.03  # 班次適應 (評分高於班次平均為佳)
W_WEIGHT_DISTANCE = 0.03  # 體重路程交互 (輕磅跑長途為佳)

# 人馬動態契合權重 (Synergy Multiplier)
W_JOCKEY_HORSE_COMBO = 0.08   # 人馬合作效益分
W_JOCKEY_TRACK_PROF = 0.06    # 騎師場地專長分
W_JOCKEY_TRAINER_COMBO = 0.05 # 騎練合作勝率


def get_supabase_client() -> Client:
    """Alias for backward compatibility."""
    return get_supabase()


# =====================================================================
# 1. 特徵標準化
# =====================================================================
def normalize_features(runners: List[Dict], distance: Optional[int] = None) -> List[Dict]:
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
        has_new_gear = any(gear.endswith('1') or gear.endswith('B1') for g in gear.split('/') if g.strip())
        r['gear_change_norm'] = 0.7 if has_new_gear else 0.5

    # best_time: parse "M:SS.cc" format, lower is faster = better
    bt_vals = []
    for r in runners:
        bt = r.get('best_time')
        if bt and isinstance(bt, str):
            try:
                parts = bt.split(':')
                if len(parts) == 2:
                    seconds = int(parts[0]) * 60 + float(parts[1])
                else:
                    seconds = float(bt)
                bt_vals.append(seconds)
                r['_best_time_sec'] = seconds
            except (ValueError, IndexError):
                r['_best_time_sec'] = None
        else:
            r['_best_time_sec'] = None
    if bt_vals:
        bt_min, bt_max = min(bt_vals), max(bt_vals)
        bt_rng = bt_max - bt_min if bt_max != bt_min else 1.0
        for r in runners:
            bt = r.get('_best_time_sec')
            if bt is None:
                r['best_time_norm'] = 0.5
            else:
                r['best_time_norm'] = max(0.0, min(1.0, 1.0 - (bt - bt_min) / bt_rng))

    # season_prize: higher total prize money this season = better horse
    sp_vals = [r.get('season_prize') for r in runners
               if r.get('season_prize') is not None and r.get('season_prize') > 0]
    if sp_vals:
        sp_min, sp_max = min(sp_vals), max(sp_vals)
        sp_rng = sp_max - sp_min if sp_max != sp_min else 1.0
        for r in runners:
            sp = r.get('season_prize')
            if sp is None or sp <= 0:
                r['season_prize_norm'] = 0.3
            else:
                r['season_prize_norm'] = max(0.0, min(1.0, (sp - sp_min) / sp_rng))

    # weight_carried_diff: lower = carrying less weight relative to assignment = better
    wcd_vals = [r.get('weight_carried_diff') for r in runners
                if r.get('weight_carried_diff') is not None]
    if wcd_vals:
        wcd_min, wcd_max = min(wcd_vals), max(wcd_vals)
        wcd_rng = wcd_max - wcd_min if wcd_max != wcd_min else 1.0
        for r in runners:
            wcd = r.get('weight_carried_diff')
            if wcd is None:
                r['weight_carried_diff_norm'] = 0.5
            else:
                r['weight_carried_diff_norm'] = max(0.0, min(1.0, 1.0 - (wcd - wcd_min) / wcd_rng))

    # class_strength: horse official_rating vs race average → higher = classing above rivals
    ratings = [r.get('official_rating') for r in runners if r.get('official_rating') is not None]
    if ratings:
        avg_rating = sum(ratings) / len(ratings)
        cs_vals = []
        for r in runners:
            rating = r.get('official_rating')
            if rating is not None:
                cs = rating - avg_rating
                r['_class_strength'] = cs
                cs_vals.append(cs)
            else:
                r['_class_strength'] = 0.0
                cs_vals.append(0.0)
        cs_min, cs_max = min(cs_vals), max(cs_vals)
        cs_rng = cs_max - cs_min if cs_max != cs_min else 1.0
        for r in runners:
            cs = r.get('_class_strength', 0.0)
            r['class_strength_norm'] = max(0.0, min(1.0, (cs - cs_min) / cs_rng))
    else:
        for r in runners:
            r['class_strength_norm'] = 0.5

    # weight_distance: declared_weight × distance interaction → lighter over distance = better
    if distance and distance > 0:
        wd_vals = []
        for r in runners:
            dw = r.get('declared_weight')
            if dw is not None and dw > 0:
                wd = dw * distance / 100000.0
                r['_weight_distance'] = wd
                wd_vals.append(wd)
            else:
                r['_weight_distance'] = None
        if wd_vals:
            wd_min, wd_max = min(wd_vals), max(wd_vals)
            wd_rng = wd_max - wd_min if wd_max != wd_min else 1.0
            for r in runners:
                wd = r.get('_weight_distance')
                if wd is None:
                    r['weight_distance_norm'] = 0.5
                else:
                    # Lower weight-distance burden = better
                    r['weight_distance_norm'] = max(0.0, min(1.0, 1.0 - (wd - wd_min) / wd_rng))
    else:
        for r in runners:
            r['weight_distance_norm'] = 0.5

    return runners


# =====================================================================
# 1b. 人馬動態契合特徵 (Jockey-Horse Synergy Features)
# =====================================================================
def fetch_historical_results(supabase: Client, months: int = 6) -> List[Dict]:
    """從 race_results 讀取近 N 個月的歷史賽果"""
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(days=months * 30)).strftime('%Y-%m-%d')

    all_results = []
    offset = 0
    batch_size = 1000

    while True:
        try:
            resp = supabase.table('race_results').select(
                'race_id,race_date,venue,horse_no,horse_name,jockey,trainer,'
                'finish_position,win_odds'
            ).gte('race_date', cutoff).range(offset, offset + batch_size - 1).execute()
            if not resp.data:
                break
            all_results.extend(resp.data)
            if len(resp.data) < batch_size:
                break
            offset += batch_size
        except Exception as e:
            print(f"  WARNING: fetch_historical_results error: {e}")
            break

    print(f"  Fetched {len(all_results)} historical results (last {months} months)")
    return all_results


def build_synergy_matrices(history: List[Dict]) -> Tuple[Dict, Dict, Dict]:
    """
    建立三個契合矩陣：
    1. jockey_horse_combo: (jockey, horse_name) → {starts, wins, places}
    2. jockey_venue_stats: (jockey, venue) → {starts, wins, places}
    3. jockey_trainer_combo: (jockey, trainer) → {starts, wins, places, roi_sum}
    """
    jh = defaultdict(lambda: {'starts': 0, 'wins': 0, 'places': 0})
    jv = defaultdict(lambda: {'starts': 0, 'wins': 0, 'places': 0})
    jt = defaultdict(lambda: {'starts': 0, 'wins': 0, 'places': 0, 'roi_sum': 0.0})

    for r in history:
        jockey = (r.get('jockey') or '').strip()
        trainer = (r.get('trainer') or '').strip()
        horse = (r.get('horse_name') or '').strip()
        venue = (r.get('venue') or '').strip()
        pos = r.get('finish_position')
        odds = r.get('win_odds')

        if not jockey:
            continue

        is_win = pos is not None and pos == 1
        is_place = pos is not None and pos <= 3

        if horse:
            key = (jockey, horse)
            jh[key]['starts'] += 1
            if is_win:
                jh[key]['wins'] += 1
            if is_place:
                jh[key]['places'] += 1

        if venue:
            key = (jockey, venue)
            jv[key]['starts'] += 1
            if is_win:
                jv[key]['wins'] += 1
            if is_place:
                jv[key]['places'] += 1

        if trainer:
            key = (jockey, trainer)
            jt[key]['starts'] += 1
            if is_win:
                jt[key]['wins'] += 1
            if is_place:
                jt[key]['places'] += 1
            if odds and odds > 1.0:
                jt[key]['roi_sum'] += (odds - 1.0) if is_win else -1.0

    return dict(jh), dict(jv), dict(jt)


def compute_synergy_features(
    runners: List[Dict],
    jh_combo: Dict,
    jv_stats: Dict,
    jt_combo: Dict,
    venue: str | None = None,
) -> List[Dict]:
    """
    為每匹馬計算三個契合特徵並標準化到 [0, 1]：
    1. jockey_horse_combo_score: 人馬合作勝率 + 上名率
    2. jockey_track_proficiency: 騎師在指定場地的勝率 + 上名率
    3. jockey_trainer_combo_win_rate: 騎練合作勝率 + ROI
    """
    if not runners:
        return runners

    for r in runners:
        jockey = (r.get('jockey') or '').strip()
        trainer = (r.get('trainer') or '').strip()
        horse = (r.get('horse_name') or '').strip()
        v = venue or ''

        # 1. jockey_horse_combo_score
        jh_key = (jockey, horse)
        jh_data = jh_combo.get(jh_key)
        if jh_data and jh_data['starts'] >= 2:
            win_rate = jh_data['wins'] / jh_data['starts']
            place_rate = jh_data['places'] / jh_data['starts']
            r['_jh_combo_raw'] = 0.6 * win_rate + 0.4 * place_rate
        else:
            r['_jh_combo_raw'] = None

        # 2. jockey_track_proficiency
        jv_key = (jockey, v)
        jv_data = jv_stats.get(jv_key)
        if jv_data and jv_data['starts'] >= 5:
            win_rate = jv_data['wins'] / jv_data['starts']
            place_rate = jv_data['places'] / jv_data['starts']
            r['_jv_prof_raw'] = 0.6 * win_rate + 0.4 * place_rate
        else:
            r['_jv_prof_raw'] = None

        # 3. jockey_trainer_combo_win_rate
        jt_key = (jockey, trainer)
        jt_data = jt_combo.get(jt_key)
        if jt_data and jt_data['starts'] >= 3:
            win_rate = jt_data['wins'] / jt_data['starts']
            place_rate = jt_data['places'] / jt_data['starts']
            roi = jt_data['roi_sum'] / jt_data['starts'] if jt_data['starts'] > 0 else 0
            r['_jt_combo_raw'] = 0.5 * win_rate + 0.3 * place_rate + 0.2 * max(0, min(1, (roi + 1) / 2))
        else:
            r['_jt_combo_raw'] = None

    # Min-Max normalize each feature to [0, 1]
    for feat_key, norm_key in [('_jh_combo_raw', 'jockey_horse_combo_norm'),
                                ('_jv_prof_raw', 'jockey_track_prof_norm'),
                                ('_jt_combo_raw', 'jockey_trainer_combo_norm')]:
        vals = [r.get(feat_key) for r in runners if r.get(feat_key) is not None]
        if vals:
            mn, mx = min(vals), max(vals)
            rng = mx - mn if mx != mn else 1.0
            for r in runners:
                v = r.get(feat_key)
                if v is None:
                    r[norm_key] = 0.4
                else:
                    r[norm_key] = max(0.0, min(1.0, (v - mn) / rng))
        else:
            for r in runners:
                r[norm_key] = 0.4

    return runners


# =====================================================================
# 2. 基礎評分計算 (Linear Score + Synergy Multiplier)
# =====================================================================
def compute_raw_score(runner: Dict) -> float:
    """
    加權線性綜合評分 + 人馬動態契合乘數 (Synergy Multiplier)
    Score_final = Score_base × (1 + w1*Combo + w2*TrackProf + w3*JTCombo)
    """
    base_score = (
        W_FORM          * runner.get('recent_form_score_norm', 0.5) +
        W_RATING        * runner.get('past_rating_norm', 0.5) +
        W_JOCKEY        * runner.get('jockey_win_rate_norm', 0.5) +
        W_TRAINER       * runner.get('trainer_win_rate_norm', 0.5) +
        W_DRAW          * runner.get('draw_norm', 0.5) +
        W_WEIGHT_CHANGE * runner.get('weight_change_norm', 0.5) +
        W_REST_DAYS     * runner.get('rest_days_norm', 0.5) +
        W_BEST_TIME     * runner.get('best_time_norm', 0.5) +
        W_SEASON_PRIZE  * runner.get('season_prize_norm', 0.5) +
        W_WEIGHT_CARRIED_DIFF * runner.get('weight_carried_diff_norm', 0.5) +
        W_CLASS_STRENGTH * runner.get('class_strength_norm', 0.5) +
        W_WEIGHT_DISTANCE * runner.get('weight_distance_norm', 0.5) +
        0.02            * runner.get('gear_change_norm', 0.5)
    )

    synergy_multiplier = 1.0 + (
        W_JOCKEY_HORSE_COMBO   * runner.get('jockey_horse_combo_norm', 0.4) +
        W_JOCKEY_TRACK_PROF    * runner.get('jockey_track_prof_norm', 0.4) +
        W_JOCKEY_TRAINER_COMBO * runner.get('jockey_trainer_combo_norm', 0.4)
    )

    return base_score * synergy_multiplier


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
    缺少賠率的馬匹使用有效賠率的平均倒數作為 fallback
    """
    if not odds:
        return []

    valid_recips = [1.0 / o for o in odds if o is not None and o > 1.0]
    avg_recip = sum(valid_recips) / len(valid_recips) if valid_recips else 0.0

    reciprocals = []
    for o in odds:
        if o is not None and o > 1.0:
            reciprocals.append(1.0 / o)
        elif avg_recip > 0:
            reciprocals.append(avg_recip)
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
def analyze_race(runners: List[Dict], distance: Optional[int] = None,
                 pre_race: bool = False,
                 synergy: Optional[Tuple[Dict, Dict, Dict]] = None,
                 venue: Optional[str] = None) -> List[Dict]:
    """
    兩階段完整計算流程：
      階段一：normalize → synergy features → raw_score (× synergy multiplier) → softmax → P_model
      階段二：market_implied → benter_fusion → P_final → EV → Kelly
    """
    runners = normalize_features(runners, distance=distance)

    if synergy:
        jh_combo, jv_stats, jt_combo = synergy
        runners = compute_synergy_features(runners, jh_combo, jv_stats, jt_combo, venue=venue)

    raw_scores = [compute_raw_score(r) for r in runners]
    p_models = softmax_probabilities(raw_scores)

    if pre_race:
        # Pre-race mode: P_model only, no market data
        results = []
        for i, r in enumerate(runners):
            p_model = p_models[i]
            results.append({
                'runner_id': r.get('runner_id'),
                'race_id': r.get('race_id'),
                'horse_no': r.get('horse_no'),
                'horse_id': r.get('horse_id'),
                'raw_model_prob': round(p_model, 5),
                'market_implied_prob': None,
                'final_prob': None,
                'expected_value': None,
                'kelly_fraction': None,
                'is_value_bet': False,
                'win_odds': r.get('win_odds'),
            })
        results.sort(key=lambda x: x['raw_model_prob'], reverse=True)
        return results

    odds_list = [r.get('win_odds') for r in runners]
    p_markets = market_implied_probabilities(odds_list)

    results = []
    for i, r in enumerate(runners):
        p_model = p_models[i]
        win_odds = r.get('win_odds')
        odds_available = win_odds is not None and win_odds > 1.0

        p_market = p_markets[i]
        p_final = benter_fusion(p_model, p_market)

        if odds_available:
            ev = compute_ev(p_final, win_odds)
            kelly = compute_kelly(p_final, win_odds)
        else:
            ev = None
            kelly = None

        is_value_bet = ev is not None and ev > 0.15

        results.append({
            'runner_id': r.get('runner_id'),
            'race_id': r.get('race_id'),
            'horse_no': r.get('horse_no'),
            'horse_id': r.get('horse_id'),
            'raw_model_prob': round(p_model, 5),
            'market_implied_prob': round(p_market, 5),
            'final_prob': round(p_final, 5),
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
                 dry_run: bool = False, pre_race: bool = False) -> List[Dict]:
    """主分析流程：讀取 → 計算 synergies → 計算 → (寫入) Supabase"""
    mode_str = " [PRE-RACE: P_model only]" if pre_race else ""
    print(f"Fetching race_runners from Supabase{mode_str}...")
    races_data = fetch_races_with_runners(supabase, race_ids)
    print(f"  Found {len(races_data)} races")

    # Fetch race metadata (distance + venue) from races table
    race_distances = {}
    race_venues = {}
    all_race_ids = list(races_data.keys())
    if all_race_ids:
        batch_size = 500
        for i in range(0, len(all_race_ids), batch_size):
            batch_ids = all_race_ids[i:i + batch_size]
            try:
                resp = supabase.table('races').select('race_id,distance,venue').in_('race_id', batch_ids).execute()
                for row in (resp.data or []):
                    race_distances[row['race_id']] = row.get('distance')
                    race_venues[row['race_id']] = row.get('venue')
            except Exception as e:
                print(f"  WARNING: could not fetch race metadata: {e}")
        print(f"  Fetched metadata for {len(race_distances)} races")

    # Fetch horse names from horses table (needed for jockey-horse combo lookup)
    horse_name_map = {}
    all_horse_ids = set()
    for runners in races_data.values():
        for r in runners:
            hid = r.get('horse_id')
            if hid:
                all_horse_ids.add(hid)
    if all_horse_ids:
        horse_id_list = list(all_horse_ids)
        batch_size = 500
        for i in range(0, len(horse_id_list), batch_size):
            batch_ids = horse_id_list[i:i + batch_size]
            try:
                resp = supabase.table('horses').select('horse_id,horse_name').in_('horse_id', batch_ids).execute()
                for row in (resp.data or []):
                    horse_name_map[row['horse_id']] = row.get('horse_name', '')
            except Exception as e:
                print(f"  WARNING: could not fetch horse names: {e}")
        print(f"  Fetched {len(horse_name_map)} horse names")

    # Inject horse_name into each runner
    for runners in races_data.values():
        for r in runners:
            hid = r.get('horse_id')
            if hid and hid in horse_name_map:
                r['horse_name'] = horse_name_map[hid]

    # Build synergy matrices from historical results
    print("\nBuilding Jockey-Horse Synergy matrices...")
    history = fetch_historical_results(supabase, months=6)
    jh_combo, jv_stats, jt_combo = build_synergy_matrices(history)
    synergy = (jh_combo, jv_stats, jt_combo)
    print(f"  Jockey-Horse combos: {len(jh_combo)}")
    print(f"  Jockey-Venue stats:  {len(jv_stats)}")
    print(f"  Jockey-Trainer combos: {len(jt_combo)}")

    all_predictions = []
    for race_id, runners in races_data.items():
        distance = race_distances.get(race_id)
        venue = race_venues.get(race_id)
        predictions = analyze_race(runners, distance=distance, pre_race=pre_race,
                                   synergy=synergy, venue=venue)
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
