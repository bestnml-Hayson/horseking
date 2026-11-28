import stat_eval as S


def test_bootstrap_ci_of_constant_is_degenerate():
    ci = S.bootstrap_ci([1.0] * 20)
    assert ci['mean'] == 1.0
    assert ci['lo'] == 1.0 and ci['hi'] == 1.0
    assert ci['n'] == 20


def test_bootstrap_ci_signs_and_determinism():
    negative = S.bootstrap_ci([-0.01] * 40)
    assert negative['hi'] < 0
    positive = S.bootstrap_ci([0.01] * 40)
    assert positive['lo'] > 0
    mixed = S.bootstrap_ci([-0.02, 0.02] * 20)
    assert mixed['lo'] < 0 < mixed['hi']
    assert mixed == S.bootstrap_ci([-0.02, 0.02] * 20)


def test_fold_verdict_needs_four_of_five():
    assert S.fold_verdict([[-0.1], [-0.1], [-0.1], [-0.1], [0.1]])['passed'] is True
    assert S.fold_verdict([[-0.1], [-0.1], [-0.1], [0.1], [0.1]])['passed'] is False


def test_bucket_sample_check_races_or_runners():
    result = S.bucket_sample_check({
        'by_races': {'races': 30, 'runners': 50},
        'by_runners': {'races': 5, 'runners': 300},
        'too_small': {'races': 5, 'runners': 50},
    })
    assert result['passed'] is False
    assert result['failed'] == ['too_small']
    assert result['buckets']['by_runners']['ok'] is True


def test_evaluate_variant_pass_and_fail_paths():
    good = S.evaluate_variant([[-0.01] * 40] * 5,
                              buckets={'all': {'races': 40, 'runners': 480}})
    assert good['passed'] is True
    assert good['reasons'] == []

    weak_folds = S.evaluate_variant(
        [[-0.01] * 40, [-0.01] * 40, [-0.01] * 40, [0.01] * 40, [0.01] * 40],
        buckets={'all': {'races': 40, 'runners': 480}})
    assert weak_folds['passed'] is False
    assert any('改善 fold' in reason for reason in weak_folds['reasons'])

    small_bucket = S.evaluate_variant(
        [[-0.01] * 40] * 5,
        buckets={'tiny': {'races': 3, 'runners': 20}})
    assert small_bucket['passed'] is False
    assert any('分桶' in reason for reason in small_bucket['reasons'])

    not_enough_folds = S.evaluate_variant([[-0.01] * 40] * 3)
    assert not_enough_folds['passed'] is False
    assert any('fold 數不足' in reason for reason in not_enough_folds['reasons'])