"""Fusion / scoring constants shared by every Python engine.

Mirror of lib/race-utils.ts — change one, change the other. Kept in one file because
ai_review.py, odds_injection.py and benter_model.py each used to hard-code their own
copy, which is how the client and the post-race review drifted apart.

Calibrated on 2026-02..2026-11 results (fit Feb-Aug, validate Sep-Nov): P_model alone
ranks worse than the price (NLL 2.34 vs 2.11), so the market anchors and the model is a
value tilt. All 9 factors are live; each venue's weight table sums to exactly 1.0.

The 2026-11-28 walk-forward (5 folds, 138 OOS races 2026-10-07 → 2026-11-25) moved
MARKET_GAMMA 1.3 → 1.0 (γ picks [1.1,1.0,1.0,1.1,1.0], NLL 2.2107 → 2.1790). After the
same-day weight refit the temperature picks were [8,8,8,8,9], so calibration is the
identity and none is applied. Dynamic fusion keeps α=0.2 but lifts it to 0.35 for
extreme prices. Banded γ fitted all-1.0, so no segmentation is deployed.
scripts/backtest_models.py reproduces every number.

scripts/recalibrate_weights.py may publish a fitted table to weights_active.json; when
that file validates, it overrides the hand-set tables below for every Python engine.
The browser reads the same numbers from pipeline_status.model_weights_active.
"""
import json
import os

MODEL_WEIGHT = 0.2
MARKET_WEIGHT = 0.8
SOFTMAX_TEMPERATURE = 8
MARKET_GAMMA = 1.0

# Post-softmax temperature scaling: softmax(s/T) is softmax(s/8) raised to 8/T.
# Re-measured after the 2026-11-28 weight refit: fold picks were [8,8,8,8,9],
# i.e. the raw P_model is already calibrated well enough (ECE 0.019) and no
# scaling is deployed. The parameter stays so the calibration path remains
# switchable without code changes.
CALIBRATION_TEMPERATURE = 8.0
CALIBRATION_POWER = SOFTMAX_TEMPERATURE / CALIBRATION_TEMPERATURE

# Extreme prices: the model adds information where the market is least reliable.
EXTREME_ODDS_ALPHA = 0.35
EXTREME_ODDS_BAND = (1.8, 25.0)

# Bayesian shrinkage of the recent-form average toward a mid-field 6.5 finish.
FORM_SHRINK_K = 2.5
FORM_SHRINK_PRIOR = 6.5

# official_rating percentile blended into the class-movement factor (OOS −0.014 NLL).
RATING_BLEND = 0.35

# Draw score uses the actual field size; the multiplier is the inside-bias strength.
DRAW_K_HV = 0.9
DRAW_K_ST_SPRINT = 0.7   # ST < 1600m
DRAW_K_ST_ROUTE = 0.55   # ST ≥ 1600m

# 跑馬地 draw-dominant (tight circuit), 沙田 form-dominant (long straights).
RAW_WEIGHTS_ST = {
    'form': 0.22, 'courseDistance': 0.16, 'jockeyTrainer': 0.13, 'draw': 0.12,
    'pace': 0.12, 'weight': 0.10, 'restDays': 0.06, 'classMov': 0.06, 'gear': 0.03,
}
RAW_WEIGHTS_HV = {
    'form': 0.20, 'draw': 0.18, 'pace': 0.14, 'courseDistance': 0.14,
    'jockeyTrainer': 0.12, 'weight': 0.08, 'restDays': 0.06, 'classMov': 0.05, 'gear': 0.03,
}

FACTOR_KEYS = ('form', 'draw', 'jockeyTrainer', 'weight', 'courseDistance',
               'restDays', 'gear', 'pace', 'classMov')

ACTIVE_WEIGHTS_PATH = os.path.join(os.path.dirname(__file__), 'weights_active.json')
_active_cache = None


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
    """Hand-set baseline (what the client uses until a fitted table is published)."""
    raw = dict(RAW_WEIGHTS_HV if venue == 'HV' else RAW_WEIGHTS_ST)
    return {k: round(v, 4) for k, v in raw.items()}


def weights_for(venue):
    """Venue weights — recalibrated table when published, hand-set table otherwise."""
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
