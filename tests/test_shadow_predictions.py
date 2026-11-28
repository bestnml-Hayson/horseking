import pytest

import shadow_predictions as S
from model_config import FACTOR_KEYS, calibrate_p_model, fuse_race, market_probabilities


def test_odds_coverage_ignores_missing_and_placeholder_prices():
    assert S.odds_coverage([2.0, 3.0, None, 0.0, 1.0]) == (2, 5, 0.4)
    assert S.odds_coverage([]) == (0, 0, 0.0)


def test_gate_sparse_race_falls_back_to_model_only():
    p = [0.6, 0.4]
    finals, info = S.availability_gate({'min_coverage': 0.8}, p, [2.0, None])
    assert info['gate'] == 'sparse'
    assert info['coverage'] == pytest.approx(0.5)
    assert finals == pytest.approx(calibrate_p_model(p))
    assert sum(finals) == pytest.approx(1.0)


def test_gate_covered_race_matches_live_fusion():
    p = [0.6, 0.4]
    odds = [2.0, 3.0]
    finals, info = S.availability_gate({'min_coverage': 0.8}, p, odds)
    assert info['gate'] == 'covered'
    assert finals == pytest.approx(fuse_race(p, market_probabilities(odds), odds))


def test_gate_sparse_market_weight_blends_available_prices():
    p = [0.6, 0.4]
    finals, info = S.availability_gate(
        {'min_coverage': 0.8, 'sparse_market_weight': 0.5}, p, [2.0, None])
    assert info['gate'] == 'sparse'
    assert finals[0] == pytest.approx(0.5 * 0.6 + 0.5 * 1.0)
    assert finals[1] == pytest.approx(0.4)


def _factor_set(**overrides):
    factors = {k: 50.0 for k in FACTOR_KEYS}
    factors.update(overrides)
    return factors


def test_avail_aware_without_missing_inputs_matches_live():
    factors = [_factor_set(form=70.0), _factor_set(form=30.0)]
    availability = [{k: True for k in FACTOR_KEYS} for _ in range(2)]
    weights = {k: 1.0 / 9 for k in FACTOR_KEYS}
    odds = [2.0, 3.0]
    live_models = S.A._softmax(
        [sum(f[k] * weights[k] for k in FACTOR_KEYS) for f in factors])
    finals, info, meta = S.avail_aware({}, factors, availability, weights,
                                       live_models, odds)
    assert info['gate'] == 'always'
    assert all(m['missing'] == [] for m in meta)
    assert all(m['used_weight'] == pytest.approx(1.0) for m in meta)
    assert finals == pytest.approx(fuse_race(live_models, market_probabilities(odds), odds))


def test_avail_aware_drops_missing_factor_weight():
    factors = [_factor_set(form=80.0), _factor_set(form=20.0)]
    availability = [{k: True for k in FACTOR_KEYS}, {k: True for k in FACTOR_KEYS}]
    availability[0]['pace'] = False
    weights = {k: 1.0 / 9 for k in FACTOR_KEYS}
    finals, _, meta = S.avail_aware({}, factors, availability, weights, [0.5, 0.5], [2.0, 3.0])
    assert meta[0]['missing'] == ['pace']
    assert meta[0]['used_weight'] == pytest.approx(8.0 / 9, abs=1e-4)
    assert meta[1]['used_weight'] == pytest.approx(1.0)
    assert finals[0] > finals[1]


def _runner(rid, horse_id, odds, form_score=60):
    return {
        'runner_id': rid, 'horse_id': horse_id, 'draw': 1,
        'win_odds': odds, 'actual_weight': 122, 'rest_days': 28,
        'recent_form_score': form_score, 'jockey_win_rate': 0.1,
        'trainer_win_rate': 0.1, 'official_rating': 60,
    }


