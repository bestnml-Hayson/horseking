from ai_review import _prior_starts
from backtest_models import split_blocks
from backtest_honest import build_asof_rates, jt_score


def _samples(n):
    return [{'race_id': f'r{i:02d}', 'date': f'2026-01-{i + 1:02d}'} for i in range(n)]


def test_split_blocks_is_chronological():
    samples = _samples(20)
    blocks = split_blocks(samples, test_frac=0.4, folds=5)
    assert len(blocks) == 5
    seen_test = []
    for train, test in blocks:
        assert train and test
        assert max(s['date'] for s in train) < min(s['date'] for s in test)
        seen_test.extend(s['race_id'] for s in test)
    assert seen_test == [s['race_id'] for s in samples[12:]]


def test_split_blocks_never_leaks_future_into_train():
    samples = _samples(60)
    for train, test in split_blocks(samples, test_frac=0.4, folds=5):
        train_ids = {s['race_id'] for s in train}
        assert not (train_ids & {s['race_id'] for s in test})


def test_prior_starts_excludes_same_day_result():
    history = [
        {'race_date': '2026-02-01', 'finish_position': 1},
        {'race_date': '2026-01-15', 'finish_position': 3},
    ]
    prior = _prior_starts(history, '2026-02-01')
    assert prior == [history[1]]
    assert _prior_starts(history, '2026-03-01') == history
    assert _prior_starts(history, None) == history


def test_asof_rates_ignore_same_day_results():
    races = [{'race_id': 'r1', 'race_date': '2026-01-01'},
             {'race_id': 'r2', 'race_date': '2026-01-08'}]
    by_race = {
        'r1': [{'runner_id': 'a', 'jockey': 'J', 'trainer': 'T', 'finish_position': 1},
               {'runner_id': 'b', 'jockey': 'K', 'trainer': 'T', 'finish_position': 2}],
        'r2': [{'runner_id': 'c', 'jockey': 'J', 'trainer': 'T', 'finish_position': 1}],
    }
    rates = build_asof_rates(races, by_race)
    # Day 1 has no earlier history -> no rate yet.
    assert rates[('jockey', 'a')] == (None, 0)
    # Day 2 sees both day-1 runners: jockey J 1/1, K 0/1 (min 3 starts not met).
    assert rates[('jockey', 'c')] == (None, 1)
    assert rates[('trainer', 'c')] == (None, 2)


def test_jt_score_matches_factor_formula():
    assert jt_score(None, None) == jt_score(0.1, 0.1) == 50.0
    assert jt_score(0.2, 0.1) == 100.0 * 0.6 + 50.0 * 0.4
    assert jt_score(1.0, 1.0) == 100.0