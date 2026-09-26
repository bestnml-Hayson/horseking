/* =========================================================
   HorseAI Engine - 20-D Feature Engineering (for XGBoost/LightGBM/RuleEngine)
   Input schema 欄位名對齊 public/data/history/*.json
   Output: featureVector[20] + namedFeatures{} (可直接推入 XGBoost model)
   ========================================================= */
(function (global) {
    'use strict';
    const ENGINE_VERSION = 'horse-ai-2.1.0-features-v20';
    function _num(v, d) { v = Number(v); return Number.isFinite(v) ? v : (d == null ? 0 : d); }
    function _clip(v, a, b) { return Math.max(a, Math.min(b, v)); }
    function _median(arr) {
        if (!arr || !arr.length) return NaN;
        const a = arr.slice().sort(function (a, b) { return a - b; });
        const m = Math.floor(a.length / 2);
        return (a.length % 2) ? a[m] : (a[m - 1] + a[m]) / 2;
    }
    function _normalize(arr) {
        if (!arr || !arr.length) return [];
        let mn = arr[0], mx = arr[0];
        for (let i = 1; i < arr.length; i++) { if (arr[i] < mn) mn = arr[i]; if (arr[i] > mx) mx = arr[i]; }
        const r = mx - mn;
        return arr.map(function (v) { return r <= 0 ? 50 : Math.round(((v - mn) / r) * 1000) / 10; });
    }

    const TRACK_CONDITION_MAP = {
        '快地': 0, '好快地': 0.25, '好地': 0.5, '好黏地': 0.75, '黏地': 0.85, '軟地': 1, '軟爛地': 1
    };
    const VENUE_ST_MAP = { '沙田': 'ST', 'SHATIN': 'ST', 'ST': 'ST', '跑馬地': 'HV', 'HAPPY VALLEY': 'HV', 'HV': 'HV' };

    function _goingEnum(goingStr) {
        if (!goingStr) return 0.5;
        const s = String(goingStr).trim();
        for (const k in TRACK_CONDITION_MAP) {
            if (s.indexOf(k) >= 0) return TRACK_CONDITION_MAP[k];
        }
        if (/fast/i.test(s)) return 0;
        if (/good.*firm/i.test(s)) return 0.25;
        if (/good/i.test(s)) return 0.5;
        if (/good.*yielding|yielding.*good/i.test(s)) return 0.75;
        if (/yielding/i.test(s)) return 0.85;
        if (/soft|heavy/i.test(s)) return 1;
        return 0.5;
    }

    function _finishWeightedScore(last6Arr) {
        if (!last6Arr || !last6Arr.length) return 50;
        const w = [0.28, 0.22, 0.18, 0.13, 0.10, 0.09];
        let s = 0;
        for (let i = 0; i < Math.min(last6Arr.length, 6); i++) {
            const el = last6Arr[i];
            let r = 14;
            if (typeof el === 'number') r = el || 14;
            else if (el && typeof el === 'object') r = (typeof el.finish === 'number' ? el.finish : 14);
            const sc = r === 1 ? 100 : r === 2 ? 85 : r === 3 ? 70 : r <= 6 ? 55 : r <= 10 ? 35 : Math.max(10, 20 - r);
            s += sc * (w[i] || 0.06);
        }
        return Math.round(s * 10) / 10;
    }

    function _winRate(records, fieldFilter) {
        if (!records || !records.length) return NaN;
        const pool = fieldFilter ? records.filter(fieldFilter) : records;
        if (!pool.length) return NaN;
        let w = 0, p = 0;
        for (let i = 0; i < pool.length; i++) {
            const el = pool[i];
            const r = typeof el === 'number' ? el : (el && typeof el.finish === 'number' ? el.finish : 99);
            if (r === 1) w++;
            if (r >= 1 && r <= 3) p++;
        }
        return { n: pool.length, winRate: w / pool.length, placeRate: p / pool.length };
    }

    function _speedFigure(bestTimeSec, distanceM, going, horseBwt) {
        if (!(bestTimeSec > 0) || !(distanceM > 0)) return 50;
        const ave = Math.round(distanceM / bestTimeSec * 10) / 10;
        const gAdj = 1 - _goingEnum(going) * 0.06;
        const bwtAdj = 1 - (_num(horseBwt, 126) - 126) * 0.0018;
        const raw = ave * gAdj * bwtAdj;
        const bench = {
            1000: 16.5, 1200: 16.2, 1400: 16.0, 1600: 15.7,
            1650: 15.7, 1800: 15.5, 2000: 15.3, 2200: 15.1, 2400: 14.9
        };
        let b = 16;
        for (const d in bench) { if (Math.abs(Number(d) - distanceM) < 100) { b = bench[d]; break; } }
        return _clip(Math.round((raw / b) * 90 * 10) / 10, 15, 95);
    }

    function _drawBiasScore(draw, distanceM, venue, going) {
        if (!(draw > 0)) return 50;
        const v = VENUE_ST_MAP[String(venue || '')] || 'ST';
        let centerBias = 6;
        if (v === 'ST') {
            if (distanceM <= 1200) centerBias = _goingEnum(going) > 0.6 ? 4 : 6;
            else if (distanceM <= 1650) centerBias = 6;
            else centerBias = 8;
        } else {
            if (distanceM <= 1200) centerBias = _goingEnum(going) > 0.6 ? 5 : 7;
            else if (distanceM <= 1650) centerBias = 7;
            else centerBias = 9;
        }
        const gap = Math.abs(draw - centerBias);
        return _clip(Math.round((100 - gap * 9) * 10) / 10, 15, 95);
    }

    function _windAdjustment(windKmh, windDegToHomeStraight, distanceM, runningStyleTag) {
        const w = Math.max(0, _num(windKmh, 0));
        if (w <= 0) return 0;
        const theta = (windDegToHomeStraight >= 0 ? windDegToHomeStraight : 180);
        const headTail = Math.cos(theta * Math.PI / 180);
        const styleBoost = runningStyleTag === 'front-runner' ? 0.15 : runningStyleTag === 'hold-up' ? -0.15 : 0;
        const distFactor = distanceM >= 1800 ? 1.2 : 1.0;
        return Math.round((w * 0.25) * (headTail + styleBoost) * distFactor * 10) / 10;
    }

    function _extractLast6Arr(h) {
        if (Array.isArray(h.last_6) && h.last_6.length) return h.last_6;
        if (Array.isArray(h.last_3) && h.last_3.length) return h.last_3;
        if (typeof h.last_6 === 'string' && h.last_6) {
            return h.last_6.split(/[\/\-\s,]+/).map(function (x) { return parseInt(x, 10) || 14; }).filter(Boolean);
        }
        return [];
    }

    function _histLookupDB(horseCode, jockeyName, trainerName, venue, distanceM, histDB) {
        const empty = { sameVenueDist: null, sameJockey: null, sameTrainer: null, sameVenueDistGoing: null };
        if (!histDB) return empty;
        return empty;
    }

    function compute20D(horse, raceInfo, meta, hist, runtimeEnv) {
        const r = raceInfo || {};
        const distanceM = _num(r.distance_m, 0);
        const going = r.going || (r.track_condition ? r.track_condition : '好地');
        const venue = r.venue || '';
        const histDB = hist || (global.window && window.DB ? window.DB : null) || {};
        const env = runtimeEnv || {};

        const h = horse || {};
        const horseCode = h.code || '';
        const last6 = _extractLast6Arr(h);
        const last3 = (Array.isArray(h.last_3) && h.last_3.length) ? h.last_3 : last6.slice(0, 3);

        const wrOverall = _winRate(last6);
        const wr3 = _winRate(last3);
        const sameVenueDist = (function () {
            try {
                const _db = histDB || (global.window && window.DB ? window.DB : null);
                if (_db && _db.horsesDB && horseCode && _db.horsesDB[horseCode] && Array.isArray(_db.horsesDB[horseCode].history)) {
                    const pool = _db.horsesDB[horseCode].history.filter(function (r) {
                        if (!r) return false;
                        if (venue && r.venue && String(r.venue) !== String(venue)) return false;
                        if (distanceM > 0 && r.distance_m && Math.abs(Number(r.distance_m) - distanceM) > 100) return false;
                        return true;
                    });
                    if (pool.length) {
                        let w = 0, p = 0;
                        pool.forEach(function (r) {
                            const f = Number(r.finish) || 99;
                            if (f === 1) w++;
                            if (f >= 1 && f <= 3) p++;
                        });
                        return { n: pool.length, winRate: (w / pool.length), placeRate: (p / pool.length) };
                    }
                }
            } catch (e) {}
            return null;
        })();

        const rating = _num(h.rating, 0);
        const weight = _num(h.weight, 126);
        const weightDelta = _num(h.weight_delta, 0);
        const draw = _num(h.draw, 6);
        const oddsW = _num(h.odds_win, 0);
        const oddsP = _num(h.odds_place, 0);
        const bestTimeSec = (h.best_time_sec && h.best_time_sec > 0 && h.best_time_sec < 999) ? h.best_time_sec : 0;
        const jockey = h.jockey || '';
        const trainer = h.trainer || '';

        const statsDB = (histDB && histDB.stats) ? histDB.stats : (global.window && window.DB && window.DB.stats ? window.DB.stats : null);
        const jockeyStats = (statsDB && statsDB.jockeys && jockey) ? statsDB.jockeys[jockey] : null;
        const trainerStats = (statsDB && statsDB.trainers && trainer) ? statsDB.trainers[trainer] : null;
        const jw = jockeyStats && typeof jockeyStats.winRate === 'number' ? jockeyStats.winRate : 0.10;
        const tw = trainerStats && typeof trainerStats.winRate === 'number' ? trainerStats.winRate : 0.10;
        const jp = jockeyStats && typeof jockeyStats.placeRate === 'number' ? jockeyStats.placeRate : 0.30;
        const tp = trainerStats && typeof trainerStats.placeRate === 'number' ? trainerStats.placeRate : 0.30;

        const windKmh = _num(env.wind_kmh, (r.wind_speed_kmh || 0));
        const windDeg = _num(env.wind_deg_home_straight, (r.wind_deg_home_straight || NaN));
        const runStyle = h.running_style || (last3.length ? (last3.filter(function (x) { return (typeof x === 'number' ? x : (x && x.draw ? x.draw : 99)) <= 4; }).length >= 2 ? 'front-runner' : 'hold-up') : 'mid-field');

        const f1_last6Score = _finishWeightedScore(last6);
        const f2_last3Score = _finishWeightedScore(last3);
        const f3_sameVenueDistWinRate = sameVenueDist ? sameVenueDist.winRate * 100 : (wrOverall.n ? wrOverall.winRate * 100 : 50);
        const f4_speedFigure = _speedFigure(bestTimeSec, distanceM, going, weight);
        const f5_weightRaw = weight;
        const f6_weightDelta = weightDelta;
        const f7_weightRatio = weight > 0 ? (_num(h.body_weight_kg, 480) / weight) : 0;
        const f8_jockeyWinRate = _clip(jw * 100, 2, 60);
        const f9_trainerWinRate = _clip(tw * 100, 2, 50);
        const f10_jxTComboWinRate = _clip((jw * 0.6 + tw * 0.4 + (jockeyStats && jockeyStats._combo && jockeyStats._combo[trainer] ? jockeyStats._combo[trainer].winRate : 0)) * 100, 2, 55);
        const f11_trackCondition = _goingEnum(going);
        const f12_drawBias = _drawBiasScore(draw, distanceM, venue, going);
        const f13_rating = rating;
        const f14_oddsOverround = oddsW > 0 ? (1 / oddsW) : 0;
        const f15_placeWinConsistency = oddsP > 0 && oddsW > 0 ? _clip((oddsP / oddsW) * 20, 20, 95) : 50;
        const f16_winPlaceGapRate = (wrOverall.n ? Math.max(0, (wrOverall.placeRate - wrOverall.winRate)) : 0.25) * 100;
        const f17_rainfall_mm = _clip(_num(env.rainfall_mm, (r.rainfall_mm || 0)), 0, 120) / 1.2;
        const f18_windImpactScore = _clip(_windAdjustment(windKmh, windDeg, distanceM, runStyle) + 50, 15, 95);
        const f19_ratingTrend = _num((h.rating_delta || (h.aug && h.aug.trend && typeof h.aug.trend.score === 'number' ? (h.aug.trend.score - 50) / 2 : 0)), 0);
        const f20_ccExpertRatio = _num(h.cc_expert_count, 0);

        const vec = [f1_last6Score, f2_last3Score, f3_sameVenueDistWinRate, f4_speedFigure,
            f5_weightRaw, f6_weightDelta, f7_weightRatio, f8_jockeyWinRate, f9_trainerWinRate,
            f10_jxTComboWinRate, f11_trackCondition, f12_drawBias, f13_rating, f14_oddsOverround,
            f15_placeWinConsistency, f16_winPlaceGapRate, f17_rainfall_mm, f18_windImpactScore,
            f19_ratingTrend, f20_ccExpertRatio];

        const named = {
            last6Score: f1_last6Score, last3Score: f2_last3Score, sameVenueDistWinRate: f3_sameVenueDistWinRate,
            speedFigure: f4_speedFigure, weightRaw: f5_weightRaw, weightDelta: f6_weightDelta, weightRatio: f7_weightRatio,
            jockeyWinRate: f8_jockeyWinRate, trainerWinRate: f9_trainerWinRate, jxTComboWinRate: f10_jxTComboWinRate,
            trackCondition: f11_trackCondition, drawBias: f12_drawBias, rating: f13_rating, oddsOverround: f14_oddsOverround,
            placeWinConsistency: f15_placeWinConsistency, winPlaceGapRate: f16_winPlaceGapRate,
            rainfallMm: f17_rainfall_mm, windImpactScore: f18_windImpactScore, ratingTrend: f19_ratingTrend,
            ccExpertRatio: f20_ccExpertRatio
        };

        return { ENGINE_VERSION: ENGINE_VERSION, featureVector: vec, named: named, _runningStyle: runStyle };
    }

    global.HorseAIFeatures = {
        compute20D: compute20D,
        _fn: { goingEnum: _goingEnum, finishWeighted: _finishWeightedScore, speedFigure: _speedFigure, drawBias: _drawBiasScore, windAdjust: _windAdjustment, normalize: _normalize, median: _median }
    };
    if (global.window && !global.window.HorseAIFeatures) global.window.HorseAIFeatures = global.HorseAIFeatures;
})(typeof window !== 'undefined' ? window : (typeof self !== 'undefined' ? self : globalThis));
