#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Benter 模型投注建議報告"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, 'scripts')
from common import get_supabase
from collections import defaultdict

sb = get_supabase()

races = sb.table('races').select('race_id,race_no,race_date,distance,class_level').eq('race_date','2026-10-01').order('race_no').execute()
race_ids = [r['race_id'] for r in races.data]
race_info = {r['race_id']: r for r in races.data}

preds = sb.table('model_predictions').select('*').in_('race_id', race_ids).execute()

runners = sb.table('race_runners').select('runner_id,race_id,horse_no,horse_id,jockey,trainer,draw,win_odds,official_rating,declared_weight,weight_change,rest_days,gear,recent_form_score').in_('race_id', race_ids).execute()
runner_map = {r['runner_id']: r for r in runners.data}

horse_ids = list(set(r.get('horse_id') for r in runners.data if r.get('horse_id')))
horses = sb.table('horses').select('horse_id,horse_name').in_('horse_id', horse_ids).execute()
horse_names = {h['horse_id']: h['horse_name'] for h in horses.data}

for p in preds.data:
    r = runner_map.get(p['runner_id'], {})
    p['_name'] = horse_names.get(r.get('horse_id',''), '?')
    p['_no'] = r.get('horse_no', '?')
    p['_odds'] = r.get('win_odds')
    p['_jockey'] = (r.get('jockey','') or '')[:6]
    p['_rating'] = r.get('official_rating')
    p['_draw'] = r.get('draw')
    p['_gear'] = r.get('gear','') or ''
    p['_form'] = r.get('recent_form_score')

by_race = defaultdict(list)
for p in preds.data:
    by_race[p['race_id']].append(p)

print('=' * 80)
print('  2026-10-01 Benter 模型完整投注建議')
print('=' * 80)

all_dark_horses = []
all_win_picks = []
all_parlay_candidates = []

for race_id in sorted(by_race.keys(), key=lambda x: race_info[x]['race_no']):
    ri = race_info[race_id]
    rp = by_race[race_id]
    dist = ri.get('distance', '?')
    cls = ri.get('class_level', '?') or '?'
    rn = ri['race_no']

    by_prob = sorted(rp, key=lambda x: x['final_prob'], reverse=True)
    by_ev = sorted(rp, key=lambda x: x.get('expected_value') if x.get('expected_value') is not None else -999, reverse=True)

    top4 = by_prob[:4]

    # Dark horse: high model rank, low market rank, high odds, positive EV
    dark_horses = []
    model_sorted = sorted(rp, key=lambda x: x['raw_model_prob'], reverse=True)
    market_sorted = sorted(rp, key=lambda x: x['market_implied_prob'], reverse=True)
    for p in rp:
        model_rank = model_sorted.index(p) + 1
        market_rank = market_sorted.index(p) + 1
        odds = p.get('_odds')
        ev = p.get('expected_value')
        if model_rank <= 5 and market_rank > 5 and odds and odds > 20 and ev and ev > 0.05:
            dark_horses.append((p, model_rank, market_rank))
    dark_horses.sort(key=lambda x: x[0].get('expected_value', 0) or 0, reverse=True)

    print()
    print('=' * 80)
    print('  第 {} 場 | {}m | {} | {} 匹馬'.format(rn, dist, cls, len(rp)))
    print('=' * 80)

    # Top 4
    print()
    print('  [模型 Top 4] (按 P_final 勝率排序)')
    print('  {:>2} {:>4} {:>12} {:>8} {:>6} {:>6} {:>3} {:>4}'.format('#', '馬號', '馬名', 'P_final', '賠率', '騎師', '檔', '評分'))
    print('  ' + '-' * 52)
    for i, p in enumerate(top4):
        odds_s = '{:.1f}'.format(p['_odds']) if p.get('_odds') else 'N/A'
        rating_s = str(p.get('_rating','')) if p.get('_rating') else ''
        draw_s = str(p.get('_draw','')) if p.get('_draw') is not None else ''
        print('  {:>2} {:>4} {:>12} {:>8.4f} {:>6} {:>6} {:>3} {:>4}'.format(
            i+1, p['_no'], p['_name'][:10], p['final_prob'], odds_s, p['_jockey'], draw_s, rating_s))

    # Win/Place
    print()
    win_pick = top4[0]
    wp_odds = '{:.1f}'.format(win_pick['_odds']) if win_pick.get('_odds') else '?'
    print('  [獨贏/位置 推薦]')
    print('  獨贏: #{} {} (賠率 {}, P_final {:.1%})'.format(win_pick['_no'], win_pick['_name'][:10], wp_odds, win_pick['final_prob']))
    place_str = ', '.join(['#{} {}'.format(p['_no'], p['_name'][:6]) for p in top4[:3]])
    print('  位置: {}'.format(place_str))

    # Quinella
    q_nums = [str(p['_no']) for p in top4[:3]]
    print()
    print('  [連贏 Q / 位置Q]')
    print('  組合: {}'.format(' + '.join(q_nums)))

    # Tierce
    t_nums = [str(p['_no']) for p in top4[:4]]
    print('  [三重彩 / 四連環]')
    print('  首三名: {} (順序: {}-{}-{})'.format(' x '.join(t_nums[:3]), t_nums[0], t_nums[1], t_nums[2]))
    print('  四連環: {}'.format(' x '.join(t_nums)))

    # Dark horses
    if dark_horses:
        print()
        print('  *** 爆冷馬 ***')
        for p, mr, mkr in dark_horses[:2]:
            odds_s = '{:.1f}'.format(p['_odds']) if p.get('_odds') else '?'
            ev_s = '{:+.4f}'.format(p['expected_value']) if p.get('expected_value') else 'N/A'
            print('  #{} {} | 賠率 {} | EV {} | 模型排名 #{} vs 市場排名 #{}'.format(
                p['_no'], p['_name'][:10], odds_s, ev_s, mr, mkr))
            all_dark_horses.append((rn, p))
            all_parlay_candidates.append((rn, p))
    else:
        best_ev = by_ev[0]
        if best_ev.get('expected_value') and best_ev['expected_value'] > 0.05:
            odds_s = '{:.1f}'.format(best_ev['_odds']) if best_ev.get('_odds') else '?'
            ev_s = '{:+.4f}'.format(best_ev['expected_value'])
            print()
            print('  [最高 EV 馬] (潛在冷門)')
            print('  #{} {} | 賠率 {} | EV {}'.format(best_ev['_no'], best_ev['_name'][:10], odds_s, ev_s))
            all_parlay_candidates.append((rn, best_ev))

    all_win_picks.append((rn, win_pick))

