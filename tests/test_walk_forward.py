from ai_review import _prior_starts
from backtest_models import split_blocks


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