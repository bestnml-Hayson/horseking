"""Fusion / scoring constants shared by every Python engine.

Mirror of lib/race-utils.ts — change one, change the other. Kept in one file because
ai_review.py, odds_injection.py and benter_model.py each used to hard-code their own
copy, which is how the client and the post-race review drifted apart.

Calibrated on 2026-02..2026-11 results (fit Feb-Aug, validate Sep-Nov): P_model alone
ranks worse than the price (NLL 2.34 vs 2.11), so the market anchors and the model is a
value tilt. weight/pace/gear carry no information on today's inputs (rank corr -0.09 /
+0.01 / n-a, and 86-100% of races score every runner identically) so they are excluded.
"""

MODEL_WEIGHT = 0.2
MARKET_WEIGHT = 0.8
SOFTMAX_TEMPERATURE = 8
MARKET_GAMMA = 1.3

DEAD_FACTORS = ('weight', 'gear', 'pace')

RAW_WEIGHTS_ST = {
    'form': 0.16, 'draw': 0.08, 'jockeyTrainer': 0.14, 'weight': 0.08,
    'courseDistance': 0.18, 'restDays': 0.10, 'gear': 0.06, 'pace': 0.10, 'classMov': 0.10,
}
RAW_WEIGHTS_HV = {
    'form': 0.18, 'draw': 0.14, 'jockeyTrainer': 0.12, 'weight': 0.08,
    'courseDistance': 0.16, 'restDays': 0.10, 'gear': 0.06, 'pace': 0.08, 'classMov': 0.08,
}


def weights_for(venue):
    """Venue weights with the dead factors removed and the rest re-normalised to 1."""
    raw = dict(RAW_WEIGHTS_HV if venue == 'HV' else RAW_WEIGHTS_ST)
    dead = sum(raw[k] for k in DEAD_FACTORS)
    scale = 1.0 / (1.0 - dead)
    for k in DEAD_FACTORS:
        raw[k] = 0.0
    return {k: round(v * scale, 4) for k, v in raw.items()}


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
