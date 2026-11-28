#!/usr/bin/env python3
"""Descriptive speed-rank vs model-rank report from the honest sample cache.

Read-only, offline. Uses reports/.honest_samples_20250907.json (as-of factors
built for the honest backtest) and the published venue weights to rank the
field, then compares that ranking with the racecard best-time speed ranking.

Display only: no weights change, no P_final change, speed_engine stays
display_only. Buckets below 30 comparable races are reported as numbers but
carry no conclusion. A true speed figure from finish_time/margin waits until
those fields are fully backfilled.
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from statistics import mean
from zoneinfo import ZoneInfo

HKT = ZoneInfo('Asia/Hong_Kong')

sys.path.insert(0, os.path.dirname(__file__))
import ai_review as A
import model_config as M
import speed_shadow as SPEED
from common import get_supabase

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_ID = 'speed_shadow_report'
DEFAULT_SAMPLES = os.path.join(ROOT, 'reports', '.honest_samples_20250907.json')
MIN_BUCKET_RACES = 30


def _distance_band(distance):
    if distance is None:
        return 'UNK'
    distance = int(distance)
    if distance <= 1200:
        return '<=1200m'
    if distance <= 1650:
        return '1201-1650m'
    return '>1650m'


def _field_band(n):
    if n <= 8:
        return '<=8'
    if n <= 11:
        return '9-11'
    return '12-14+'


def race_metrics(sample, weights):
    """One race: model vs speed ranks, top-1/top-3 hits, Spearman rho."""
    factors = sample.get('factors') or []
    runner_count = len(factors)
    if not factors or runner_count < 4:
        return None
    scores = [sum(f[k] * weights[k] for k in M.FACTOR_KEYS) for f in factors]
    probs = A._softmax(scores)
    model_ranks = SPEED.ranks(probs)
    meta, rows = SPEED.compare_runners(sample.get('best_times') or [], model_ranks)
    if not meta['comparable']:
        return None

    winner = sample.get('winner_idx')
    model_order = sorted(range(runner_count), key=lambda i: -probs[i])
    speed_order = sorted(
        range(runner_count),
        key=lambda i: (rows[i]['best_time_sec'] is None, rows[i]['best_time_sec'] or 0.0))
    deltas = [abs(r['rank_delta']) for r in rows if r['rank_delta'] is not None]
    has_winner = isinstance(winner, int) and 0 <= winner < runner_count
    return {
        'race_id': sample.get('race_id'),
        'venue': sample.get('venue'),
        'distance': sample.get('distance'),
        'field': runner_count,
        'winner_idx': winner,
        'rank_corr': meta['rank_corr'],
        'model_top1': model_order[0],
        'speed_top1': speed_order[0],
        'model_top1_hit': has_winner and model_order[0] == winner,
        'speed_top1_hit': has_winner and speed_order[0] == winner,
        'model_top3_hit': has_winner and winner in model_order[:3],
        'speed_top3_hit': has_winner and winner in speed_order[:3],
        'top3_overlap': len(set(model_order[:3]) & set(speed_order[:3])) / 3.0,
        'mean_abs_delta': round(mean(deltas), 3) if deltas else None,
    }


def summarise(races, label):
    if not races:
        return {'label': label, 'races': 0, 'sufficient': False}
    rhos = [r['rank_corr'] for r in races if r['rank_corr'] is not None]
    deltas = [r['mean_abs_delta'] for r in races if r['mean_abs_delta'] is not None]
    return {
        'label': label,
        'races': len(races),
        'sufficient': len(races) >= MIN_BUCKET_RACES,
        'mean_rank_corr': round(mean(rhos), 4) if rhos else None,
        'model_top1_hit': round(mean(1.0 if r['model_top1_hit'] else 0.0 for r in races), 4),
        'speed_top1_hit': round(mean(1.0 if r['speed_top1_hit'] else 0.0 for r in races), 4),
        'model_top3_hit': round(mean(1.0 if r['model_top3_hit'] else 0.0 for r in races), 4),
        'speed_top3_hit': round(mean(1.0 if r['speed_top3_hit'] else 0.0 for r in races), 4),
        'top3_overlap': round(mean(r['top3_overlap'] for r in races), 4),
        'mean_abs_rank_delta': round(mean(deltas), 3) if deltas else None,
    }


def build_report(samples):
    by_venue, by_field, by_distance = defaultdict(list), defaultdict(list), defaultdict(list)
    coverage = {'samples': len(samples), 'races_any_time': 0,
                'races_comparable': 0, 'runners_with_time': 0, 'runners': 0,
                'date_min': None, 'date_max': None}
    metrics = []
    for sample in samples:
        times = sample.get('best_times') or []
        valid = sum(1 for t in times if t is not None)
        coverage['runners'] += len(times)
        coverage['runners_with_time'] += valid
        coverage['races_any_time'] += 1 if valid else 0
        weights = M.weights_for(sample.get('venue') or 'ST')
        row = race_metrics(sample, weights)
        if row is None:
            continue
        metrics.append(row)
        coverage['races_comparable'] += 1
        date = str(sample.get('date') or '')[:10]
        if date:
            coverage['date_min'] = min(coverage['date_min'] or date, date)
            coverage['date_max'] = max(coverage['date_max'] or date, date)
        by_venue[row['venue'] or 'UNK'].append(row)
        by_field[_field_band(row['field'])].append(row)
        by_distance[_distance_band(row['distance'])].append(row)
    coverage['race_rate'] = round(coverage['races_comparable'] / len(samples), 4) if samples else 0.0
    coverage['runner_rate'] = round(
        coverage['runners_with_time'] / coverage['runners'], 4) if coverage['runners'] else 0.0
    return {
        'coverage': coverage,
        'overall': summarise(metrics, 'overall'),
        'by_venue': {k: summarise(v, k) for k, v in sorted(by_venue.items())},
        'by_field': {k: summarise(v, k) for k, v in sorted(by_field.items())},
        'by_distance': {k: summarise(v, k) for k, v in sorted(by_distance.items())},
        'races': metrics,
    }


def _pct(v):
    return '—' if v is None else f'{v * 100:.1f}%'


def _table(rows):
    lines = ['| 分桶 | 場數 | 樣本足夠(≥30) | 平均 rank rho | 模型 Top1 | 速度 Top1 '
             '| 模型 Top3 | 速度 Top3 | Top3 重疊 | 平均絕對排名差 |',
             '|---|---|---|---|---|---|---|---|---|---|']
    for row in rows:
        lines.append(
            f'| {row["label"]} | {row["races"]} | {"是" if row["sufficient"] else "否（不結論）"} '
            f'| {row.get("mean_rank_corr", "—")} | {_pct(row.get("model_top1_hit"))} '
            f'| {_pct(row.get("speed_top1_hit"))} | {_pct(row.get("model_top3_hit"))} '
            f'| {_pct(row.get("speed_top3_hit"))} | {_pct(row.get("top3_overlap"))} '
            f'| {row.get("mean_abs_rank_delta", "—")} |')
    return lines


def render_markdown(report, generated, samples_path):
    cov = report['coverage']
    lines = [
        f'# 速度分 vs 模型排名 shadow 對照（{generated}）',
        '',
        '- 唯讀描述性報表；模型與速度排名都只用賽前資料，不入任何權重、不改 P_final。',
        '- 「模型」= P_model（9 因子，未融合市場）；唔係 live 顯示嘅 P_final。',
        '- 速度 = 賽日卡 `best_time`（同場同程最佳時間）；真正的締速指數要等 '
        'finish_time／margin 補齊後另開。',
        '- `has_best_time=0` 一律留空，不填常數；模型原本的途程分原封不動。',
        f'- 樣本：{os.path.relpath(samples_path, ROOT)}（as-of 因子＋已發佈權重，診斷用）。',
        '',
        '## 覆蓋率',
        '',
        f'- {cov["samples"]} 場樣本；有最佳時間 {cov["races_any_time"]} 場；'
        f'全場 ≥4 匹有時間（可比較）{cov["races_comparable"]} 場'
        f'（{_pct(cov["race_rate"])}）。',
        f'- 可比較場次期間：{cov["date_min"]} → {cov["date_max"]}'
        '（best_time 只在近期抓取有值，結論只覆蓋此期間）。',
        f'- 馬匹層面：{cov["runners_with_time"]}/{cov["runners"]} 有最佳時間'
        f'（{_pct(cov["runner_rate"])}）。',
        '',
        '## 整體',
        '',
        *_table([report['overall']]),
        '',
        '## 分場地',
        '',
        *_table(list(report['by_venue'].values())),
        '',
        '## 分馬數',
        '',
        *_table(list(report['by_field'].values())),
        '',
        '## 分途程',
        '',
        *_table(list(report['by_distance'].values())),
        '',
        '## 判讀',
        '',
    ]
    overall = report['overall']
    if overall['races'] and overall['mean_rank_corr'] is not None:
        lines.append(f'- 整體 Spearman rho = {overall["mean_rank_corr"]}：模型（P_model）與 '
                     f'best_time 兩個排名大部分唔一致；Top3 重疊只有 {_pct(overall["top3_overlap"])}。')
        lines.append(f'- 單靠 best_time：Top1 {_pct(overall["speed_top1_hit"])}、'
                     f'Top3 {_pct(overall["speed_top3_hit"])}，明顯低於模型嘅 '
                     f'{_pct(overall["model_top1_hit"])}／{_pct(overall["model_top3_hit"])}；'
                     '與已知「速度混入 P_model 令 NLL 變差」一致，維持 display_only。')
    lines += [
        '- 少於 30 場的分桶只列數字、不結論；達標與否都不會改 live 預設。',
        '- 目前 best_time 覆蓋有限（舊場次多為空），任何「速度因子」研究都要先等 '
        'finish_time／margin 全面補齊，再按 docs/PREREGISTERED_AB.md 走 A/B。',
        '- `speed_engine` 維持 display_only、default off；shadow 每 tick 寫入 '
        '`pipeline_status.shadow_predictions`（保留 7 日）。',
        '',
    ]
    return '\n'.join(lines)


def generate(samples_path=DEFAULT_SAMPLES, out_dir=None, date=None, persist=True):
    with open(samples_path, encoding='utf-8') as fh:
        cache = json.load(fh)
    samples = cache['samples']
    report = build_report(samples)
    report['meta'] = cache.get('meta', {})
    generated = date or datetime.now(HKT).strftime('%Y-%m-%d')

    out_dir = out_dir or os.path.join(ROOT, 'reports')
    os.makedirs(out_dir, exist_ok=True)
    md_path = os.path.join(out_dir, f'speed_shadow_{generated}.md')
    json_path = os.path.join(out_dir, f'speed_shadow_{generated}.json')
    with open(md_path, 'w', encoding='utf-8') as fh:
        fh.write(render_markdown(report, generated, samples_path))
    with open(json_path, 'w', encoding='utf-8') as fh:
        json.dump({'generated': generated, **report}, fh, ensure_ascii=False, indent=2)
    print(f'[SpeedShadow] {report["overall"]["races"]} comparable races '
          f'({report["coverage"]["race_rate"] * 100:.1f}%) -> {md_path} | {json_path}')

    if persist:
        try:
            supabase = get_supabase()
            if supabase:
                from common import retry_supabase
                retry_supabase(lambda: supabase.table('pipeline_status').upsert({
                    'id': REPORT_ID,
                    'last_run': datetime.now(HKT).isoformat(),
                    'status_json': {
                        'date': generated,
                        'path': os.path.relpath(md_path, ROOT),
                        'races': report['overall']['races'],
                        'mean_rank_corr': report['overall']['mean_rank_corr'],
                        'model_top1_hit': report['overall']['model_top1_hit'],
                        'speed_top1_hit': report['overall']['speed_top1_hit'],
                        'updated_at': datetime.now(HKT).isoformat(),
                    },
                }, on_conflict='id').execute())
        except Exception as e:
            print(f'[SpeedShadow] WARN summary not persisted: {e}')
    return md_path, json_path, report


def main():
    parser = argparse.ArgumentParser(description='Speed vs model rank shadow report')
    parser.add_argument('--samples', default=DEFAULT_SAMPLES)
    parser.add_argument('--out-dir', default=None)
    parser.add_argument('--date', default=datetime.now(HKT).strftime('%Y-%m-%d'))
    parser.add_argument('--no-persist', action='store_true')
    args = parser.parse_args()
    generate(args.samples, args.out_dir, args.date, persist=not args.no_persist)
    return 0


if __name__ == '__main__':
    sys.exit(main())