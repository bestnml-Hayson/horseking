#!/usr/bin/env python3
"""Reusable A/B statistics for the v5.86 gates.

Pure functions only: no data loading, no DB access, no verdicts are produced
here. Callers pass per-fold deltas (e.g. NLL_variant - NLL_baseline, negative
is better) and bucket sample sizes, and get the same three checks every flag
must pass: bootstrap CI, >=4/5 folds improved, bucket guardrails.
"""
import random
from statistics import mean

DEFAULT_BOOTSTRAP = 1000
DEFAULT_SEED = 42


def _quantile(sorted_values, q):
    if not sorted_values:
        raise ValueError('empty sample')
    idx = min(len(sorted_values) - 1, max(0, int(round(q * (len(sorted_values) - 1)))))
    return sorted_values[idx]


def bootstrap_ci(values, n_boot=DEFAULT_BOOTSTRAP, alpha=0.05, seed=DEFAULT_SEED):
    """Percentile bootstrap CI of the mean."""
    vals = [float(v) for v in values]
    if not vals:
        raise ValueError('bootstrap_ci needs at least one value')
    rng = random.Random(seed)
    n = len(vals)
    means = sorted(mean(vals[rng.randrange(n)] for _ in range(n)) for _ in range(n_boot))
    return {
        'mean': mean(vals),
        'lo': _quantile(means, alpha / 2),
        'hi': _quantile(means, 1 - alpha / 2),
        'n': n,
        'n_boot': n_boot,
        'alpha': alpha,
    }


def fold_verdict(fold_deltas, min_improved=4):
    """Count folds whose mean delta is negative (better than baseline)."""
    means = [mean([float(v) for v in fold]) for fold in fold_deltas if len(fold)]
    improved = sum(1 for m in means if m < 0)
    return {
        'fold_means': means,
        'improved': improved,
        'total': len(means),
        'min_improved': min_improved,
        'passed': improved >= min_improved,
    }


def bucket_sample_check(buckets, min_races=30, min_runners=300):
    """Each bucket passes if it has >= min_races or >= min_runners."""
    detail = {}
    for label, counts in buckets.items():
        races = int(counts.get('races', 0))
        runners = int(counts.get('runners', 0))
        detail[label] = {
            'races': races,
            'runners': runners,
            'ok': races >= min_races or runners >= min_runners,
        }
    return {
        'buckets': detail,
        'failed': [label for label, d in detail.items() if not d['ok']],
        'passed': all(d['ok'] for d in detail.values()),
    }


def evaluate_variant(deltas_by_fold, buckets=None, min_fold_improved=4,
                     required_folds=5, min_races=30, min_runners=300,
                     n_boot=DEFAULT_BOOTSTRAP, seed=DEFAULT_SEED):
    """Combine the three gates. Negative delta = variant better.

    passed == CI entirely below zero AND >= 4/5 folds better AND all buckets
    meet the sample guardrail (when buckets are supplied).
    """
    flat = [float(v) for fold in deltas_by_fold for v in fold]
    ci = bootstrap_ci(flat, n_boot=n_boot, seed=seed)
    folds = fold_verdict(deltas_by_fold, min_improved=min_fold_improved)
    buckets_result = bucket_sample_check(
        buckets or {}, min_races=min_races, min_runners=min_runners)

    reasons = []
    if ci['hi'] >= 0:
        reasons.append('CI 未全負')
    if folds['total'] < required_folds:
        reasons.append(f"fold 數不足（{folds['total']} < {required_folds}）")
    if not folds['passed']:
        reasons.append(f"改善 fold {folds['improved']}/{folds['total']} < {min_fold_improved}")
    if buckets and not buckets_result['passed']:
        reasons.append('分桶樣本不足: ' + ', '.join(buckets_result['failed']))

    return {
        'ci': ci,
        'folds': folds,
        'buckets': buckets_result if buckets else None,
        'passed': not reasons,
        'reasons': reasons,
    }