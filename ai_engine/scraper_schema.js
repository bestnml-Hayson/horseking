/* =========================================================
   賽事數據 Schema 擴展 (v2.1.0) + Scraper Template
   新增必備欄位：風速/跑道狀況enum/負重變更delta/即時賠率跳動/天氣降雨
   此檔案 = 合併 reference + 補齊缺值；scraper 可直接 extend
   ========================================================= */
(function (global) {
    'use strict';
    const SCHEMA_VERSION = 'horse-ai-2.1.0-env-schema-v1';

    const HKO_OBS_URL = 'https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=zh';
    const WIND_HOME_STRAIGHT_DEG = { ST: 120, HV: 300 };

    function _num(v, d) { v = Number(v); return Number.isFinite(v) ? v : (d == null ? 0 : d); }
    function _get(obj, path, def) {
        try {
            return path.split('.').reduce(function (o, k) { return (o != null) ? o[k] : undefined; }, obj) ?? def;
        } catch (e) { return def; }
    }

    function enrichRaceInfo(raceInfoOrig, envSnapshot, opts) {
        const r = Object.assign({}, (raceInfoOrig || {}));
        if (!r.meta) r.meta = {};
        r.meta.schema_version = SCHEMA_VERSION;
        const env = envSnapshot || {};
        const venueCode = (String(r.venue || '')).indexOf('跑馬') >= 0 || /HV|happy/i.test(String(r.venue || '')) ? 'HV' : 'ST';

        if (!r.track_condition_enum) {
            const go = String(r.going || '');
            const map = {
                '快地': 'FAST', '好快地': 'GOOD_TO_FIRM', '好地': 'GOOD',
                '好黏地': 'GOOD_TO_YIELDING', '黏地': 'YIELDING', '軟地': 'SOFT', '軟爛地': 'HEAVY'
            };
            r.track_condition_enum = map[go] || 'GOOD';
        }
        r.venue_code = r.venue_code || venueCode;
        r.wind_speed_kmh = _num(env.wind_speed_kmh, _num(r.wind_speed_kmh, 0));
        r.wind_direction_deg = _num(env.wind_direction_deg, _num(r.wind_direction_deg, NaN));
        r.wind_deg_home_straight = Number.isFinite(r.wind_direction_deg)
            ? Math.round(((r.wind_direction_deg - WIND_HOME_STRAIGHT_DEG[r.venue_code || 'ST']) % 360 + 360) % 360)
            : (r.wind_deg_home_straight || 180);
        r.air_temp_c = _num(env.air_temp_c, _num(r.air_temp_c, 26));
        r.humidity_pct = _num(env.humidity_pct, _num(r.humidity_pct, 80));
        r.rainfall_mm = _num(env.rainfall_mm, _num(r.rainfall_mm, 0));
        r.pressure_hpa = _num(env.pressure_hpa, _num(r.pressure_hpa, 1012));
        return r;
    }

    function enrichHorseWithDeltas(horse, previousRaceSameHorse) {
        const h = Object.assign({}, horse || {});
        const prev = previousRaceSameHorse || null;
        if (prev) {
            if (typeof prev.weight === 'number' && typeof h.weight === 'number' && prev.weight > 0) {
                h.weight_delta = Math.round((h.weight - prev.weight) * 10) / 10;
            }
            if (typeof prev.rating === 'number' && typeof h.rating === 'number') {
                h.rating_delta = h.rating - prev.rating;
            }
            if (typeof prev.odds_win === 'number' && typeof h.odds_win === 'number' && prev.odds_win > 0) {
                h.odds_movement_pct = Math.round((h.odds_win - prev.odds_win) / prev.odds_win * 1000) / 10;
            }
        } else {
            h.weight_delta = 0;
            h.rating_delta = 0;
            h.odds_movement_pct = 0;
        }
        return h;
    }

    function applyLiveOddsPatch(raceJson, liveOddsDict) {
        const r = Object.assign({}, raceJson || {});
        r.horses = (r.horses || []).map(function (h) {
            const key = String(h.code || h.number || '');
            const o = liveOddsDict ? (liveOddsDict[key] || liveOddsDict[String(h.number || '')] || null) : null;
            if (!o) return h;
            const hh = Object.assign({}, h);
            if (typeof o.odds_win === 'number' && o.odds_win > 0) {
                hh.odds_movement_pct = Number.isFinite(hh.odds_win) && hh.odds_win > 0
                    ? Math.round((o.odds_win - hh.odds_win) / hh.odds_win * 1000) / 10
                    : 0;
                hh.odds_win = o.odds_win;
            }
            if (typeof o.odds_place === 'number' && o.odds_place > 0) hh.odds_place = o.odds_place;
            if (typeof o.scratched === 'boolean') hh.scratched = o.scratched;
            if (typeof o.weight_change_lbs === 'number') hh.weight_delta = o.weight_change_lbs;
            return hh;
        });
        if (liveOddsDict && liveOddsDict.wind) {
            r.race_info = enrichRaceInfo(r.race_info, liveOddsDict.wind);
        }
        r.meta = r.meta || {};
        r.meta.odds_patch_applied_at = new Date().toISOString();
        return r;
    }

    async function fetchHKOObservedJSON() {
        if (typeof fetch !== 'function') return null;
        try {
            const r = await fetch(HKO_OBS_URL, { cache: 'no-store' });
            if (!r.ok) return null;
            return await r.json();
        } catch (e) { return null; }
    }

    function extractShaTinHappyValleyFromHKO(hkoJson) {
        const out = { ST: null, HV: null };
        if (!hkoJson || !Array.isArray(hkoJson.temperature)) return out;
        const tryFind = function (nameLike, arr, field) {
            for (let i = 0; i < (arr || []).length; i++) {
                const n = String(arr[i].place || '');
                if (n.indexOf(nameLike) >= 0) return _num(arr[i][field], NaN);
            }
            return NaN;
        };
        const stTemp = tryFind('沙田', hkoJson.temperature, 'value');
        const hvTemp = tryFind('跑馬地', hkoJson.temperature, 'value');
        const stHum = tryFind('沙田', hkoJson.humidity, 'value');
        const hvHum = tryFind('跑馬地', hkoJson.humidity, 'value');
        const uv = tryFind('京士柏', hkoJson.uvindex, 'value');
        let stWind = null, hvWind = null;
        (hkoJson.wind || []).forEach(function (w) {
            const p = String(w.place || '');
            if (p.indexOf('沙田') >= 0) stWind = { kmh: _num(w.windSpeed, 0) * 3.6, deg: _num(parseInt((w.windDirection || '0').match(/\d+/) || [0], 10), 0) };
            if (p.indexOf('跑馬地') >= 0 || p.indexOf('天星') >= 0) hvWind = { kmh: _num(w.windSpeed, 0) * 3.6, deg: _num(parseInt((w.windDirection || '0').match(/\d+/) || [0], 10), 0) };
        });
        out.ST = { air_temp_c: stTemp, humidity_pct: stHum, wind_speed_kmh: stWind ? stWind.kmh : 0, wind_direction_deg: stWind ? stWind.deg : NaN, uv_index: uv };
        out.HV = { air_temp_c: hvTemp, humidity_pct: hvHum, wind_speed_kmh: hvWind ? hvWind.kmh : 0, wind_direction_deg: hvWind ? hvWind.deg : NaN, uv_index: uv };
        return out;
    }

    global.HorseAIScraperSchema = {
        SCHEMA_VERSION: SCHEMA_VERSION,
        HKO_OBS_URL: HKO_OBS_URL,
        WIND_HOME_STRAIGHT_DEG: WIND_HOME_STRAIGHT_DEG,
        enrichRaceInfo: enrichRaceInfo,
        enrichHorseWithDeltas: enrichHorseWithDeltas,
        applyLiveOddsPatch: applyLiveOddsPatch,
        fetchHKOObservedJSON: fetchHKOObservedJSON,
        extractShaTinHappyValleyFromHKO: extractShaTinHappyValleyFromHKO
    };
    if (global.window && !global.window.HorseAIScraperSchema) global.window.HorseAIScraperSchema = global.HorseAIScraperSchema;
})(typeof window !== 'undefined' ? window : (typeof self !== 'undefined' ? self : globalThis));
