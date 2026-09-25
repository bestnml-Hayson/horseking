/* =========================================================
   HorseAI Engine - EV + Kelly Criterion (Full/Half/Fractional Kelly)
   必讀：使用前，P 一定要是 AI 真實勝率（0-100%），市場賠率 = decimal odds (HKJC 賠率)
   ========================================================= */
(function (global) {
    'use strict';
    const KELLY_VERSION = 'horse-ai-2.1.0-kelly-ev-v3';
    const _num = function (v, d) { v = Number(v); return Number.isFinite(v) ? v : (d == null ? 0 : d); };
    const _clip = function (v, a, b) { return Math.max(a, Math.min(b, v)); };

    function decimalToB(decimalOdds) {
        const o = _num(decimalOdds, 0);
        if (!(o > 1)) return 0;
        return Math.round((o - 1) * 10000) / 10000;
    }

    function expectedValue(winProbPct, decimalOdds) {
        const p = _clip(_num(winProbPct, 0) / 100, 0, 1);
        const o = _num(decimalOdds, 0);
        if (!(o > 1) || !(p > 0)) return { ev: -1, evPct: -100, isValueBet: false };
        const ev = p * o - 1;
        return {
            ev: Math.round(ev * 10000) / 10000,
            evPct: Math.round(ev * 10000) / 100,
            isValueBet: ev > 0
        };
    }

    function kellyFStar(winProbPct, decimalOdds) {
        const p = _clip(_num(winProbPct, 0) / 100, 0, 1);
        const q = 1 - p;
        const o = _num(decimalOdds, 0);
        if (!(o > 1)) return 0;
        const B = decimalToB(o);
        if (!(B > 0)) return 0;
        const f = (B * p - q) / B;
        return Math.round(f * 10000) / 10000;
    }

    function fractionalKelly(fStar, fraction) {
        const fr = _num(fraction, 0.5);
        return _clip(Math.round(fStar * fr * 10000) / 10000, 0, 0.25);
    }

    function analyzeBet(winProbPct, decimalOdds, placeProbPct, placeOdds, opts) {
        const o = {
            maxFraction: 0.20, minUnitHKD: 10,
            kellyFraction: 0.5,
            bankrollHKD: 5000,
            ...(opts || {})
        };
        const evWin = expectedValue(winProbPct, decimalOdds);
        const fWinStar = kellyFStar(winProbPct, decimalOdds);
        const fWin = fractionalKelly(fWinStar, o.kellyFraction);
        const fWinClamped = _clip(fWin, 0, o.maxFraction);

        const evPlace = (placeProbPct && placeOdds) ? expectedValue(placeProbPct, placeOdds) : { ev: -1, evPct: -100, isValueBet: false };
        const fPlaceStar = (placeProbPct && placeOdds) ? kellyFStar(placeProbPct, placeOdds) : 0;
        const fPlace = fractionalKelly(fPlaceStar, o.kellyFraction);
        const fPlaceClamped = _clip(fPlace, 0, o.maxFraction);

        const winBetHKD = evWin.isValueBet && fWinClamped > 0 ? Math.round((o.bankrollHKD * fWinClamped) / o.minUnitHKD) * o.minUnitHKD : 0;
        const placeBetHKD = evPlace.isValueBet && fPlaceClamped > 0 ? Math.round((o.bankrollHKD * fPlaceClamped) / o.minUnitHKD) * o.minUnitHKD : 0;
        const minUnitBet = 0;

        return {
            KELLY_VERSION: KELLY_VERSION,
            win: {
                decimalOdds: decimalOdds || 0, B: decimalToB(decimalOdds),
                winProbPct: winProbPct, ev: evWin.ev, evPct: evWin.evPct,
                isValueBet: evWin.isValueBet, fStar: fWinStar,
                fKellyFraction: fWinClamped, kellyFractionLabel: o.kellyFraction === 1 ? 'Full Kelly' : (o.kellyFraction === 0.5 ? 'Half Kelly' : (Math.round(o.kellyFraction * 100) + '% Kelly')),
                betHKD: winBetHKD,
                note: !evWin.isValueBet ? 'EV ≤ 0 市場過熱，建議放棄獨贏' : (fWinStar > 0 ? '' : 'Kelly f* ≤ 0，不建議下注')
            },
            place: {
                decimalOdds: placeOdds || 0, B: decimalToB(placeOdds),
                placeProbPct: placeProbPct || 0, ev: evPlace.ev, evPct: evPlace.evPct,
                isValueBet: evPlace.isValueBet, fStar: fPlaceStar,
                fKellyFraction: fPlaceClamped, kellyFractionLabel: o.kellyFraction === 1 ? 'Full Kelly' : (o.kellyFraction === 0.5 ? 'Half Kelly' : (Math.round(o.kellyFraction * 100) + '% Kelly')),
                betHKD: placeBetHKD,
                note: !evPlace.isValueBet ? 'EV ≤ 0 不建議位置' : (fPlaceStar > 0 ? '' : 'Kelly f* ≤ 0，不建議下注')
            },
            summary: {
                maxAllowedFraction: o.maxFraction,
                bankrollHKD: o.bankrollHKD,
                minUnitHKD: o.minUnitHKD,
                totalBetHKD: winBetHKD + placeBetHKD
            }
        };
    }

    function valueBetRank(raceHorseArray, opts) {
        const list = [];
        (raceHorseArray || []).forEach(function (h, i) {
            const ai = (h && h._ai) ? h._ai : (h && h.scores && typeof h.scores.total === 'number' ? { winProbPct: 50, placeProbPct: 30 } : { winProbPct: 0, placeProbPct: 0 });
            const r = analyzeBet(ai.winProbPct || 0, h.odds_win || 0, ai.placeProbPct || 0, h.odds_place || 0, opts || {});
            list.push({ idx: i, code: h.code || null, number: h.number || null, name: h.name || null, analysis: r });
        });
        const s = list.slice().sort(function (a, b) {
            const ax = (a.analysis.win.isValueBet ? a.analysis.win.evPct : -9999) + 0.35 * (b.analysis.place.isValueBet ? b.analysis.place.evPct : -9999);
            const bx = (b.analysis.win.isValueBet ? b.analysis.win.evPct : -9999) + 0.35 * (b.analysis.place.isValueBet ? b.analysis.place.evPct : -9999);
            return bx - ax;
        }).map(function (x, r) { x._rank = r + 1; return x; });
        return { KELLY_VERSION: KELLY_VERSION, items: list, valueBetsSorted: s, count: list.length, valueBetCount: s.filter(function (x) { return x.analysis.win.isValueBet || x.analysis.place.isValueBet; }).length };
    }

    global.HorseAIKelly = {
        KELLY_VERSION: KELLY_VERSION,
        expectedValue: expectedValue,
        kellyFStar: kellyFStar,
        fractionalKelly: fractionalKelly,
        analyzeBet: analyzeBet,
        valueBetRank: valueBetRank,
        _util: { decimalToB: decimalToB }
    };
    if (global.window && !global.window.HorseAIKelly) global.window.HorseAIKelly = global.HorseAIKelly;
})(typeof window !== 'undefined' ? window : (typeof self !== 'undefined' ? self : globalThis));
