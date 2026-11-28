from datetime import date

import pytest

import monthly_data_audit as M


def _record(sparse, draw_diff=0.0, aware_diff=0.0, coverage=None):
    live = {'r1': {'p_model': 0.5, 'p_final': 0.5}}
    cov = coverage if coverage is not None else (0.0 if sparse else 0.9)
    return {
        'live': live,
        'shadow': {
            'availability_gate': {'meta': {'gate': 'sparse' if sparse else 'covered',
                                           'coverage': cov}},
            'draw_v2': {'runners': {'r1': {'p_final': 0.5 + draw_diff}}},
            'avail_aware': {'runners': {'r1': {'p_final': 0.5 + aware_diff}}},
        },
    }


def test_summarize_shadow_counts_gate_triggers_and_drift():
    state = {'races': {'a': _record(True, aware_diff=0.02),
                       'b': _record(False)}}
    summary = M.summarize_shadow(state)
    assert summary['races'] == 2
    assert summary['gate_sparse'] == 1
    assert summary['gate_covered'] == 1
    assert summary['sparse_coverages'] == [0.0]
    assert summary['draw_identity_max_diff'] == 0.0
    assert summary['avail_aware_mean_abs_diff'] == pytest.approx(0.01)
    assert summary['no_variance'] is False
    assert summary['all_sparse_unpriced'] is True

    partial = M.summarize_shadow({'races': {'a': _record(True, coverage=0.5)}})
    assert partial['all_sparse_unpriced'] is False

    quiet = M.summarize_shadow({'races': {'a': _record(False)}})
    assert quiet['no_variance'] is True
    assert quiet['all_sparse_unpriced'] is False
    assert M.summarize_shadow({})['no_variance'] is False


def test_fallback_sizes_report_raw_and_gzip():
    state = {'races': {f'R{i}': {'rows': {f'h{j}': {'odds': 3.4} for j in range(20)}}
                       for i in range(50)}}
    sizes = M.fallback_sizes(state)
    assert sizes['raw_bytes'] > sizes['gzip_bytes'] > 0


def test_compression_advice_thresholds():
    assert '低於 512 KB' in M.compression_advice(1024)
    assert '壓縮／歸檔' in M.compression_advice(M.FALLBACK_WARN_BYTES)
    assert '立即 gzip' in M.compression_advice(M.FALLBACK_CRIT_BYTES)


def test_months_since_and_escalation():
    start = date(2026, 11, 28)
    assert M.months_since(start, date(2026, 11, 28)) == 0
    assert M.months_since(start, date(2027, 2, 27)) == 2
    assert M.months_since(start, date(2027, 2, 28)) == 3
    assert M.months_since(start, date(2026, 11, 1)) == 0

    assert 'DB 表可用' in M.escalation_status(True, 6)
    assert '未滿 3 個月' in M.escalation_status(False, 1)
    assert 'staging' in M.escalation_status(False, 3)
    assert '第三方 storage' in M.escalation_status(False, 3)


def test_render_monthly_contains_gate_shadow_and_risks_checklist():
    audit = {
        'generated': '2026-11-28',
        'progress': {'complete_pre_race_races': 0, 'partial_races': 0,
                     'total_races': 0, 'target': 50,
                     'missing_reason_counts': {}, 'store': 'pipeline_status'},
        'table_ready': False,
        'fallback': {'raw_bytes': 2048, 'gzip_bytes': 900},
        'shadow': {'races': 4, 'gate_sparse': 0, 'gate_covered': 4,
                   'sparse_coverages': [],
                   'draw_identity_max_diff': 0.0,
                   'avail_aware_mean_abs_diff': 0.0, 'no_variance': True,
                   'all_sparse_unpriced': False},
        'migration_present': True,
        'months_elapsed': 0,
        'escalation': 'fallback 收集第 1 個月（未滿 3 個月）：繼續觀察，按月重檢。',
        'daily_report': None,
        'weekly_report': None,
    }
    md = M.render_monthly_markdown(audit)
    assert '0/50' in md
    assert 'shadow 無變異' in md
    assert 'R5' in md and 'R3' in md
    assert '未滿 3 個月' in md