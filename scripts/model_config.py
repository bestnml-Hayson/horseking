"""Fusion / scoring constants shared by every Python engine.

Mirror of lib/race-utils.ts — change one, change the other. Kept in one file because
ai_review.py, odds_injection.py and benter_model.py each used to hard-code their own
copy, which is how the client and the post-race review drifted apart.

Calibrated on 2026-02..2026-11 results (fit Feb-Aug, validate Sep-Nov): P_model alone
ranks worse than the price (NLL 2.34 vs 2.11), so the market anchors and the model is a
value tilt. All 9 factors are live; each venue's weight table sums to exactly 1.0.

scripts/recalibrate_weights.py may publish a fitted table to weights_active.json; when
that file validates, it overrides the hand-set tables below for every Python engine.
The browser reads the same numbers from pipeline_status.model_weights_active.
"""
import json
import os

MODEL_WEIGHT = 0.2
MARKET_WEIGHT = 0.8
SOFTMAX_TEMPERATURE = 8
MARKET_GAMMA = 1.3

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
