"""Fusion / scoring constants shared by every Python engine.

Single source of truth: config/model_profiles.json. lib/race-utils.ts loads the
same file, so the browser, the post-race review and the backtests cannot drift.

The default profile is current_v586 (the deployed v5.86 constants). legacy_v576
reproduces the old v5.76 baseline; honest_v586 reuses the v5.86 constants but
evaluates them without leakage (as-of jockey/trainer rates, fold-train-only
weights, labelled odds). exp_* profiles switch one Phase 1/2 experiment at a
time and are all off by default.

scripts/recalibrate_weights.py may publish a fitted table to weights_active.json;
when that file validates, it overrides the profile's hand-set tables for every
Python engine. The browser reads the same numbers from
pipeline_status.model_weights_active.
"""
import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'model_profiles.json')

_FEATURE_KEYS = ('form_shrink', 'rating_blend', 'draw_field_size', 'run_style_pace',
                 'extreme_odds_alpha', 'calibration')
_EXPERIMENT_KEYS = ('segmented_gamma', 'platt', 'availability_renorm',
                    'timing_fusion', 'extreme_favourite_guard', 'dual_probability',
                    'st1000_draw_reversal', 'speed_engine', 'finish_time_margin')
_CALIBRATION_METHODS = ('none', 'temperature', 'platt', 'isotonic')
_ODDS_SOURCES = ('sp', 'labeled', 'pre_race')

FACTOR_KEYS = ('form', 'draw', 'jockeyTrainer', 'weight', 'courseDistance',
               'restDays', 'gear', 'pace', 'classMov')

ACTIVE_WEIGHTS_PATH = os.path.join(os.path.dirname(__file__), 'weights_active.json')
_active_cache = None


def load_profiles():
    """Raw JSON as shipped. Callers should normally use resolve_profile()."""
    with open(CONFIG_PATH, encoding='utf-8') as fh:
        return json.load(fh)


def _deep_merge(base, override):
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def resolve_profile(name, raw=None):
    """Resolve one profile, following `extends` chains (child wins per key)."""
    raw = raw if raw is not None else load_profiles()
    profiles = raw.get('profiles') or {}
    seen = []
    current = name
    chain = []
    while True:
        if current in seen:
            raise ValueError(f'profile inheritance cycle: {" -> ".join(seen + [current])}')
        seen.append(current)
        if current not in profiles:
            raise KeyError(f'unknown model profile: {current}')
        spec = profiles[current]
        chain.append(spec)
        parent = spec.get('extends')
        if not parent:
            break
        current = parent
    resolved = {}
    for spec in reversed(chain):
        resolved = _deep_merge(resolved, {k: v for k, v in spec.items() if k != 'extends'})
    resolved['name'] = name
    return resolved


def profile_names(raw=None):
    raw = raw if raw is not None else load_profiles()
    return list((raw.get('profiles') or {}).keys())


PROFILE_NAME = os.environ.get('MODEL_PROFILE') or load_profiles().get('default_profile')
PROFILE = resolve_profile(PROFILE_NAME)
FEATURES = dict(PROFILE['features'])
EXPERIMENTS = dict(PROFILE['experiments'])
EVALUATION = dict(PROFILE['evaluation'])

_FUSION = PROFILE['fusion']
_MODEL = PROFILE['model']
_FACTORS = PROFILE['factors']

MODEL_WEIGHT = float(_FUSION['model_weight'])
MARKET_WEIGHT = float(_FUSION['market_weight'])
MARKET_GAMMA = float(_FUSION['market_gamma'])
EXTREME_ODDS_ALPHA = float(_FUSION['extreme_odds_alpha'])
EXTREME_ODDS_BAND = (float(_FUSION['extreme_odds_band'][0]), float(_FUSION['extreme_odds_band'][1]))

SOFTMAX_TEMPERATURE = float(_MODEL['softmax_temperature'])
CALIBRATION_METHOD = str(_MODEL['calibration_method'])
CALIBRATION_TEMPERATURE = float(_MODEL['calibration_temperature'])
CALIBRATION_POWER = float(_MODEL['calibration_power'])

