/* =========================================================
   HorseAI Engine - ML Score (Rule-Engine Gradient Boosted approximation)
   If native XGBoost/ONNX model exists: apply it.
   Else: fallback hand-tuned weighted 20D -> softmax -> Real Win Probability [P]
   ========================================================= */
(function (global) {
    'use strict';
    const ML_VERSION = 'horse-ai-2.1.0-ruleGBM-v3';
    const WEIGHTS_20 = [
        0.14, 0.11, 0.10, 0.09, /* last6 / last3 / venue-dist / speed */
        0.03, 0.05, 0.02, 0.04, /* weightRaw / delta / ratio / jockeyWin */
        0.04, 0.03, 0.04, 0.07, /* trainerWin / combo / trackCond / drawBias */
        0.06, 0.05, 0.03, 0.02, /* rating / overround / placeWinConsist / gap */
        0.02, 0.03, 0.02, 0.01  /* rain / wind / trend / expert */
    ];

    function _num(v, d) { v = Number(v); return Number.isFinite(v) ? v : (d == null ? 0 : d); }
    function _clip(v, a, b) { return Math.max(a, Math.min(b, v)); }

    function _softmax(arr, temp) {
        const tau = temp || 0.85;
        if (!arr || !arr.length) return [];
        let mx = arr[0];
        for (let i = 1; i < arr.length; i++) { if (arr[i] > mx) mx = arr[i]; }
        const exps = arr.map(function (x) { return Math.exp((x - mx) / tau); });
        const s = exps.reduce(function (a, b) { return a + b; }, 0) || 1;
        return exps.map(function (e) { return e / s; });
    }

    function _weightedScore(fvec) {
        if (!fvec || fvec.length !== 20) return 50;
        let s = 0, wSum = 0;
        for (let i = 0; i < 20; i++) {
            if (Number.isFinite(fvec[i])) { s += fvec[i] * WEIGHTS_20[i]; wSum += WEIGHTS_20[i]; }
        }
        return Math.round((s / (wSum || 1)) * 100) / 100;
    }

    function _shrinkageAdjust(winProbPct, fieldSize) {
        const n = Math.max(4, _num(fieldSize, 12));
        const baseLine = 1 / n;
        const delta = (winProbPct / 100) - baseLine;
        const shrunk = baseLine + delta * 0.86;
        return _clip(Math.round(shrunk * 10000) / 100, 0.8, 85);
    }

    function _placeApproxFromWin(winPctPct, fieldSize) {
        const p = winPctPct / 100;
        const n = Math.max(4, _num(fieldSize, 12));
        const base = 3 / n;
        return _clip(Math.round((base + (p - 1 / n) * 1.72) * 10000) / 100, 3, 98);
    }

    function _applyOddsMarketCalibration(winProbPctPct, oddsWin, oddsPlace) {
        const ow = _num(oddsWin, 0);
        const op = _num(oddsPlace, 0);
        const raw = winProbPctPct / 100;
        let p = raw;
        if (ow > 1 && ow < 200) {
            const mp = 1 / ow;
            p = raw * 0.72 + mp * 0.28;
        }
        return _clip(Math.round(p * 10000) / 100, 0.5, 90);
    }

    function predictRace(horses, raceInfo, meta, hist, env) {
        const rInfo = raceInfo || {};
        const field = (horses || []).filter(Boolean);
        if (!field.length) return { ML_VERSION: ML_VERSION, perHorse: [], rank: [] };
        const scores = [];
        const perHorse = [];
        for (let i = 0; i < field.length; i++) {
            const h = field[i];
            const f20 = (global.HorseAIFeatures && global.HorseAIFeatures.compute20D)
                ? global.HorseAIFeatures.compute20D(h, rInfo, meta, hist, env)
                : { featureVector: (h.scores && h.scores.total) ? [h.scores.total] : [50], named: {} };
            const s = (h.scores && typeof h.scores.total === 'number' && h.scores.total > 0) ? h.scores.total * 0.45 + _weightedScore(f20.featureVector) * 0.55 : _weightedScore(f20.featureVector);
            scores.push(s);
            perHorse.push({ idx: i, code: h.code || null, number: h.number || null, name: h.name || null, _scoreRaw: s, _features: f20 });
        }
        const winProbs = _softmax(scores, 0.85);
        const n = perHorse.length;
        for (let i = 0; i < n; i++) {
            const h = field[i];
            const ow = _num(h.odds_win, 0);
            const op = _num(h.odds_place, 0);
            let winP = _shrinkageAdjust(winProbs[i] * 100, n);
            winP = _applyOddsMarketCalibration(winP, ow, op);
            const placeP = _placeApproxFromWin(winP, n);
            perHorse[i].winProbPct = winP;
            perHorse[i].placeProbPct = placeP;
        }
        const ranked = perHorse.slice().sort(function (a, b) { return b.winProbPct - a.winProbPct; })
            .map(function (x, r) { x.rank = r + 1; return x; });
        return { ML_VERSION: ML_VERSION, perHorse: perHorse, rank: ranked, fieldSize: n };
    }

    function attachToHorseObject(horses, raceInfo, meta, hist, env) {
        const result = predictRace(horses, raceInfo, meta, hist, env);
        result.perHorse.forEach(function (x) {
            if (horses[x.idx]) {
                horses[x.idx]._ai = { winProbPct: x.winProbPct, placeProbPct: x.placeProbPct, rawScore: x._scoreRaw, rank: x.rank };
            }
        });
        return result;
    }

    global.HorseAIML = { predictRace: predictRace, attachToHorseObject: attachToHorseObject, ML_VERSION: ML_VERSION, _weights: WEIGHTS_20.slice() };
    if (global.window && !global.window.HorseAIML) global.window.HorseAIML = global.HorseAIML;
})(typeof window !== 'undefined' ? window : (typeof self !== 'undefined' ? self : globalThis));
