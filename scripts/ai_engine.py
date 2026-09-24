#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
賽馬 AI 評分引擎 & 自動分析模塊
支援 6 維度評分：近績走勢、評分實力、最佳時間、檔位優勢、體重狀態、賠率信心
"""
import json
import os
import random
from datetime import datetime, timedelta
from copy import deepcopy

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(BASE_DIR, 'data', 'race_data.json')
ANALYSIS_FILE = os.path.join(BASE_DIR, 'data', 'latest_analysis.json')


def load_race_data():
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_analysis(analysis):
    with open(ANALYSIS_FILE, 'w', encoding='utf-8') as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)


def min_max(values, reverse=False):
    if not values:
        return {}
    mn, mx = min(values), max(values)
    if mn == mx:
        return {v: 100.0 for v in values}
    if reverse:
        return {v: round(100 * (1 - (v - mn) / (mx - mn)), 2) for v in values}
    return {v: round(100 * (v - mn) / (mx - mn), 2) for v in values}


def analyze_last3(last3):
    """近績評分：越低名次越好（1=冠軍最好），最近一場權重較高"""
    if not last3:
        return 0
    weights = [0.5, 0.3, 0.2]
    weighted_sum = 0
    for i in range(min(len(last3), 3)):
        rank = last3[i]
        rank_score = max(0, 100 - (rank - 1) * 8)
        weighted_sum += rank_score * weights[i]
    return round(weighted_sum, 2)


def analyze_pace(race_info, horses):
    """步速預測 & 爭放分析"""
    distance = race_info.get('distance_m', 1000)
    total_draws = race_info.get('num_horses', len(horses))

    pace_type = '中步速'
    if distance <= 1200:
        pace_type = '快步速'

    leaders = []
    for h in horses:
        draw = h.get('draw', 0)
        last3 = h.get('last_3', [])
        front_run_score = 0
        if draw and draw <= 3:
            front_run_score += 40
        if last3 and last3 and last3[0] <= 3:
            front_run_score += 30
        if last3 and len(last3) >= 2 and last3[1] <= 3:
            front_run_score += 20
        bt = h.get('best_time_sec', 999)
        if bt and bt <= 58.0:
            front_run_score += 10
        leaders.append({'number': h['number'], 'code': h['code'], 'name': h.get('name', ''),
                        'score': front_run_score, 'draw': draw})

    leaders.sort(key=lambda x: x['score'], reverse=True)
    front_leaders = [x for x in leaders if x['score'] >= 60][:3]

    beneficiaries = []
    for h in horses:
        benefit_score = 0
        draw = h.get('draw', 0)
        if draw and 3 <= draw <= 5:
            benefit_score += 40
        bt = h.get('best_time_sec', 999)
        if bt and bt <= 58.0:
            benefit_score += 30
        rating = h.get('rating', 0)
        if rating and rating >= 128:
            benefit_score += 20
        if benefit_score >= 50:
            beneficiaries.append({'number': h['number'], 'code': h['code'],
                                  'name': h.get('name', ''), 'score': benefit_score})
    beneficiaries.sort(key=lambda x: x['score'], reverse=True)

    return {
        'pace_type': pace_type,
        'pace_reason': f"{distance}米短途賽，{len(front_leaders)}匹前列馬爭放頭，預計步速偏急",
        'front_leaders': front_leaders,
        'beneficiaries': beneficiaries
    }


def score_horses(horses, race_info):
    """6 維度 AI 評分模型"""
    last3_scores = [analyze_last3(h.get('last_3', [])) for h in horses]
    ratings = [h.get('rating', 0) for h in horses]
    best_times = [h.get('best_time_sec', 999) for h in horses]
    draws = [h.get('draw', 100) for h in horses]
    weights = [h.get('weight', 0) for h in horses]
    odds_list = [h.get('odds_win', 999) for h in horses]

    rating_map = min_max(ratings)
    time_map = min_max(best_times, reverse=True)
    draw_map = min_max(draws, reverse=True)
    weight_map = min_max(weights)

    inv_odds = [100 / o if o > 0 else 0 for o in odds_list]
    odds_map = min_max(inv_odds)

    scored = []
    for idx, h in enumerate(horses):
        s_last3 = last3_scores[idx]
        s_rating = rating_map[h['rating']]
        s_time = time_map[h['best_time_sec']]
        s_draw = draw_map[h['draw']]
        s_weight = weight_map[h['weight']]
        s_odds = odds_map.get(100 / h['odds_win'] if h['odds_win'] > 0 else 0, 0)

        total = round(
            s_last3 * 0.30 +
            s_rating * 0.20 +
            s_time * 0.15 +
            s_draw * 0.15 +
            s_weight * 0.10 +
            s_odds * 0.10, 2
        )

        scored.append({
            'number': h['number'],
            'code': h['code'],
            'name': h.get('name', ''),
            'jockey': h.get('jockey', ''),
            'trainer': h.get('trainer', ''),
            'draw': h['draw'],
            'rating': h['rating'],
            'weight': h['weight'],
            'last_3': h.get('last_3', []),
            'best_time_sec': h['best_time_sec'],
            'odds_win': h['odds_win'],
            'scores': {
                'last3': s_last3,
                'rating': s_rating,
                'time': s_time,
                'draw': s_draw,
                'weight': s_weight,
                'odds': s_odds,
                'total': total
            },
            'value_ratio': round(total / (h['odds_win'] if h['odds_win'] > 0 else 1) * 10, 2)
        })

    scored.sort(key=lambda x: x['scores']['total'], reverse=True)
    for i, s in enumerate(scored):
        s['ai_rank'] = i + 1
    return scored


def generate_betting_suggestion(top4, all_horses, race_info):
    """投注策略 & 值博率建議"""
    main_pick = top4[0]
    second_pick = top4[1]
    hot_horses = sorted(all_horses, key=lambda x: x['odds_win'])
    hottest = hot_horses[0]

    hot_concerns = []
    if hottest.get('code') != main_pick.get('code'):
        last3 = hottest.get('last_3', [])
        good_races = sum(1 for r in last3 if r <= 3)
        if good_races < 2:
            hot_concerns.append(f"近績三仗僅 {good_races} 次入三甲，狀態不穩")
        if hottest.get('draw', 0) > 6:
            hot_concerns.append(f"檔位 {hottest['draw']} 偏外，短途賽疊罰較重")
        if hottest.get('weight', 0) < 1100:
            hot_concerns.append(f"體重 {hottest['weight']} 磅偏輕，質素存疑")
        if hottest.get('best_time_sec', 999) > 58.0:
            hot_concerns.append(f"最佳時間 {hottest['best_time_sec']} 秒僅屬中游，爆頭難度高")

    if not hot_concerns:
        hot_concerns.append("大熱門整體條件不俗，但值博率因低賠率而下降")

    top_4_codes = [h.get('code') for h in top4]
    cold_picks = [h for h in all_horses if h['odds_win'] >= 15 and h['best_time_sec'] <= 58.0]

    win_picks = [
        {'code': main_pick.get('code'), 'name': main_pick.get('name'),
         'odds': main_pick['odds_win'], 'reason': _core_advantage(main_pick)}
    ]
    if second_pick['odds_win'] <= 15:
        win_picks.append({
            'code': second_pick.get('code'), 'name': second_pick.get('name'),
            'odds': second_pick['odds_win'], 'reason': _core_advantage(second_pick)
        })

    q_combos = [
        {'a': main_pick.get('code'), 'a_name': main_pick.get('name'),
         'b': second_pick.get('code'), 'b_name': second_pick.get('name'),
         'type': '核心 Q 超值之選'},
        {'a': main_pick.get('code'), 'a_name': main_pick.get('name'),
         'b': hottest.get('code'), 'b_name': hottest.get('name'),
         'type': '穩健 Q 大熱保護'},
    ]

    triple_chase = {
        'banker': {'code': main_pick.get('code'), 'name': main_pick.get('name')},
        'legs': [
            {'code': second_pick.get('code'), 'name': second_pick.get('name')},
            {'code': top4[2].get('code'), 'name': top4[2].get('name')},
            {'code': top4[3].get('code'), 'name': top4[3].get('name')}
        ]
    }

    cold_bets = []
    for c in cold_picks[:2]:
        cold_bets.append({
            'code': c.get('code'), 'name': c.get('name'),
            'odds': c['odds_win'],
            'potential': f"最佳時間 {c['best_time_sec']} 秒屬頂尖水準，小注怡情有驚喜"
        })

    budget_plan = [
        {'item': f"獨贏主膽 {main_pick.get('code')}({main_pick.get('name')})", 'amount': 100},
        {'item': f"獨贏次選 {second_pick.get('code')}({second_pick.get('name')})", 'amount': 50},
        {'item': f"Q 核心 {main_pick.get('code')} {second_pick.get('code')}", 'amount': 50},
        {'item': f"Q 穩健 {main_pick.get('code')} {hottest.get('code')}", 'amount': 30},
        {'item': f"三重彩膽拖(膽:{main_pick.get('code')})", 'amount': 50},
        {'item': '冷馬小注怡情', 'amount': 20},
    ]
    total_budget = sum(x['amount'] for x in budget_plan)

    return {
        'overpriced_hot': {
            'code': hottest.get('code'),
            'name': hottest.get('name'),
            'odds': hottest['odds_win'],
            'concerns': hot_concerns
        },
        'win_picks': win_picks,
        'q_combos': q_combos,
        'triple_chase': triple_chase,
        'cold_bets': cold_bets,
        'budget_plan': budget_plan,
        'total_budget': total_budget
    }


def _core_advantage(h):
    """核心優勢文字總結"""
    reasons = []
    last3 = h.get('last_3', [])
    good = sum(1 for r in last3 if r <= 3)
    if good == 3:
        reasons.append("近績三仗全入三甲，狀態頂峰")
    elif good >= 2:
        reasons.append("近績穩定入 Q，質素保證")
    if h.get('draw', 0) <= 4:
        reasons.append(f"內檔 {h['draw']} 檔之利，短途走勢佳")
    if 3 <= h.get('draw', 0) <= 6:
        reasons.append(f"中間 {h['draw']} 檔，進可攻退可守")
    if h.get('best_time_sec', 999) <= 58.0:
        reasons.append(f"最佳時間 {h['best_time_sec']} 秒，步速夠快")
    if h.get('weight', 0) >= 1180:
        reasons.append(f"體重 {h['weight']} 磅，肌肉量飽滿狀態佳")
    if h.get('rating', 0) >= 130:
        reasons.append(f"評分 {h['rating']} 分，班底超班")
    if h.get('odds_win', 0) >= 10 and h.get('scores', {}).get('total', 0) >= 65:
        reasons.append("被市場低估，值博率高")
    return ' + '.join(reasons[:3]) if reasons else "整體條件均衡"


def run_analysis():
    data = load_race_data()
    race_info = data['race_info']
    horses = data['horses']

    pace_analysis = analyze_pace(race_info, horses)
    scored_horses = score_horses(horses, race_info)
    top4 = scored_horses[:4]
    betting = generate_betting_suggestion(top4, scored_horses, race_info)

    analysis = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'race_info': race_info,
        'meta': data.get('meta', {}),
        'pace_analysis': pace_analysis,
        'top4_predictions': [
            {
                'rank': i + 1,
                'horse': h,
                'core_advantage': _core_advantage(h)
            }
            for i, h in enumerate(top4)
        ],
        'all_ranked_horses': scored_horses,
        'betting_strategy': betting
    }
    save_analysis(analysis)
    return analysis


def simulate_update():
    """模擬自動更新：引入隨機擾動更新賠率、更新時間"""
    data = load_race_data()
    now = datetime.now()
    data['meta']['update_time'] = now.strftime('%Y-%m-%d %H:%M:%S')
    data['meta']['source'] = 'auto_refresh_simulated'
    for h in data['horses']:
        delta = random.choice([-0.5, -0.3, -0.1, 0, 0.1, 0.3, 0.5])
        new_odds = max(1.1, round(h['odds_win'] + delta, 1))
        h['odds_win'] = new_odds
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    analysis = run_analysis()
    return {
        'updated_at': data['meta']['update_time'],
        'horses_refreshed': len(data['horses']),
        'analysis_regenerated': True
    }


if __name__ == '__main__':
    result = run_analysis()
    print(f"[AI Engine] 分析完成 @ {result['generated_at']}")
    print(f"[AI Engine] 頭 4 名預測：")
    for p in result['top4_predictions']:
        h = p['horse']
        print(f"  第{p['rank']}名 -> #{h['number']} {h['code']}({h.get('name','')}) "
              f"AI分數={h['scores']['total']} 賠率={h['odds_win']}倍")
