import math

import pytest

import model_config as M


CURRENT_WEIGHTS = {
    'HV': {'form': 0.20, 'draw': 0.18, 'jockeyTrainer': 0.12, 'weight': 0.08,
           'courseDistance': 0.14, 'restDays': 0.06, 'gear': 0.03, 'pace': 0.14,
           'classMov': 0.05},
    'ST': {'form': 0.22, 'draw': 0.12, 'jockeyTrainer': 0.13, 'weight': 0.10,
           'courseDistance': 0.16, 'restDays': 0.06, 'gear': 0.03, 'pace': 0.12,
           'classMov': 0.06},
}


def test_default_profile_is_current_v586():
    assert M.PROFILE_NAME == 'current_v586'
    assert M.MODEL_WEIGHT == pytest.approx(0.2)
    assert M.MARKET_WEIGHT == pytest.approx(0.8)
    assert M.MARKET_GAMMA == pytest.approx(1.0)
    assert M.SOFTMAX_TEMPERATURE == pytest.approx(8.0)
    assert M.CALIBRATION_METHOD == 'temperature'
    assert M.CALIBRATION_POWER == pytest.approx(1.0)
    assert M.EXTREME_ODDS_ALPHA == pytest.approx(0.35)
    assert M.EXTREME_ODDS_BAND == (1.8, 25.0)
    assert M.FORM_SHRINK_K == pytest.approx(2.5)
    assert M.FORM_SHRINK_PRIOR == pytest.approx(6.5)
    assert M.RATING_BLEND == pytest.approx(0.35)
    assert M.DRAW_K_HV == pytest.approx(0.9)
    assert M.DRAW_K_ST_SPRINT == pytest.approx(0.7)
    assert M.DRAW_K_ST_ROUTE == pytest.approx(0.55)
    assert M.DRAW_ST_ROUTE_MIN_DISTANCE == 1600


def test_default_weights_match_v586_tables():
    for venue, table in CURRENT_WEIGHTS.items():
        resolved = M.raw_weights_for(venue)
        assert set(resolved) == set(M.FACTOR_KEYS)
        for key, value in table.items():
            assert resolved[key] == pytest.approx(value, abs=1e-9), f'{venue}.{key}'
        assert sum(resolved.values()) == pytest.approx(1.0, abs=1e-6)


def test_all_profiles_validate():
    assert M.validate_profiles() == []


def test_honest_profile_flags_leakage_controls():
    honest = M.resolve_profile('honest_v586')
    assert honest['evaluation']['as_of_jockey_trainer_rates'] is True
    assert honest['evaluation']['fold_train_only_weights'] is True
    assert honest['evaluation']['odds_source'] == 'labeled'
    # Same model constants as the deployed profile.
    assert honest['fusion'] == M.PROFILE['fusion'] or (
        honest['fusion'] == M.resolve_profile('current_v586')['fusion'])
    assert honest['weights'] == M.resolve_profile('current_v586')['weights']


def test_legacy_profile_reproduces_v576_baseline():
    legacy = M.resolve_profile('legacy_v576')
    assert legacy['fusion']['market_gamma'] == pytest.approx(1.3)
    assert legacy['fusion']['extreme_odds_alpha'] == pytest.approx(0.2)
    assert legacy['factors']['form_shrink_k'] == 0
    assert legacy['factors']['rating_blend'] == 0
    assert legacy['factors']['draw_k'] == {'HV': 1.0, 'ST_sprint': 1.0, 'ST_route': 1.0, 'ST_1000': 0.0}
    expected = {
        'HV': {'form': 0.2308, 'draw': 0.1795, 'jockeyTrainer': 0.1538, 'weight': 0.0,
               'courseDistance': 0.2051, 'restDays': 0.1282, 'gear': 0.0, 'pace': 0.0,
               'classMov': 0.1026},
        'ST': {'form': 0.2105, 'draw': 0.1053, 'jockeyTrainer': 0.1842, 'weight': 0.0,
               'courseDistance': 0.2368, 'restDays': 0.1316, 'gear': 0.0, 'pace': 0.0,
               'classMov': 0.1316},
    }
    for venue in ('HV', 'ST'):
        table = legacy['weights'][venue]
        for key in ('weight', 'gear', 'pace'):
            assert table[key] == 0, f'{venue}.{key} must stay dead in legacy_v576'
        for key, value in expected[venue].items():
            assert table[key] == pytest.approx(value), f'{venue}.{key}'
        assert sum(table.values()) == pytest.approx(1.0, abs=1e-4)


def test_experiment_profiles_are_opt_in():
    current = M.resolve_profile('current_v586')
    for name in M.profile_names():
        if not name.startswith('exp_'):
            continue
        profile = M.resolve_profile(name)
        enabled = [k for k, v in profile['experiments'].items() if v['enabled']]
        assert enabled, name
        for key in enabled:
            assert current['experiments'][key]['enabled'] is False, key
    for key, value in current['experiments'].items():
        assert value['enabled'] is False, key


def test_market_probabilities_de_vig():
    probs = M.market_probabilities([2.0, 4.0])
    assert probs[0] == pytest.approx(2 / 3)
    assert probs[1] == pytest.approx(1 / 3)
    assert sum(probs) == pytest.approx(1.0)


def test_market_probabilities_missing_odds_stay_zero():
    probs = M.market_probabilities([None, 2.0])
    assert probs[0] == 0
    assert probs[1] == pytest.approx(1.0)
    assert M.market_probabilities([None, None]) == pytest.approx([0.5, 0.5])


def test_fuse_race_alpha_and_missing_market():
    fused = M.fuse_race([0.6, 0.4], [0.5, 0.5], [3.0, 3.0])
    assert fused[0] == pytest.approx(0.52)
    assert fused[1] == pytest.approx(0.48)
    extreme = M.fuse_race([0.6, 0.4], [0.5, 0.5], [1.5, 3.0])
    assert extreme[0] == pytest.approx(0.35 * 0.6 + 0.65 * 0.5)
    assert extreme[1] == pytest.approx(0.48)
    model_only = M.fuse_race([0.6, 0.4], [None, None], [None, None])
    assert model_only == pytest.approx([0.6, 0.4])


def test_calibration_is_identity_in_default_profile():
    p = [0.1, 0.2, 0.7]
    assert M.calibrate_p_model(p) == pytest.approx(p)
    assert math.isclose(sum(M.calibrate_p_model(p)), 1.0)


def test_unknown_profile_raises():
    with pytest.raises(KeyError):
        M.resolve_profile('does_not_exist')