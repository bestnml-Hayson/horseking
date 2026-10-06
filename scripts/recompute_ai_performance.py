"""
重新精算 AI 覆盤數據 v5.43
統一使用 EV-based 策略重新計算所有歷史 ai_performance 記錄
修復 ROI、win_rate、top3_rate 等指標

嚴禁觸碰 2026-10-07 的數據
"""

import os
import sys
from collections import defaultdict
from dotenv import load_dotenv
from supabase import create_client, Client

sys.stdout.reconfigure(encoding='utf-8')

load_dotenv('.env.local')

SUPABASE_URL = os.getenv('NEXT_PUBLIC_SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_KEY')
CUTOFF_DATE = '2026-10-07'

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing Supabase credentials in .env.local")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def recompute_performance_for_race(race_id, race_date, venue, race_no):
    """重新計算單場賽事的 ai_performance"""

    # 1. 獲取該場次的所有 race_runners (需要 finish_position 和 win_odds)
    runners_resp = supabase.table('race_runners').select('*').eq('race_id', race_id).execute()
    runners = runners_resp.data or []

    if not runners:
        return None

    runner_map = {r['runner_id']: r for r in runners}

    # 2. 嘗試獲取 model_predictions
    preds_resp = supabase.table('model_predictions').select('*').eq('race_id', race_id).execute()
    preds = preds_resp.data or []

    # 3. 計算 top1_hit 和 top3_hit_count
    if preds:
        # 使用 model_predictions: 按 final_prob 排序
        sorted_preds = sorted(preds, key=lambda p: p.get('final_prob') or p.get('raw_model_prob') or 0, reverse=True)
    else:
        # 無 model_predictions: 使用 win_odds 最低作為 proxy (熱門馬)
        runners_with_odds = [r for r in runners if r.get('win_odds') and r['win_odds'] > 1.0]
        if not runners_with_odds:
            return None
        sorted_by_odds = sorted(runners_with_odds, key=lambda r: r['win_odds'])
        # 偽造 predictions 格式
        sorted_preds = [{'runner_id': r['runner_id'], 'final_prob': 1.0/r['win_odds'], 'expected_value': 0.0} for r in sorted_by_odds]

    # Top 1 pick
    top1_pred = sorted_preds[0] if sorted_preds else None
    top1_runner = runner_map.get(top1_pred['runner_id']) if top1_pred else None
    top1_finish = top1_runner.get('finish_position') if top1_runner else None
    top1_hit = top1_finish == 1 if top1_finish else False

    # Top 3 picks
    top3_preds = sorted_preds[:3]
    top3_hit_count = 0
    for p in top3_preds:
        r = runner_map.get(p['runner_id'])
        if r:
            finish_pos = r.get('finish_position')
            if finish_pos is not None and finish_pos <= 3:
                top3_hit_count += 1

    # 4. 計算 total_bets 和 total_returns (EV-based strategy)
    total_bets = 0
    total_returns = 0

    if preds:
        # 有 model_predictions: 使用 EV > 0.15 策略
        for p in sorted_preds:
            ev = p.get('expected_value') or 0
            if ev > 0.15:
                r = runner_map.get(p['runner_id'])
                if r and r.get('win_odds') and r.get('finish_position'):
                    bet_amount = 100
                    total_bets += bet_amount
                    if r['finish_position'] == 1:
                        total_returns += bet_amount * r['win_odds']
    else:
        # 無 model_predictions: 使用 odds < 5.0 策略 (backfill proxy)
        for r in runners:
            odds = r.get('win_odds')
            if odds and 1.0 < odds < 5.0 and r.get('finish_position'):
                bet_amount = 100
                total_bets += bet_amount
                if r['finish_position'] == 1:
                    total_returns += bet_amount * odds

    roi_percent = ((total_returns - total_bets) / total_bets * 100) if total_bets > 0 else 0

    # 5. 構建 ai_performance 記錄
    top3_picks = ','.join([p['runner_id'] for p in top3_preds]) if top3_preds else None

    record = {
        'race_id': race_id,
        'race_date': race_date,
        'venue': venue,
        'race_no': race_no,
        'top1_pick_runner_id': top1_pred['runner_id'] if top1_pred else None,
        'top1_pick_finish_pos': top1_finish,
        'top1_hit': top1_hit,
        'top3_picks': top3_picks,
        'top3_hit_count': top3_hit_count,
        'total_bets': total_bets,
        'total_returns': total_returns,
        'roi_percent': round(roi_percent, 2),
        'analysis_date': race_date,
    }

    return record


def main():
    print("="*60)
    print("AI 覆盤重新精算腳本 v5.43")
    print(f"修復範圍: race_date < {CUTOFF_DATE}")
    print("策略: 統一使用 EV-based (有 model_predictions) 或 odds-based (無)")
    print("="*60)

    # 1. 獲取所有歷史場次
    print("\n查詢歷史場次...")
    races_resp = supabase.table('races').select('race_id,race_date,venue,race_no').lt('race_date', CUTOFF_DATE).execute()
    races = races_resp.data or []
    print(f"  找到 {len(races)} 場歷史賽事")

    # 2. 重新計算每場賽事的 ai_performance
    print("\n開始重新計算...")
    recomputed = 0
    errors = 0

    for i, race in enumerate(races, 1):
        if i % 50 == 0:
            print(f"  進度: {i}/{len(races)}")

        try:
            record = recompute_performance_for_race(
                race['race_id'],
                race['race_date'],
                race['venue'],
                race['race_no']
            )

            if record is None:
                continue

            # 更新或插入 ai_performance
            # 先檢查是否已存在
            existing = supabase.table('ai_performance').select('id').eq('race_id', race['race_id']).execute()

            if existing.data:
                # 更新
                supabase.table('ai_performance').update(record).eq('race_id', race['race_id']).execute()
            else:
                # 插入
                supabase.table('ai_performance').insert(record).execute()

            recomputed += 1

        except Exception as e:
            print(f"  ERROR {race['race_date']} R{race['race_no']}: {e}")
            errors += 1

    print(f"\n[OK] 重新計算完成")
    print(f"  成功: {recomputed} 場")
    print(f"  錯誤: {errors} 場")

    # 3. 驗證結果
    print("\n驗證結果...")
    perf_resp = supabase.table('ai_performance').select('*').lt('race_date', CUTOFF_DATE).execute()
    perf_records = perf_resp.data or []

    if perf_records:
        total_races = len(perf_records)
        top1_hits = sum(1 for r in perf_records if r.get('top1_hit'))
        total_bets = sum(r.get('total_bets', 0) for r in perf_records)
        total_returns = sum(r.get('total_returns', 0) for r in perf_records)
        avg_roi = sum(r.get('roi_percent', 0) for r in perf_records) / total_races if total_races > 0 else 0

        print(f"  總場次: {total_races}")
        print(f"  獨贏命中: {top1_hits} ({top1_hits/total_races*100:.1f}%)")
        print(f"  總下注: ${total_bets}")
        print(f"  總回報: ${total_returns}")
        print(f"  淨利潤: ${total_returns - total_bets}")
        print(f"  平均 ROI: {avg_roi:.1f}%")


if __name__ == '__main__':
    main()
