#!/usr/bin/env python3
"""Honest-protocol evaluation of the jockey-upgrade differential.

The feature (scripts/jockey_upgrade.py) is a candidate tenth signal: the
current jockey's as-of win rate minus the mean as-of win rate of the jockeys
who rode the horse in its last six starts. This script answers three questions
before any flag can be discussed:

  1. Coverage - is the jockey column complete, and how often can the as-of
     differential be computed?
  2. Redundancy - Pearson r against the deployed jockeyTrainer factor. The
     variant is implemented as a blend *into* jockeyTrainer (a merge, not a
     second correlated factor); |r| > 0.65 is reported as mandatory-merge.
  3. Honest value - walk-forward 5-fold, fold-train-only weights, paired NLL
     delta with day-bootstrap CI and per-fold improvement count.

Read-only against Supabase; output reports/jockey_upgrade_<date>.md + .json and
pipeline_status.jockey_upgrade_report. The feature stays shadow-only; nothing
here changes the live P_model or any default.
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from statistics import mean
from zoneinfo import ZoneInfo

if __name__ == '__main__' and hasattr(sys.stdout, 'buffer'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
sys.path.insert(0, os.path.dirname(__file__))

from common import get_supabase, retry_supabase
import backtest_honest as H
import backtest_models as B
import jockey_upgrade as J
import model_config as M

HKT = ZoneInfo('Asia/Hong_Kong')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'reports', '.honest_samples_20250907.json')
STATUS_ID = 'jockey_upgrade_report'
BLENDS = (0.15, 0.30)


def load_runner_history(supabase):
    """Every finished run with its jockey, for as-of rates and prior riders."""
    rows, offset = [], 0
    while True:
        got = retry_supabase(
            lambda o=offset: supabase.table('race_runners')
            .select('horse_id,jockey,finish_position,races!inner(race_date)')
            .not_.is_('finish_position', 'null')
            .order('runner_id').range(o, o + 999).execute()).data or []
        for row in got:
            race = row.get('races')
            if isinstance(race, list):
                race = race[0] if race else None
            if not race or not race.get('race_date'):
                continue
            rows.append({
                'horse_id': row.get('horse_id'),
                'jockey': row.get('jockey'),
                'finish_position': row.get('finish_position'),
                'race_date': str(race['race_date'])[:10],
            })
        if len(got) < 1000:
            break
        offset += 1000
    return rows


def load_samples():
    with open(CACHE, encoding='utf-8') as fh:
        payload = json.load(fh)
    return payload['samples'], payload['meta']


def attach_features(samples, history, asof):
    for sample in samples:
        sample['jockey_upgrade'] = [
            J.feature_asof(asof, row.get('jockey'),
                           history.get(row.get('horse_id'), []), sample['date'])
            for row in sample['rows']
        ]
    return samples


def coverage_stats(samples, meta):
    total = covered = miss_current = no_prior = no_prior_rate = 0
    by_month, by_venue = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for sample in samples:
        for fv in sample['jockey_upgrade']:
            total += 1
            if fv['score'] is not None:
                covered += 1
                by_month[sample['date'][:7]][0] += 1
                by_venue[sample['venue']][0] += 1
            else:
                if fv['current_rate'] is None:
                    miss_current += 1
                elif fv['prior_runs'] == 0:
                    no_prior += 1
                else:
                    no_prior_rate += 1
            by_month[sample['date'][:7]][1] += 1
            by_venue[sample['venue']][1] += 1
    return {
        'runners': total,
        'covered': covered,
        'coverage': round(covered / total, 4) if total else 0.0,
        'missing_current_rate': miss_current,
        'no_prior_runs': no_prior,
        'prior_runs_without_rate': no_prior_rate,
        'by_month': {k: {'covered': v[0], 'runners': v[1],
                         'coverage': round(v[0] / v[1], 4) if v[1] else 0.0}
                     for k, v in sorted(by_month.items())},
        'by_venue': {k: {'covered': v[0], 'runners': v[1],
                         'coverage': round(v[0] / v[1], 4) if v[1] else 0.0}
                     for k, v in sorted(by_venue.items())},
        'honest_cache': {
            'usable_races': meta.get('usable'),
            'runners': meta.get('runners'),
            'asof_jockey_covered': meta.get('asof_jockey_covered'),
        },
    }


def correlation_stats(samples):
    scores, jt, delta, rate = [], [], [], []
    for sample in samples:
        for i, fv in enumerate(sample['jockey_upgrade']):
            if fv['score'] is None:
                continue
            scores.append(fv['score'])
            delta.append(fv['delta'])
            rate.append(fv['current_rate'])
            jt.append(sample['factors'][i].get('jockeyTrainer'))
    stats = {
        'runners': len(scores),
        'r_score_jockeyTrainer': J.pearson(scores, jt),
        'r_delta_jockeyTrainer': J.pearson(delta, jt),
        'r_current_rate_jockeyTrainer': J.pearson(rate, jt),
    }
    if scores:
        ordered = sorted(scores)
        stats['score_mean'] = round(mean(scores), 2)
        stats['score_p05'] = ordered[int(0.05 * (len(ordered) - 1))]
        stats['score_p95'] = ordered[int(0.95 * (len(ordered) - 1))]
        stats['delta_mean'] = round(mean(delta), 4)
    return stats


def blend_factors(sample, blend):
    factors = [dict(f) for f in sample['factors']]
    for i, fv in enumerate(sample['jockey_upgrade']):
        if fv['score'] is None:
            continue
        factors[i]['jockeyTrainer'] = ((1 - blend) * factors[i]['jockeyTrainer']
                                       + blend * fv['score'])
    return factors


def evaluate(samples, blocks):
    base_tables = {'HV': M.raw_weights_for('HV'), 'ST': M.raw_weights_for('ST')}
    fold_map, diagnostics = H.fit_blocks(samples, blocks, base_tables)
    test_ids = [s for _, test in blocks for s in test]
    covered = [s for s in test_ids
               if any(fv['score'] is not None for fv in s['jockey_upgrade'])]
    covered_ids = {s['race_id'] for s in covered}
    full_race_ok = [s for s in covered
                    if sum(1 for fv in s['jockey_upgrade'] if fv['score'] is not None)
                    >= 0.8 * len(s['rows'])]

    sample_by_id = {s['race_id']: s for s in samples}
    results = {'oos_races': len(test_ids), 'covered_races': len(covered),
               'covered_runners': sum(1 for s in covered
                                      for fv in s['jockey_upgrade']
                                      if fv['score'] is not None),
               'near_full_coverage_races': len(full_race_ok)}

    def probs(sample, factors_by_race):
        return H.p_model(sample, factors_by_race[sample['race_id']],
                         fold_map[sample['race_id']])

    base_factors = {s['race_id']: s['factors'] for s in covered}
    base_probs = {s['race_id']: probs(s, base_factors) for s in covered}
    base_rows = H.race_rows(covered, base_probs)
    results['baseline'] = H.summarize(base_rows)

    results['variants'] = {}
    for blend in BLENDS:
        factors_by_race = {s['race_id']: blend_factors(s, blend) for s in covered}
        var_probs = {s['race_id']: probs(s, factors_by_race) for s in covered}
        var_rows = H.race_rows(covered, var_probs)
        delta, ci = H.paired_delta(var_rows, base_rows)
        folds = H.fold_improvements(blocks, sample_by_id, base_probs, var_probs)
        subset_probs = {rid: p for rid, p in var_probs.items() if rid in
                        {s['race_id'] for s in full_race_ok}}
        subset_base = {rid: p for rid, p in base_probs.items() if rid in subset_probs}
        sub_rows = H.race_rows(full_race_ok, subset_probs)
        sub_base_rows = H.race_rows(full_race_ok, subset_base)
        sub_delta, sub_ci = H.paired_delta(sub_rows, sub_base_rows)
        results['variants'][str(blend)] = {
            'blend': blend,
            'variant': H.summarize(var_rows),
            'delta_nll': delta, 'delta_ci': ci,
            'folds': folds,
            'near_full': {
                'races': len(full_race_ok),
                'baseline': H.summarize(sub_base_rows),
                'variant': H.summarize(sub_rows),
                'delta_nll': sub_delta, 'delta_ci': sub_ci,
            },
            'strata_venue': {
                label: H.summarize(group)
                for label, group in _group_by_venue(var_rows).items()
            },
        }

    results['fold_weights'] = diagnostics
    return results


def _group_by_venue(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row['venue']].append(row)
    return groups


def fmt(value, digits=4):
    return '-' if value is None else f'{value:.{digits}f}'


def pct(value):
    return '-' if value is None else f'{value * 100:.1f}%'


def passed(entry):
    ci = entry.get('delta_ci') or [None, None]
    folds = entry.get('folds') or {}
    return (entry.get('delta_nll') is not None and entry['delta_nll'] < 0
            and ci[1] is not None and ci[1] < 0
            and folds.get('folds') and folds.get('improved', 0) >= 4)


def build_report(payload):
    cov = payload['coverage']
    corr = payload['correlation']
    ev = payload['evaluation']
    lines = []
    add = lines.append
    add(f"# 騎師升級差特徵（{payload['generated_at'][:10]}）")
    add('')
    add('- 定義：今場騎師 as-of 勝率 − 該駒最近 6 仗騎師 as-of 勝率平均值；'
        '嚴格只用比賽日之前的賽果（min 3 starts）。')
    add('- 只作 shadow／研究；未入 live P_model，所有 flag 維持 off。')
    add('')
    add('## 欄位完整度（DB）')
    add('')
    add(f"- race_runners 總數 {payload['jockey_completeness']['runners']}；"
        f"騎師欄位非空 {pct(payload['jockey_completeness']['jockey_nonempty'])}；"
        f"完成賽事中缺騎師的場次 {payload['jockey_completeness']['races_missing_jockey']}")
    add('')
    add('## 特徵覆蓋率（honest 樣本）')
    add('')
    add(f"- runners {cov['runners']}；可計算 {cov['covered']}（{pct(cov['coverage'])}）；"
        f"缺今場騎師率 {cov['missing_current_rate']}、無往績 {cov['no_prior_runs']}、"
        f"往績騎師全部 <3 場 {cov['prior_runs_without_rate']}")
    add('')
    add('| 月份 | 可計算 | runners | 覆蓋 |')
    add('|---|---|---|---|')
    for month, d in cov['by_month'].items():
        add(f"| {month} | {d['covered']} | {d['runners']} | {pct(d['coverage'])} |")
    add('')
    add('| 場地 | 可計算 | runners | 覆蓋 |')
    add('|---|---|---|---|')
    for venue, d in cov['by_venue'].items():
        add(f"| {venue} | {d['covered']} | {d['runners']} | {pct(d['coverage'])} |")
    add('')
    add('## 與現有 jockeyTrainer 因子相關性')
    add('')
    add(f"- runners {corr['runners']}；r(score, jockeyTrainer) = "
        f"{fmt(corr['r_score_jockeyTrainer'])}；r(delta, jockeyTrainer) = "
        f"{fmt(corr['r_delta_jockeyTrainer'])}；r(current_rate, jockeyTrainer) = "
        f"{fmt(corr['r_current_rate_jockeyTrainer'])}")
    level_r = corr.get('r_current_rate_jockeyTrainer')
    diff_r = corr.get('r_score_jockeyTrainer')
    add('- 判定：原始騎師勝率水平與 jockeyTrainer 的 r = '
        f'{fmt(level_r)}（>0.65），不可作為第二個獨立因子；'
        f'差分本身 r = {fmt(diff_r)}。因此只使用差分，並以 blend 方式'
        '合併進 jockeyTrainer（合併而非新增因子），符合「合併或二選一」規則。')
    add('')
    add('## Honest 回測（5 折 walk-forward、逐折權重、paired bootstrap）')
    add('')
    add(f"- OOS races {ev['oos_races']}；特徵可計算 races {ev['covered_races']}"
        f"（runners {ev['covered_runners']}）；≥80% runners 有值的 races "
        f"{ev['near_full_coverage_races']}")
    add('')
    add('| blend | 場數 | 基線 NLL | 變體 NLL | ΔNLL | 95% CI | 基線 Top1 | 變體 Top1 | 改善折 | 達標 |')
    add('|---|---|---|---|---|---|---|---|---|---|')
    base = ev['baseline']
    for name, d in ev['variants'].items():
        ci = d['delta_ci']
        fo = d['folds']
        add(f"| {d['blend']} | {ev['covered_races']} | {fmt(base['nll'], 5)} | "
            f"{fmt(d['variant']['nll'], 5)} | {fmt(d['delta_nll'], 5)} | "
            f"{fmt(ci[0], 5) if ci else '-'} ~ {fmt(ci[1], 5) if ci else '-'} | "
            f"{pct(base['top1'])} | {pct(d['variant']['top1'])} | "
            f"{fo.get('improved', '-')}/{fo.get('folds', '-')} | "
            f"{'是' if passed(d) else '否'} |")
    add('')
    add('### 近全覆蓋子集（每場 ≥80% runners 有特徵）')
    add('')
    add('| blend | 場數 | 基線 NLL | 變體 NLL | ΔNLL | 95% CI |')
    add('|---|---|---|---|---|---|')
    for name, d in ev['variants'].items():
        near = d['near_full']
        ci = near['delta_ci']
        add(f"| {d['blend']} | {near['races']} | {fmt(near['baseline']['nll'], 5)} | "
            f"{fmt(near['variant']['nll'], 5)} | {fmt(near['delta_nll'], 5)} | "
            f"{fmt(ci[0], 5) if ci else '-'} ~ {fmt(ci[1], 5) if ci else '-'} |")
    add('')
    add('### 分場地（最佳 blend）')
    add('')
    passing = [n for n, d in ev['variants'].items() if passed(d)]
    pool = passing or list(ev['variants'])
    best_name = max(pool, key=lambda n: -(ev['variants'][n]['delta_nll'] or 9e9))
    best = ev['variants'][best_name]
    add(f"- 展示 blend = {best['blend']}"
        + ('（達標變體中 ΔNLL 最低）' if passing else '（無達標變體，僅供參考）'))
    add('')
    add('| venue | 場數 | NLL | Top1 | Top3 |')
    add('|---|---|---|---|---|')
    for venue, d in best['strata_venue'].items():
        add(f"| {venue} | {d['races']} | {fmt(d['nll'], 5)} | {pct(d['top1'])} | {pct(d['top3'])} |")
    add('')
    meet = [n for n, d in ev['variants'].items() if passed(d)]
    add('## 結論')
    add('')
    if meet:
        add(f"- blend {', '.join(meet)} 達到 ΔNLL<0、CI 全負、≥4/5 折改善；"
            '仍只保留 flag（default off），需另開獨立 A/B 才可談上線。')
    else:
        add('- 未有任何 blend 達到採納門檻（ΔNLL<0、95% CI 全負、≥4/5 折改善）；'
            '維持 shadow-only，flag 預設 off。')
    add(f"- 覆蓋率 {pct(cov['coverage'])}；接近全覆蓋的場次 "
        f"{ev['near_full_coverage_races']}，未達每個分桶 ≥30 場前不報分桶結論。")
    add('- 首月（2025-09）覆蓋僅 17%，因 archive 由該月開始、無 3 場往績；'
        'blend 只作用於有值的 runners，其餘沿用原 jockeyTrainer（fallback）。')
    add('- `jockey_upgrade` flag 預設 off；live P_model／P_final 計算路徑零改動。')
    add('')
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description='Jockey-upgrade honest backtest')
    parser.add_argument('--out-dir', default=os.path.join(ROOT, 'reports'))
    parser.add_argument('--report-only', action='store_true')
    args = parser.parse_args()

    stamp = datetime.now(HKT).strftime('%Y-%m-%d')
    if args.report_only:
        json_path = os.path.join(args.out_dir, f'jockey_upgrade_{stamp}.json')
        with open(json_path, encoding='utf-8') as fh:
            payload = json.load(fh)
        md_path = os.path.join(args.out_dir, f'jockey_upgrade_{stamp}.md')
        with open(md_path, 'w', encoding='utf-8') as fh:
            fh.write(build_report(payload))
        print(f'[Write] {os.path.basename(md_path)} (from JSON)')
        return 0

    samples, meta = load_samples()
    print(f'[Load] {len(samples)} races / {meta["runners"]} runners from cache')
    supabase = get_supabase()
    rows = load_runner_history(supabase)
    print(f'[Load] {len(rows)} finished runs with jockey for as-of rates')
    history = defaultdict(list)
    for row in rows:
        if row.get('horse_id'):
            history[row['horse_id']].append(row)
    jockey_nonempty = sum(1 for r in rows if (r.get('jockey') or '').strip())
    races_missing, races_seen = 0, 0
    for sample in samples:
        races_seen += 1
        if any(not (row.get('jockey') or '').strip() for row in sample['rows']):
            races_missing += 1

    asof = J.AsOfRates(rows)
    attach_features(samples, history, asof)
    coverage = coverage_stats(samples, meta)
    correlation = correlation_stats(samples)
    print(f'[Feature] coverage {coverage["covered"]}/{coverage["runners"]} '
          f'({coverage["coverage"]:.1%}); r(score,jt)='
          f'{correlation["r_score_jockeyTrainer"]}')

    blocks = B.split_blocks(samples, H.TEST_FRAC, H.FOLDS)
    print(f'[Eval] walk-forward {len(blocks)} folds')
    evaluation = evaluate(samples, blocks)
    for name, d in evaluation['variants'].items():
        print(f"  blend {d['blend']}: dNLL={d['delta_nll']} CI={d['delta_ci']} "
              f"folds={d['folds']}")

    payload = {
        'generated_at': datetime.now(HKT).isoformat(),
        'jockey_completeness': {
            'runners': len(rows),
            'jockey_nonempty': round(jockey_nonempty / len(rows), 4) if rows else 0.0,
            'races_missing_jockey': races_missing,
            'races_checked': races_seen,
        },
        'coverage': coverage,
        'correlation': correlation,
        'evaluation': evaluation,
        'cache_meta': meta,
        'flags': {'jockey_upgrade': False},
    }

    json_path = os.path.join(args.out_dir, f'jockey_upgrade_{stamp}.json')
    with open(json_path, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    md_path = os.path.join(args.out_dir, f'jockey_upgrade_{stamp}.md')
    with open(md_path, 'w', encoding='utf-8') as fh:
        fh.write(build_report(payload))
    print(f'[Write] {os.path.basename(md_path)} | {os.path.basename(json_path)}')

    try:
        retry_supabase(lambda: supabase.table('pipeline_status').upsert({
            'id': STATUS_ID,
            'last_run': datetime.now(HKT).isoformat(),
            'status_json': {
                'coverage': coverage['coverage'],
                'correlation': correlation,
                'variants': {k: {'delta_nll': v['delta_nll'], 'delta_ci': v['delta_ci'],
                                 'folds': v['folds']}
                             for k, v in evaluation['variants'].items()},
                'flags': {'jockey_upgrade': False},
            },
        }, on_conflict='id').execute())
    except Exception as exc:
        print(f'[WARN] status not persisted: {exc}')
    return 0


if __name__ == '__main__':
    sys.exit(main())