FORM_SHRINK_K = float(_FACTORS['form_shrink_k'])
FORM_SHRINK_PRIOR = float(_FACTORS['form_shrink_prior'])
RATING_BLEND = float(_FACTORS['rating_blend'])
DRAW_ST_ROUTE_MIN_DISTANCE = int(_FACTORS['draw_st_route_min_distance'])
DRAW_K_HV = float(_FACTORS['draw_k']['HV'])
DRAW_K_ST_SPRINT = float(_FACTORS['draw_k']['ST_sprint'])
DRAW_K_ST_ROUTE = float(_FACTORS['draw_k']['ST_route'])
DRAW_K_ST_1000 = float(_FACTORS['draw_k']['ST_1000'])

RAW_WEIGHTS_ST = {k: float(PROFILE['weights']['ST'][k]) for k in FACTOR_KEYS}
RAW_WEIGHTS_HV = {k: float(PROFILE['weights']['HV'][k]) for k in FACTOR_KEYS}


def validate_profiles(raw=None):
    """Structural + numeric validation for every profile (including inherited)."""
    raw = raw if raw is not None else load_profiles()
    errors = []
    if not isinstance(raw, dict):
        return ['config root must be an object']
    if not isinstance(raw.get('version'), int):
        errors.append('version must be an integer')
    profiles = raw.get('profiles')
    if not isinstance(profiles, dict) or not profiles:
        return ['profiles must be a non-empty object']
    default = raw.get('default_profile')
    if default not in profiles:
        errors.append(f'default_profile {default!r} not found in profiles')

    for name in profiles:
        try:
            profile = resolve_profile(name, raw)
        except (KeyError, ValueError) as exc:
            errors.append(str(exc))
            continue
        errors.extend(f'{name}: {e}' for e in _validate_profile(profile))
        spec = profiles[name]
        if name.startswith('exp_'):
            enabled = [k for k, v in (profile.get('experiments') or {}).items()
                       if isinstance(v, dict) and v.get('enabled')]
            if not enabled:
                errors.append(f'{name}: experiment profile enables nothing')
        if isinstance(spec.get('extends'), str) and spec['extends'] not in profiles:
            errors.append(f'{name}: extends unknown profile {spec["extends"]!r}')

    legacy = profiles.get('legacy_v576')
    if isinstance(legacy, dict):
        dead = ((legacy.get('weights') or {}).get('HV') or {})
        dead_st = ((legacy.get('weights') or {}).get('ST') or {})
        for venue, table in (('HV', dead), ('ST', dead_st)):
            for key in ('weight', 'gear', 'pace'):
                if table.get(key) != 0:
                    errors.append(f'legacy_v576: dead factor {key} must stay zero for {venue}')
    return errors