def test_race_shadow_records_both_columns_and_identity_draw():
    runners = [_runner(f'r{i}', f'h{i}', odds)
               for i, odds in enumerate([2.0, 4.0, 6.0, None])]
    experiments = {
        'availability_gate': {'enabled': False, 'min_coverage': 0.8,
                              'sparse_market_weight': 0.0},
        'avail_aware': {'enabled': False, 'min_coverage': 0.8},
        'draw_v2': {'enabled': False},
    }
    record = S.race_shadow(runners, 'ST', 1200, 'Class 4', '2026-12-02', {},
                           race_no=1, experiments=experiments)
    assert record['meta']['covered'] == 3
    assert record['meta']['odds_coverage'] == pytest.approx(0.75)
    assert record['shadow']['availability_gate']['meta']['gate'] == 'sparse'
    for rid, live in record['live'].items():
        assert record['shadow']['draw_v2']['runners'][rid]['p_final'] == live['p_final']
        assert rid in record['shadow']['availability_gate']['runners']
        assert rid in record['shadow']['avail_aware']['runners']
        assert rid in record['shadow']['jockey_upgrade']['runners']
        assert rid in record['shadow']['speed_engine']['runners']
    assert record['flags'] == {'availability_gate': False, 'draw_v2': False,
                               'avail_aware': False, 'jockey_upgrade': False,
                               'speed_engine': False}
    gate = record['shadow']['availability_gate']['runners']['r0']['p_final']
    assert gate == pytest.approx(record['live']['r0']['p_model'], abs=5e-5)


def test_race_shadow_jockey_upgrade_records_feature():
    runners = [_runner('r0', 'h0', 2.0), _runner('r1', 'h1', 4.0)]
    runners[0]['jockey'] = 'A'
    runners[0]['jockey_win_rate'] = 0.2
    runners[1]['jockey'] = 'B'
    runners[1]['jockey_win_rate'] = 0.05
    history = {
        'h0': [{'jockey': 'C', 'race_date': '2026-01-01', 'jockey_win_rate': 0.1}],
        'h1': [{'jockey': 'D', 'race_date': '2026-01-01', 'jockey_win_rate': 0.1}],
    }
    experiments = {'jockey_upgrade': {'enabled': False, 'blend': 0.15,
                                      'prior_window': 6}}
    record = S.race_shadow(runners, 'ST', 1200, 'Class 4', '2026-12-02', history,
                           race_no=1, experiments=experiments)
    ju = record['shadow']['jockey_upgrade']
    assert ju['meta']['covered'] == 2
    assert ju['runners']['r0']['score'] == pytest.approx(100.0)
    assert ju['runners']['r1']['score'] == pytest.approx(25.0)
    assert record['flags']['jockey_upgrade'] is False
    # the live column must not consume the shadow feature
    assert record['live']['r0']['p_final'] != ju['runners']['r0']['p_final']


def test_race_shadow_speed_engine_compares_ranks_without_touching_live():
    runners = [_runner(f'r{i}', f'h{i}', 2.0 + i) for i in range(4)]
    for runner, raw in zip(runners, ['1.08.00', '1.09.00', '1.10.00', '1.11.00']):
        runner['best_time'] = raw
    experiments = {'speed_engine': {'enabled': False, 'mode': 'display_only'}}
    record = S.race_shadow(runners, 'ST', 1200, 'Class 4', '2026-12-02', {},
                           race_no=1, experiments=experiments)
    speed = record['shadow']['speed_engine']
    assert speed['meta']['comparable'] is True
    assert speed['meta']['has_best_time'] == 4
    ranks = {rid: row['speed_rank'] for rid, row in speed['runners'].items()}
    assert ranks == {'r0': 1, 'r1': 2, 'r2': 3, 'r3': 4}
    assert all(row['model_rank'] is not None for row in speed['runners'].values())
    assert record['flags']['speed_engine'] is False

    for runner in runners:
        runner.pop('best_time')
    without = S.race_shadow(runners, 'ST', 1200, 'Class 4', '2026-12-02', {},
                            race_no=1, experiments=experiments)
    assert without['shadow']['speed_engine']['meta']['comparable'] is False
    assert without['live'] == record['live']
    assert all(row['speed_rank'] is None
               for row in without['shadow']['speed_engine']['runners'].values())


def test_race_shadow_handles_empty_field():
    assert S.race_shadow([], 'HV', 1650, None, '2026-12-02', {}) is None