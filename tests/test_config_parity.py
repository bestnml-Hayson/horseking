import json
import os

import model_config as M

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, 'config', 'model_profiles.json')


def _profile():
    with open(CONFIG, encoding='utf-8') as fh:
        data = json.load(fh)
    assert data['default_profile'] == 'current_v586'
    return data['profiles'][data['default_profile']]


def test_python_constants_match_shared_config():
    prof = _profile()
    assert M.MODEL_WEIGHT == prof['fusion']['model_weight']
    assert M.MARKET_WEIGHT == prof['fusion']['market_weight']
    assert M.MARKET_GAMMA == prof['fusion']['market_gamma']
    assert M.SOFTMAX_TEMPERATURE == prof['model']['softmax_temperature']
    assert M.CALIBRATION_POWER == prof['model']['calibration_power']
    assert M.EXTREME_ODDS_ALPHA == prof['fusion']['extreme_odds_alpha']
    assert tuple(prof['fusion']['extreme_odds_band']) == M.EXTREME_ODDS_BAND
    assert M.FORM_SHRINK_K == prof['factors']['form_shrink_k']
    assert M.FORM_SHRINK_PRIOR == prof['factors']['form_shrink_prior']
    assert M.RATING_BLEND == prof['factors']['rating_blend']
    assert M.DRAW_K_HV == prof['factors']['draw_k']['HV']
    assert M.DRAW_K_ST_SPRINT == prof['factors']['draw_k']['ST_sprint']
    assert M.DRAW_K_ST_ROUTE == prof['factors']['draw_k']['ST_route']
    assert M.RAW_WEIGHTS_ST == prof['weights']['ST']
    assert M.RAW_WEIGHTS_HV == prof['weights']['HV']


def test_ts_engine_reads_the_same_json_instead_of_a_second_copy():
    with open(os.path.join(ROOT, 'lib', 'race-utils.ts'), encoding='utf-8') as fh:
        source = fh.read()
    assert 'config/model_profiles.json' in source
    assert 'modelProfiles' in source
    # The constants must not be re-hardcoded next to the loader.
    for literal in ('const MODEL_WEIGHT = 0.2', 'const MARKET_GAMMA = 1.0',
                    'const SOFTMAX_TEMPERATURE = 8', 'const DRAW_K_HV = 0.9'):
        assert literal not in source