# ============================================================
# CROSS-RACE
# ============================================================
print()
print('=' * 80)
print('  跨場投注建議')
print('=' * 80)

# Parlay
print()
print('  [過關推薦] (揀 2-3 場最有信心嘅馬)')
all_parlay_candidates.sort(key=lambda x: x[1].get('expected_value', 0) or 0, reverse=True)
shown = set()
parlay_picks = []
for rn, p in all_parlay_candidates:
    if rn not in shown and len(parlay_picks) < 4:
        parlay_picks.append((rn, p))
        shown.add(rn)

if len(parlay_picks) >= 2:
    combined_odds = 1.0
    for rn, p in parlay_picks:
        odds = p.get('_odds', 1) or 1
        combined_odds *= odds
        ev_s = '{:+.3f}'.format(p['expected_value']) if p.get('expected_value') else 'N/A'
        print('  Race {}: #{} {} (賠率 {}, EV {})'.format(rn, p['_no'], p['_name'][:10], p.get('_odds','?'), ev_s))
    print('  過關賠率: {:.0f}x'.format(combined_odds))
    print('  建議注碼: 總資金嘅 0.5-1% (高風險高回報)')

# Dark horse accumulator
print()
print('  [爆冷過關] (高賠率組合)')
dark_picks = []
for rn, p in all_dark_horses[:3]:
    dark_picks.append((rn, p))
if len(dark_picks) >= 2:
    combined = 1.0
    for rn, p in dark_picks:
        odds = p.get('_odds', 1) or 1
        combined *= odds
        print('  Race {}: #{} {} (賠率 {})'.format(rn, p['_no'], p['_name'][:10], p.get('_odds','?')))
    print('  爆冷過關賠率: {:.0f}x'.format(combined))
    print('  建議注碼: 總資金嘅 0.1-0.3% (極高風險)')

# Best value races
print()
print('  [最佳博弈場次] (最多正EV馬嘅場次)')
race_ev_count = defaultdict(int)
race_max_ev = defaultdict(float)
for p in preds.data:
    ev = p.get('expected_value')
    if ev and ev > 0:
        rno = race_info[p['race_id']]['race_no']
        race_ev_count[rno] += 1
        race_max_ev[rno] = max(race_max_ev[rno], ev)

for rn in sorted(race_ev_count.keys(), key=lambda x: race_ev_count[x], reverse=True)[:3]:
    print('  Race {}: {} 匹正EV | 最高EV {:+.3f}'.format(rn, race_ev_count[rn], race_max_ev[rn]))

# Summary table
print()
print('=' * 80)
print('  全場爆冷馬總覽')
print('=' * 80)
all_ev_list = []
for p in preds.data:
    r = runner_map.get(p['runner_id'], {})
    ev = p.get('expected_value')
    odds = r.get('win_odds')
    if ev and ev > 0.10 and odds and odds > 25:
        name = horse_names.get(r.get('horse_id',''), '?')
        rno = race_info[p['race_id']]['race_no']
        all_ev_list.append((rno, r.get('horse_no','?'), name, odds, ev, p['final_prob'], p['raw_model_prob']))

all_ev_list.sort(key=lambda x: x[4], reverse=True)
print()
print('  {:>4} {:>4} {:>12} {:>6} {:>8} {:>8} {:>8}'.format('場', '馬號', '馬名', '賠率', 'EV', 'P_final', 'P_model'))
print('  ' + '-' * 56)
for rno, hno, name, odds, ev, pf, pm in all_ev_list[:15]:
    print('  R{:<3} #{:<3} {:>12} {:>5.0f}x {:>+7.4f} {:>7.4f} {:>7.4f}'.format(
        rno, hno, name[:10], odds, ev, pf, pm))

print()
print('=' * 80)
print('  注意: 模型建議僅供參考，投注需自負風險。')
print('  Kelly 注碼極保守，冷門馬勝率低但賠率高，適合小額博弈。')
print('=' * 80)
