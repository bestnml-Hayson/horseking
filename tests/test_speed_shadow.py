import pytest

import speed_shadow as S


def test_parse_best_time_formats_and_range():
    assert S.parse_best_time('1.09.20') == pytest.approx(69.2)
    assert S.parse_best_time('1:09.20') == pytest.approx(69.2)
    assert S.parse_best_time(69.2) == pytest.approx(69.2)
    assert S.parse_best_time(None) is None
    assert S.parse_best_time('') is None
    assert S.parse_best_time('bad') is None
    assert S.parse_best_time('0.39.99') is None  # below 40s gate
    assert S.parse_best_time('4.00.00') is None  # above 240s gate


def test_ranks_competition_ties_and_nulls():
    assert S.ranks([0.9, 0.8, 0.9, None]) == [1, 3, 1, None]
    assert S.ranks([0.1, 0.2, 0.3], lower_is_better=True) == [1, 2, 3]
    assert S.ranks([None, None]) == [None, None]


def test_speed_scores_fastest_is_100_and_missing_stays_null():
    scores = S.speed_scores([69.0, 70.0, None, 71.0])
    assert scores[0] == pytest.approx(100.0)
    assert scores[3] == pytest.approx(0.0)
    assert scores[2] is None
    assert S.speed_scores([69.0, 69.0]) == [None, None]


def test_compare_runners_below_min_field_keeps_ranks_null():
    meta, rows = S.compare_runners(['1.09.20', None, '1.10.00'], [1, 2, 3])
    assert meta['has_best_time'] == 2
    assert meta['comparable'] is False
    assert all(r['speed_rank'] is None for r in rows)
    assert all(r['speed_score'] is None for r in rows)
    assert rows[0]['best_time_sec'] == pytest.approx(69.2)


def test_compare_runners_records_ranks_delta_and_correlation():
    times = ['1.08.00', '1.09.00', '1.10.00', '1.11.00', None]
    model_ranks = [1, 2, 3, 4, 5]
    meta, rows = S.compare_runners(times, model_ranks)
    assert meta['comparable'] is True
    assert meta['has_best_time'] == 4
    assert meta['coverage'] == pytest.approx(0.8)
    assert rows[0]['speed_rank'] == 1 and rows[0]['speed_score'] == pytest.approx(100.0)
    assert rows[3]['speed_rank'] == 4 and rows[3]['speed_score'] == pytest.approx(0.0)
    assert rows[0]['rank_delta'] == 0
    assert rows[4]['speed_rank'] is None and rows[4]['rank_delta'] is None
    assert meta['rank_corr'] == pytest.approx(1.0)

    reversed_meta, _ = S.compare_runners(times, [4, 3, 2, 1, None])
    assert reversed_meta['rank_corr'] == pytest.approx(-1.0)


def test_spearman_ties_and_flat_fields():
    # all tied on one side -> zero variance -> None, not a fake 0
    assert S.spearman([1, 1, 1, 1], [1, 2, 3, 4]) is None
    assert S.spearman([1, None, 3], [1, 2, 3]) is None  # <4 pairs
    rho = S.spearman([1, 2, 2, 3], [1, 2, 3, 4])
    assert rho is not None and 0.8 < rho < 1.0