def _validate_profile(profile):
    errors = []
    fusion = profile.get('fusion') or {}
    model = profile.get('model') or {}
    factors = profile.get('factors') or {}
    weights = profile.get('weights') or {}
    features = profile.get('features') or {}
    experiments = profile.get('experiments') or {}
    evaluation = profile.get('evaluation') or {}

    def num(section, obj, key, lo=None, hi=None):
        value = obj.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            errors.append(f'{section}.{key} must be numeric')
            return None
        if lo is not None and value < lo:
            errors.append(f'{section}.{key} below {lo}')
        if hi is not None and value > hi:
            errors.append(f'{section}.{key} above {hi}')
        return float(value)

    mw = num('fusion', fusion, 'model_weight', 0, 1)
    mkw = num('fusion', fusion, 'market_weight', 0, 1)
    if mw is not None and mkw is not None and abs(mw + mkw - 1) > 0.02:
        errors.append('fusion.model_weight + fusion.market_weight must sum to 1')
    num('fusion', fusion, 'market_gamma', 0.5, 2.5)
    num('fusion', fusion, 'extreme_odds_alpha', 0, 1)
    band = fusion.get('extreme_odds_band')
    if (not isinstance(band, list) or len(band) != 2
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in band)
            or band[0] >= band[1]):
        errors.append('fusion.extreme_odds_band must be [low, high] with low < high')
    bands = fusion.get('banded_gamma')
    if not isinstance(bands, list) or not bands:
        errors.append('fusion.banded_gamma must be a non-empty list')
    else:
        for i, entry in enumerate(bands):
            if not isinstance(entry, dict):
                errors.append(f'fusion.banded_gamma[{i}] must be an object')
                continue
            num(f'fusion.banded_gamma[{i}]', entry, 'gamma', 0.5, 2.5)
            if i < len(bands) - 1 and entry.get('max_odds') is None:
                errors.append(f'fusion.banded_gamma[{i}].max_odds must not be null before the last band')

    t = num('model', model, 'softmax_temperature', 0.1, 100)
    method = model.get('calibration_method')
    if method not in _CALIBRATION_METHODS:
        errors.append(f'model.calibration_method must be one of {_CALIBRATION_METHODS}')
    power = num('model', model, 'calibration_power', 0.05, 20)
    tcal = num('model', model, 'calibration_temperature', 0.1, 100)
    if method == 'temperature' and t is not None and tcal is not None and power is not None:
        if abs(power - t / tcal) > 1e-6:
            errors.append('model.calibration_power must equal softmax_temperature / calibration_temperature')
    pmin = num('model', model, 'platt_window_min', 0)
    pmax = num('model', model, 'platt_window_max', 0)
    if pmin is not None and pmax is not None and pmax and pmax < pmin:
        errors.append('model.platt_window_max below platt_window_min')

    num('factors', factors, 'form_shrink_k', 0)
    num('factors', factors, 'form_shrink_prior', 1, 20)
    num('factors', factors, 'rating_blend', 0, 1)
    num('factors', factors, 'draw_st_route_min_distance', 800, 2600)
    draw_k = factors.get('draw_k')
    if not isinstance(draw_k, dict):
        errors.append('factors.draw_k must be an object')
    else:
        for key in ('HV', 'ST_sprint', 'ST_route', 'ST_1000'):
            if not isinstance(draw_k.get(key), (int, float)) or isinstance(draw_k.get(key), bool):
                errors.append(f'factors.draw_k.{key} must be numeric')

    for venue in ('HV', 'ST'):
        table = weights.get(venue)
        if not isinstance(table, dict):
            errors.append(f'weights.{venue} must be an object')
            continue
        if set(table) != set(FACTOR_KEYS):
            errors.append(f'weights.{venue} must contain exactly the nine factor keys')
            continue
        values = []
        for key in FACTOR_KEYS:
            value = table[key]
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(f'weights.{venue}.{key} must be numeric')
                continue
            if value < 0 or value > 0.5:
                errors.append(f'weights.{venue}.{key} outside [0, 0.5]')
            values.append(float(value))
        if len(values) == len(FACTOR_KEYS) and abs(sum(values) - 1) > 0.02:
            errors.append(f'weights.{venue} must sum to 1 (got {sum(values):.4f})')

    if set(features) != set(_FEATURE_KEYS):
        errors.append(f'features must contain exactly {_FEATURE_KEYS}')
    for key, value in features.items():
        if not isinstance(value, bool):
            errors.append(f'features.{key} must be boolean')

    if set(experiments) != set(_EXPERIMENT_KEYS):
        errors.append(f'experiments must contain exactly {_EXPERIMENT_KEYS}')
    for key, value in experiments.items():
        if not isinstance(value, dict) or not isinstance(value.get('enabled'), bool):
            errors.append(f'experiments.{key} must be an object with boolean enabled')
            continue
        if key == 'platt':
            lo, hi = value.get('window_min'), value.get('window_max')
            if not isinstance(lo, int) or not isinstance(hi, int) or hi < lo:
                errors.append('experiments.platt needs integer window_min <= window_max')
        if key == 'timing_fusion':
            for k in ('no_odds_market_weight', 'min_coverage', 'far_market_weight', 'near_market_weight'):
                if not isinstance(value.get(k), (int, float)) or not 0 <= value[k] <= 1:
                    errors.append(f'experiments.timing_fusion.{k} must be in [0, 1]')
            if not isinstance(value.get('far_hours'), (int, float)) or value['far_hours'] <= 0:
                errors.append('experiments.timing_fusion.far_hours must be positive')
        if key == 'extreme_favourite_guard':
            if not isinstance(value.get('threshold'), (int, float)) or not 1 <= value['threshold'] <= 10:
                errors.append('experiments.extreme_favourite_guard.threshold must be in [1, 10]')
            if not isinstance(value.get('max_model_weight'), (int, float)) or not 0 <= value['max_model_weight'] <= 1:
                errors.append('experiments.extreme_favourite_guard.max_model_weight must be in [0, 1]')
        if key == 'availability_renorm':
            if not isinstance(value.get('min_coverage'), (int, float)) or not 0 <= value['min_coverage'] <= 1:
                errors.append('experiments.availability_renorm.min_coverage must be in [0, 1]')
        if key == 'st1000_draw_reversal':
            if not isinstance(value.get('draw_k'), (int, float)) or not -1 <= value['draw_k'] <= 1:
                errors.append('experiments.st1000_draw_reversal.draw_k must be in [-1, 1]')
        if key in ('speed_engine', 'finish_time_margin'):
            if value.get('mode') != 'display_only':
                errors.append(f'experiments.{key}.mode must stay display_only')

    if evaluation.get('odds_source') not in _ODDS_SOURCES:
        errors.append(f'evaluation.odds_source must be one of {_ODDS_SOURCES}')
    for key in ('as_of_jockey_trainer_rates', 'fold_train_only_weights'):
        if not isinstance(evaluation.get(key), bool):
            errors.append(f'evaluation.{key} must be boolean')
    if not isinstance(evaluation.get('roi_label'), str) or not evaluation['roi_label']:
        errors.append('evaluation.roi_label must be a non-empty string')
    return errors


