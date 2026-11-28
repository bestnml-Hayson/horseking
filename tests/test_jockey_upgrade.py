import pytest

import jockey_upgrade as J


def _run(jockey, date, fp=1):
    return {'jockey': jockey, 'race_date': date, 'finish_position': fp}


def test_asof_rate_uses_only_strictly_earlier_races():
    rows = [
        _run('A', '2026-01-01', 1),
        _run('A', '2026-01-02', 3),
        _run('A', '2026-01-03', 1),
        _run('A', '2026-01-04', 1),
    ]
    asof = J.AsOfRates(rows, min_starts=2)
    assert asof.rate('A', '2026-01-01') == (None, 0)
    assert asof.rate('A', '2026-01-03') == (pytest.approx(0.5), 2)
    # a win on the race day itself must not enter the same day's rate
    assert asof.rate('A', '2026-01-04') == (pytest.approx(2 / 3), 3)
    assert asof.rate('A', '2026-01-05') == (pytest.approx(0.75), 4)


def test_asof_rate_min_starts_and_unknown_jockey():
    rows = [_run('B', '2026-02-01', 1), _run('B', '2026-02-02', 2)]
    asof = J.AsOfRates(rows)
    assert asof.rate('B', '2026-03-01') == (None, 2)
    assert asof.rate('Nobody', '2026-03-01') == (None, 0)


def test_future_results_never_change_past_rates():
    past = [_run('C', '2026-01-01', 1), _run('C', '2026-01-02', 2),
            _run('C', '2026-01-03', 1)]
    base = J.AsOfRates(past)
    with_future = J.AsOfRates(past + [_run('C', '2026-06-01', 1)])
    assert base.rate('C', '2026-02-01') == with_future.rate('C', '2026-02-01')


def test_feature_delta_and_score():
    asof = J.AsOfRates([
        _run('NEW', '2026-01-01', 1), _run('NEW', '2026-01-02', 1),
        _run('NEW', '2026-01-03', 2),
        _run('OLD', '2026-01-01', 3), _run('OLD', '2026-01-02', 4),
        _run('OLD', '2026-01-03', 5),
    ])
    history = [{'jockey': 'OLD', 'race_date': '2026-01-10'},
               {'jockey': 'OLD', 'race_date': '2026-01-20'}]
    fv = J.feature_asof(asof, 'NEW', history, '2026-02-01')
    assert fv['current_rate'] == pytest.approx(2 / 3, abs=1e-4)
    assert fv['prior_mean'] == pytest.approx(0.0)
    assert fv['delta'] == pytest.approx(2 / 3, abs=1e-4)
    assert fv['score'] == 100.0
    assert fv['prior_runs'] == 2 and fv['prior_rated'] == 2


def test_feature_returns_none_without_current_rate_or_prior_rated_runs():
    asof = J.AsOfRates([_run('D', '2026-01-01', 1)])
    assert J.feature_asof(asof, 'D', [], '2026-02-01')['score'] is None
    assert J.feature_asof(asof, 'D', [{'jockey': 'D', 'race_date': '2026-01-05'}],
                          '2026-02-01')['score'] is None
    # prior runs exist but their jockeys have <3 starts
    fv = J.feature_asof(asof, 'D', [{'jockey': 'E', 'race_date': '2026-01-05'}],
                        '2026-02-01')
    assert fv['prior_runs'] == 1 and fv['prior_rated'] == 0
    assert fv['score'] is None


def test_prior_window_keeps_last_six_runs():
    asof = J.AsOfRates([
        _run('J', '2026-01-01', 1), _run('J', '2026-01-02', 1),
        _run('J', '2026-01-03', 1),
        _run('K', '2026-01-01', 2), _run('K', '2026-01-02', 2),
    ])
    history = [{'jockey': 'J', 'race_date': f'2026-01-{d:02d}'} for d in range(1, 9)]
    fv = J.feature_asof(asof, 'K', history, '2026-02-01', prior_window=6)
    assert fv['prior_runs'] == 6
    assert fv['prior_rated'] == 6


def test_feature_from_stored_uses_recorded_rates():
    history = [
        {'jockey': 'X', 'race_date': '2026-01-01', 'jockey_win_rate': 0.1},
        {'jockey': 'Y', 'race_date': '2026-01-02', 'jockey_win_rate': 0.2},
        {'jockey': 'Z', 'race_date': '2026-01-03', 'jockey_win_rate': None},
    ]
    fv = J.feature_from_stored('N', 0.2, history, '2026-02-01')
    assert fv['prior_rated'] == 2
    assert fv['prior_mean'] == pytest.approx(0.15)
    assert fv['delta'] == pytest.approx(0.05)
    assert fv['score'] == pytest.approx(75.0)


def test_pearson_known_values():
    assert J.pearson([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert J.pearson([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    assert J.pearson([1, None, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)
    assert J.pearson([1, None, 3], [1, 2, 3]) is None
    assert J.pearson([1, 1, 1], [1, 2, 3]) is None