def _valid_table(table) -> bool:
    if not isinstance(table, dict):
        return False
    try:
        values = [float(table[k]) for k in FACTOR_KEYS]
    except (KeyError, TypeError, ValueError):
        return False
    return all(0.0 <= v <= 0.5 for v in values) and abs(sum(values) - 1.0) < 0.02


def load_active_weights() -> dict:
    """Fitted tables published by recalibrate_weights.py, or {} when absent/invalid."""
    global _active_cache
    if _active_cache is not None:
        return _active_cache
    try:
        with open(ACTIVE_WEIGHTS_PATH, encoding='utf-8') as fh:
            data = json.load(fh)
        weights = data.get('weights') if isinstance(data, dict) else None
        _active_cache = weights if isinstance(weights, dict) else {}
    except (OSError, ValueError):
        _active_cache = {}
    return _active_cache


def raw_weights_for(venue):
    """Profile baseline (what the client uses until a fitted table is published)."""
    raw = dict(RAW_WEIGHTS_HV if venue == 'HV' else RAW_WEIGHTS_ST)
    return {k: round(v, 4) for k, v in raw.items()}


def weights_for(venue):
    """Venue weights — recalibrated table when published, profile table otherwise."""
    active = load_active_weights()
    table = active.get('HV' if venue == 'HV' else 'ST')
    if not _valid_table(table):
        return raw_weights_for(venue)
    return {k: round(v, 4) for k, v in table.items()}


def market_probabilities(odds):
    """(1/odds)^GAMMA, renormalised — strips the ~22% takeout and the longshot bias."""
    raw = [(1.0 / o) ** MARKET_GAMMA if o and o > 1.0 else 0.0 for o in odds]
    total = sum(raw)
    if total <= 0:
        n = max(1, len(odds))
        return [1.0 / n] * len(odds)
    return [r / total for r in raw]


def fuse(p_model, p_market):
    return MODEL_WEIGHT * p_model + MARKET_WEIGHT * p_market


def fusion_alpha(odds):
    """Core α=0.2, lifted when the price is extreme (OOS NLL 2.1749 → 2.1657)."""
    if odds is not None and (odds < EXTREME_ODDS_BAND[0] or odds > EXTREME_ODDS_BAND[1]):
        return EXTREME_ODDS_ALPHA
    return MODEL_WEIGHT


def calibrate_p_model(p_models):
    """Post-softmax temperature scaling over the whole field, renormalised."""
    scaled = [max(float(p), 0.0) ** CALIBRATION_POWER for p in p_models]
    total = sum(scaled)
    if total <= 0:
        return list(p_models)
    return [p / total for p in scaled]


def fuse_race(p_models, p_markets, odds_list=None):
    """Calibrate the field once, then fuse each runner (dynamic α at extreme odds).

    p_markets may contain None when a runner has no price; those stay model-only.
    """
    calibrated = calibrate_p_model(p_models)
    fused = []
    for i, p_model in enumerate(calibrated):
        p_market = p_markets[i] if p_markets else None
        if p_market is None:
            fused.append(p_model)
            continue
        odds = odds_list[i] if odds_list else None
        alpha = fusion_alpha(odds)
        fused.append(alpha * p_model + (1 - alpha) * p_market)
    return fused