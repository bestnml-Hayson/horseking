/* =========================================================
   賽馬 AI Live APP - 黑金 Mobile First 版本
   ========================================================= */
(function () {
  'use strict';

  const DB = {
    races: {},
    raceIndex: [],
    horsesDB: {},
    jockeysDB: {},
    trainersDB: {},
    trackwork: {},
    jockeyHorseStats: {},
    horseDistanceStats: {},
    classStats: {},
    historyStats: null,
    currentRaceId: null,
    raceFilter: 'all'
  };
  window.DB = DB;
  window.RacingAugmented = {
    get horses() { return DB.horsesDB; },
    get jockeys() { return DB.jockeysDB; },
    get trainers() { return DB.trainersDB; },
    get trackwork() { return DB.trackwork; },
    get jockeyHorse() { return DB.jockeyHorseStats; },
    get horseDistance() { return DB.horseDistanceStats; },
    get classStats() { return DB.classStats; }
  };
  const $ = function (id) { return document.getElementById(id); };

  function toast(msg, type) {
    const t = $('toast');
    if (!t) return;
    t.textContent = msg;
    t.className = 'toast show ' + (type || '');
    clearTimeout(t._tid);
    t._tid = setTimeout(function () { t.className = 'toast'; }, 2800);
  }
  window.showToast = toast;

  async function api(path) {
    try {
      const r = await fetch(path, { cache: 'no-store' });
      return r.ok ? await r.json() : null;
    } catch (e) {
      return null;
    }
  }

  /* ========== 馬匹詳細資料 Modal ========== */
  function currentRaceHorses() {
    if (!DB.currentRaceId || !DB.races[DB.currentRaceId]) return [];
    const id = DB.currentRaceId;
    if (DB._scoredHorses && DB._scoredHorses[id]) return DB._scoredHorses[id];
    const raw = DB.races[id].horses || [];
    const hasScore = raw.some(function (h) { return h.scores && typeof h.scores.total === 'number'; });
    if (hasScore) return raw;
    const ana = DB._analysisCache && DB._analysisCache[id];
    if (ana && ana.all_ranked_horses && ana.all_ranked_horses.length) {
      DB._scoredHorses = DB._scoredHorses || {};
      DB._scoredHorses[id] = ana.all_ranked_horses;
      return ana.all_ranked_horses;
    }
    if (window.RacingAI && typeof window.RacingAI.runFullAnalysis === 'function') {
      try {
        const fresh = window.RacingAI.runFullAnalysis(DB.races[id]);
        const scored = fresh && fresh.all_ranked_horses ? fresh.all_ranked_horses : raw;
        if (scored && scored.length) {
          DB._analysisCache = DB._analysisCache || {};
          DB._analysisCache[id] = fresh;
          DB._scoredHorses = DB._scoredHorses || {};
          DB._scoredHorses[id] = scored;
        }
        return scored;
      } catch (e) {
        console.warn('score fallback err', e);
        return raw;
      }
    }
    return raw;
  }
  function findHorseByAny(numberOrName) {
    const horses = currentRaceHorses();
    const n = parseInt(numberOrName, 10);
    if (!isNaN(n)) {
      const byNo = horses.find(function (h) { return h.number === n; });
      if (byNo) return byNo;
    }
    if (typeof numberOrName === 'string' && numberOrName) {
      return horses.find(function (h) { return h.name === numberOrName; }) || null;
    }
    return null;
  }
  function openHorseDetail(numberOrName) {
    const h = findHorseByAny(numberOrName);
    if (!h) { toast('未找到該馬匹資料', 'warn'); return; }
    const race = DB.currentRaceId ? DB.races[DB.currentRaceId] : null;
    const raceInfo = race ? race.race_info : {};
    const meta = race ? (race.meta || {}) : {};
    const rawHorses = race ? (race.horses || []) : [];
    const baseScores = h.scores && typeof h.scores.last3 === 'number' ? h.scores : (function () {
      const rHorses = rawHorses.length ? rawHorses : [h];
      function minMax(arr, invert) {
        if (!arr || arr.length === 0) return {};
        let min = arr[0], max = arr[0];
        for (let i = 1; i < arr.length; i++) { const v = arr[i]; if (v < min) min = v; if (v > max) max = v; }
        const r = max - min;
        const map = {};
        arr.forEach(function (v) {
          const norm = r <= 0 ? 50 : Math.round((invert ? (max - v) / r : (v - min) / r) * 1000) / 10;
          map[v] = Math.max(5, Math.min(95, isNaN(norm) ? 50 : norm));
        });
        return map;
      }
      const ratings = rHorses.map(function (x) { return x.rating || 0; });
      const timesRaw = rHorses.map(function (x) { return x.best_time_sec || 999; });
      const _tReal = timesRaw.filter(function (t) { return Number.isFinite(t) && t > 0 && t < 900; });
      const _tMed = _tReal.length ? _tReal.slice().sort(function (a, b) { return a - b; })[Math.max(0, Math.floor(_tReal.length / 2))] : 90;
      const times = timesRaw.map(function (t) { return Number.isFinite(t) && t > 0 && t < 900 ? t : _tMed; });
      const draws = rHorses.map(function (x) { return x.draw || 100; });
      const weights = rHorses.map(function (x) { return x.weight || 0; });
      const oddsRaw = rHorses.map(function (x) { return x.odds_win || 999; });
      const _oReal = oddsRaw.filter(function (o) { return Number.isFinite(o) && o > 0 && o < 900; });
      const _invMed = _oReal.length ? (function () {
        const arr = _oReal.map(function (o) { return 100 / (o > 0 ? o : 1); }).sort(function (a, b) { return a - b; });
        return arr[Math.max(0, Math.floor(arr.length / 2))];
      })() : 4;
      const invO = oddsRaw.map(function (o) { return (Number.isFinite(o) && o > 0 && o < 900) ? (100 / o) : _invMed; });
      const rm = minMax(ratings), tm = minMax(times, true), dm = minMax(draws, true), wm = minMax(weights), om = minMax(invO);
      const sLast3 = (function (ls) { if (!ls || !ls.length) return 50; let t = 0; ls.forEach(function (r) { const f = typeof r === 'number' ? r : (r && typeof r.finish === 'number' ? r.finish : 14); if (f === 1) t += 100; else if (f === 2) t += 85; else if (f === 3) t += 70; else if (f <= 6) t += 50; else if (f <= 10) t += 35; else t += 15; }); return Math.round((t / ls.length) * 10) / 10; })(h.last_3);
      const _hBt = (Number.isFinite(h.best_time_sec) && h.best_time_sec > 0 && h.best_time_sec < 900) ? h.best_time_sec : _tMed;
      const _hInv = (Number.isFinite(h.odds_win) && h.odds_win > 0 && h.odds_win < 900) ? (100 / h.odds_win) : _invMed;
      return {
        last3: sLast3, rating: rm[h.rating] || 50, time: tm[_hBt] || 50,
        draw: dm[h.draw] || 50, weight: wm[h.weight] || 50, odds: om[_hInv] || 50,
        trackwork: 50, distance: 50, synergy: 50, trend: 50, base6: 50, total: 50
      };
    })();
    const aug = h.aug || {};
    const raceClass = raceInfo.class || (meta.class ? meta.class : '');
    const dist = raceInfo.distance_m || 0;
    const jB = typeof window.jockeyBonus === 'function' ? window.jockeyBonus(h.jockey, dist, h.trainer) : 0;
    const tB = typeof window.trainerBonus === 'function' ? window.trainerBonus(h.trainer, dist) : 0;
    const _dashboardTotal = (h.scores && typeof h.scores.total === 'number' && h.scores.total > 0) ? h.scores.total : 0;
    const _tmpForm = 50;
    const _tmpExcept = 80;
    const _tmpVet = 90;
    const _base6 = baseScores.last3 * 0.30 + baseScores.rating * 0.20 + baseScores.time * 0.15 + baseScores.draw * 0.15 + baseScores.weight * 0.10 + baseScores.odds * 0.10;
    const _baseAug = twScore * 0.12 + _tmpForm * 0.10 + _tmpExcept * 0.10 + _tmpVet * 0.08 + distScore * 0.03 + synScore * 0.03 + trScore * 0.03;
    const _popupCalcTotal = Math.round((_base6 * 0.54 + _baseAug) * 10) / 10;
    const s = Object.assign({}, baseScores, {
      jockey_bonus: (typeof baseScores.jockey_bonus === 'number' && baseScores.jockey_bonus > 0) ? baseScores.jockey_bonus : (isNaN(jB) ? 0 : jB),
      trainer_bonus: (typeof baseScores.trainer_bonus === 'number' && baseScores.trainer_bonus > 0) ? baseScores.trainer_bonus : (isNaN(tB) ? 0 : tB),
      base6: _base6,
      total: _dashboardTotal > 0 ? _dashboardTotal : _popupCalcTotal
    });
    $('hdName').textContent = h.name || '';
    $('hdMeta').textContent = '#' + (h.number || '?') + ' · ' + (h.draw || '?') + '檔 · ' + (raceInfo.venue || '') + ' ' + (raceInfo.distance_m || '') + 'm · ' + raceClass;

    const basic = [
      { k: '評分', v: h.rating || '-' },
      { k: '體重', v: (h.weight || '-') + (h.weight ? ' 磅' : '') },
      { k: '騎師', v: h.jockey || '-' },
      { k: '練馬師', v: h.trainer || '-' },
      { k: '最佳時間', v: (h.best_time_sec && typeof h.best_time_sec === 'number' && h.best_time_sec < 999 && h.best_time_sec > 0) ? h.best_time_sec + 's' : '--' },
      { k: '檔位', v: (h.draw || '?') + ' 檔' },
      { k: '獨贏賠率', v: (typeof h.odds_win === 'number' && h.odds_win > 0 && h.odds_win < 999) ? (Math.round(h.odds_win * 10) / 10).toFixed(1) + 'x' : '--' },
      { k: '位置賠率', v: (typeof h.odds_place === 'number' && h.odds_place > 0 && h.odds_place < 999) ? (Math.round(h.odds_place * 10) / 10).toFixed(1) + 'x' : '--' }
    ];
    const basicHtml = '<div class="hd-grid">' + basic.map(function (c) {
      return '<div class="cell"><span class="k">' + c.k + '</span><span class="v">' + c.v + '</span></div>';
    }).join('') + '</div>';

    const augTW = aug.trackwork || (window.RacingAI && window.RacingAI.analyzeTrackwork ? window.RacingAI.analyzeTrackwork(h.code, DB.currentRaceId || '', h.jockey, raceInfo.venue || '') : null);
    const augDist = aug.distance || (window.RacingAI && window.RacingAI.analyzeDistanceSpecialty ? window.RacingAI.analyzeDistanceSpecialty(h.code, dist, raceInfo.venue || '') : null);
    const augSyn = aug.synergy || (window.RacingAI && window.RacingAI.analyzeJockeyHorseSynergy ? window.RacingAI.analyzeJockeyHorseSynergy(h.code, h.jockey) : null);
    const augTr = aug.trend || (window.RacingAI && window.RacingAI.analyzeRatingTrend && DB.horsesDB ? window.RacingAI.analyzeRatingTrend(h.code, h.rating, raceClass, DB.horsesDB[h.code] || null) : null);
    const twScore = typeof s.trackwork === 'number' && s.trackwork > 0 ? s.trackwork : (augTW && typeof augTW.score === 'number' ? augTW.score : 50);
    const distScore = typeof s.distance === 'number' && s.distance > 0 ? s.distance : (augDist && typeof augDist.score === 'number' ? augDist.score : 50);
    const synScore = typeof s.synergy === 'number' && s.synergy > 0 ? s.synergy : (augSyn && typeof augSyn.score === 'number' ? augSyn.score : 50);
    const trScore = typeof s.trend === 'number' && s.trend > 0 ? s.trend : (augTr && typeof augTr.score === 'number' ? augTr.score : 50);
    const formScore = (typeof s.form === 'number' && isFinite(s.form)) ? s.form : 50;
    const vetScore = (typeof s.vet === 'number' && isFinite(s.vet)) ? s.vet : 90;
    const exceptScore = (typeof s.except === 'number' && isFinite(s.except)) ? s.except : 80;
    if (!(s.form > 0)) s.form = formScore;
    if (!(s.vet > 0)) s.vet = vetScore;
    if (!(s.except > 0)) s.except = exceptScore;
    if (!(_dashboardTotal > 0)) {
      const _base6Revised = s.last3 * 0.30 + s.rating * 0.20 + s.time * 0.15 + s.draw * 0.15 + s.weight * 0.10 + s.odds * 0.10;
      const _baseAugRevised = twScore * 0.12 + formScore * 0.10 + exceptScore * 0.10 + vetScore * 0.08 + distScore * 0.03 + synScore * 0.03 + trScore * 0.03;
      s.total = Math.round((_base6Revised * 0.54 + _baseAugRevised) * 10) / 10;
      s.base6 = _base6Revised;
    }
    const formTitle = (aug.form_detail && aug.form_detail.note) ? String(aug.form_detail.note).slice(0, 80) : '近績形勢線分析';
    const vetFlags = (aug.vet_detail && Array.isArray(aug.vet_detail.flags)) ? aug.vet_detail.flags : [];
    const vetNote = (aug.vet_detail && aug.vet_detail.note) ? String(aug.vet_detail.note).slice(0, 80) : '獸醫健康檢查';
    const vetTitle = vetFlags.length ? (vetFlags.join('、') + ' · ' + vetNote) : vetNote;
    const exceptFlags = (aug.except_detail && Array.isArray(aug.except_detail.flags)) ? aug.except_detail.flags : [];
    const exceptNote = (aug.except_detail && aug.except_detail.note) ? String(aug.except_detail.note).slice(0, 80) : '異常因素分析';
    const exceptTitle = exceptFlags.length ? (exceptFlags.join('、') + ' · ' + exceptNote) : exceptNote;

    const scoreList = [
      { k: '🎖️ 晨操狀態 (12%)', n: twScore, note: augTW ? (augTW.detail || '') : '晨操紙 + 晨操歷史狀態混合' },
      { k: '🎯 近績形勢 (10%)', n: formScore, note: formTitle },
      { k: '⚠️ 異常因素 (10%)', n: exceptScore, note: exceptTitle },
      { k: '🏥 獸醫健康 (8%)', n: vetScore, note: vetTitle },
      { k: '📏 路程專長 (3%)', n: distScore, note: augDist ? (augDist.detail || '') : '同路程往績分析' },
      { k: '🤝 騎練默契 (3%)', n: synScore, note: augSyn ? (augSyn.detail || '') : '騎師 × 馬匹往績' },
      { k: '📈 同班走勢 (3%)', n: trScore, note: augTr ? (augTr.detail || '') : '評分走勢 + 班次升降' },
      { k: '🏁 近績質素 (30% base)', n: s.last3 || 0, note: '近3仗名次評分' },
      { k: '⭐ 評分實力 (20% base)', n: s.rating || 0, note: '現有評分轉換' },
      { k: '⏱️ 最佳時間 (15% base)', n: s.time || 0, note: (h.best_time_sec && typeof h.best_time_sec === 'number' && h.best_time_sec < 900) ? ('實測 ' + h.best_time_sec + 's 轉換') : '暫無數據 → 全中位數中性評分' },
      { k: '🚪 檔位優勢 (15% base)', n: s.draw || 0, note: '檔位內檔/外檔優勢' },
      { k: '⚖️ 體態/負磅 (10% base)', n: s.weight || 0, note: '負磅相對馬匹評分' },
      { k: '💰 市場預期 (10% base)', n: s.odds || 0, note: (Number.isFinite(h.odds_win) && h.odds_win > 0 && h.odds_win < 900) ? ('實際賠率 ' + h.odds_win.toFixed(1) + 'x 倒數熱度') : '暫無即時賠率 → 全中位數中性評分' }
    ];
    const jTSection = [
      { k: '騎師加成 (14%)', n: s.jockey_bonus || 0, note: s.jockey_bonus > 0 ? '+' + s.jockey_bonus.toFixed(1) + ' 分（騎師路程/班次表現）' : '0 分' },
      { k: '練馬師加成 (12%)', n: s.trainer_bonus || 0, note: s.trainer_bonus > 0 ? '+' + s.trainer_bonus.toFixed(1) + ' 分（練馬師路程/班次表現）' : '0 分' }
    ];
    const scoreHtml = scoreList.map(function (r) {
      const pct = Math.min(100, Math.max(0, r.n));
      const note = r.note ? (' <span style="color:var(--text-dim);margin-left:8px;font-size:11px;">— ' + r.note + '</span>') : '';
      return '<div class="score-bar-row"><span class="k">' + r.k + '</span>' +
        '<div class="bar"><div style="width:' + pct + '%;"></div></div>' +
        '<span class="n">' + (typeof r.n === 'number' ? r.n.toFixed(1) : r.n) + '</span></div>' + note;
    }).join('') +
      jTSection.map(function (r) {
        const pct = Math.min(100, Math.max(0, r.n));
        const note = r.note ? (' <span style="color:var(--text-dim);margin-left:8px;font-size:11px;">— ' + r.note + '</span>') : '';
        return '<div class="score-bar-row"><span class="k">' + r.k + '</span>' +
          '<div class="bar" style="background:linear-gradient(90deg,#2a1a0a,#5a3a10);"><div style="width:' + pct + '%;background:linear-gradient(90deg,#8a5a20,#f0c050);"></div></div>' +
          '<span class="n" style="color:var(--gold);">' + (typeof r.n === 'number' ? r.n.toFixed(1) : r.n) + '</span></div>' + note;
      }).join('') +
      '<div class="hd-total"><div><div class="label">AI 總分（基礎 54% + 增強 46%）</div>' +
      '<div style="color:var(--text-dim);font-size:11px;margin-top:2px;">base6 (近績+評分+步速+檔位+負磅+預期) 54% · 晨操12%/形勢10%/異常10%/獸醫8% · 路3%/契3%/勢3% · 騎師14% · 練馬師12%</div></div>' +
      '<div class="val">' + (s.total ? s.total.toFixed(1) : (s.base6 ? s.base6.toFixed(1) : '50.0')) + '</div></div>';

    const last3 = h.last_3 || [];
    let last3Html = '';
    if (last3.length === 0) {
      last3Html = '<div style="color:var(--text-dim);font-size:12px;">暫無近績紀錄（新馬或首次出賽）</div>';
    } else {
      last3Html = '<table class="hd-table"><thead><tr>' +
        '<th>日期</th><th>場地</th><th>賽事</th><th>距離</th><th>班次</th><th>名次</th></tr></thead><tbody>' +
        last3.map(function (r, idx) {
          const fin = typeof r === 'number' ? r : (r && typeof r.finish === 'number' ? r.finish : 99);
          const finCls = fin === 1 ? 'fin-1' : (fin === 2 ? 'fin-2' : (fin === 3 ? 'fin-3' : ''));
          const finStr = fin <= 20 ? fin : '—';
          const isNumRow = typeof r === 'number';
          const d = (!isNumRow && r && r.date) ? r.date : (['最近 1 仗', '最近 2 仗', '最近 3 仗'][idx] || '');
          const v = (!isNumRow && r && r.venue) ? r.venue : (isNumRow ? '—' : '');
          const rn = (!isNumRow && r && typeof r.race_no === 'number') ? ('R' + r.race_no) : '';
          const dm = (!isNumRow && r && r.distance_m) ? (r.distance_m + 'm') : '';
          const cl = (!isNumRow && r && r.class) ? r.class : '';
          return '<tr><td>' + d + '</td><td>' + v + '</td><td>' + rn + '</td><td>' + dm + '</td><td>' + cl + '</td>' +
            '<td class="' + finCls + '"><b>' + finStr + '</b></td></tr>';
        }).join('') + '</tbody></table>';
    }

    const augExtras = [];
    if (h.core_advantage) augExtras.push({ k: '✨ AI 核心優勢', v: h.core_advantage });
    if (h.flags && h.flags.length) augExtras.push({ k: '🚩 留意事項', v: h.flags.join('、') });
    if (meta.odds_update_time) augExtras.push({ k: '🕐 即時賠率更新', v: meta.odds_update_time + (meta.odds_source ? '（' + meta.odds_source.split(' live: ')[0] + '）' : '') });
    const extraHtml = augExtras.length ? ('<div class="hd-grid">' + augExtras.map(function (c) {
      return '<div class="cell" style="grid-column:span 2;"><span class="k">' + c.k + '</span><span class="v">' + c.v + '</span></div>';
    }).join('') + '</div>') : '';

    const ccChips = [];
    if (typeof h.cc_expert_count === 'number' && h.cc_expert_count > 0) {
      const experts = Array.isArray(h.cc_experts) ? h.cc_experts.filter(Boolean).join('、') : '';
      const tips = Array.isArray(h.cc_expert_tips) && h.cc_expert_tips.length
        ? h.cc_expert_tips.map(function (t) { return t.expert + '(第' + t.rank + '挑)'; }).join('、')
        : '';
      ccChips.push('<div style="display:flex;flex-direction:column;gap:4px;padding:8px 10px;border-radius:8px;background:linear-gradient(135deg,rgba(240,90,90,0.14),rgba(240,160,60,0.08));border:1px solid rgba(240,120,90,0.35);">' +
        '<div style="display:flex;align-items:center;gap:6px;"><span style="font-size:18px;">🔥</span><b style="font-size:13px;color:#ff9d6a;">' + h.cc_expert_count + ' 位名家最後來料推薦</b></div>' +
        (experts ? '<div style="font-size:11px;color:var(--text-dim);">推薦名家：' + experts + '</div>' : '') +
        (tips ? '<div style="font-size:11px;color:var(--text-dim);">排名：' + tips + '</div>' : '') +
        '</div>');
    }
    const barrierDiffs = [];
    if (h.cc_draw_oncc && h.cc_draw_oncc !== h.draw) barrierDiffs.push('檔位：馬會' + h.draw + ' → 東方' + h.cc_draw_oncc);
    if (h.cc_jockey_oncc && h.cc_jockey_oncc !== h.jockey) barrierDiffs.push('騎師：馬會' + (h.jockey || '—') + ' → 東方' + h.cc_jockey_oncc);
    if (typeof h.cc_weight_change === 'number' && h.cc_weight_change !== 0) barrierDiffs.push('負磅變動：' + (h.cc_weight_change > 0 ? '+' : '') + h.cc_weight_change + ' 磅');
    if (typeof h.cc_rating_change === 'number' && h.cc_rating_change !== 0) barrierDiffs.push('評分變動：' + (h.cc_rating_change > 0 ? '+' : '') + h.cc_rating_change + ' 分');
    if (typeof h.cc_body_weight_change === 'number' && h.cc_body_weight_change !== 0) barrierDiffs.push('排位體重變動：' + (h.cc_body_weight_change > 0 ? '+' : '') + h.cc_body_weight_change + ' 磅');
    if (h.cc_equipment && h.cc_equipment !== '—') barrierDiffs.push('配備：' + h.cc_equipment);
    if (h.cc_gear_symbols && String(h.cc_gear_symbols).trim() !== '') barrierDiffs.push('裝備符號：' + String(h.cc_gear_symbols).trim());
    if (h.cc_trainer_surname || h.cc_trainer_oncc) {
      const tn = h.cc_trainer_oncc || h.cc_trainer_surname;
      if (tn && tn !== h.trainer) barrierDiffs.push('練馬師核對：東方' + tn);
    }
    if (h.cc_name_oncc && h.cc_name_oncc !== h.name) barrierDiffs.push('馬名異體：' + h.cc_name_oncc);
    if (barrierDiffs.length) {
      ccChips.push('<div style="padding:8px 10px;border-radius:8px;background:rgba(120,180,255,0.08);border:1px solid rgba(100,160,240,0.3);">' +
        '<div style="display:flex;align-items:center;gap:6px;margin-bottom:3px;"><span style="font-size:16px;">🏇</span><b style="font-size:13px;color:#7fb0ff;">東方日報排位差異</b></div>' +
        '<div style="font-size:11px;color:var(--text-dim);display:flex;flex-direction:column;gap:2px;">' +
        barrierDiffs.map(function (x) { return '<div>• ' + x + '</div>'; }).join('') +
        '</div></div>');
    }
    let twHtml = '';
    if (h.cc_trackwork_summary || h.cc_trackwork_daily) {
      const dailyRows = [];
      if (h.cc_trackwork_daily && typeof h.cc_trackwork_daily === 'object') {
        const keys = Object.keys(h.cc_trackwork_daily);
        keys.forEach(function (k) {
          const v = h.cc_trackwork_daily[k];
          if (v === '—' || (typeof v === 'string' && v.trim() === '')) return;
          dailyRows.push('<div style="display:grid;grid-template-columns:72px 1fr;gap:6px;padding:3px 0;border-bottom:1px dashed rgba(255,255,255,0.06);">' +
            '<span style="color:var(--gold);font-size:11px;font-weight:700;">' + k + ' 日</span>' +
            '<span style="font-size:11px;color:var(--text-dim);">' + v + '</span></div>');
        });
      }
      twHtml = '<div style="padding:8px 10px;border-radius:8px;background:rgba(120,220,160,0.07);border:1px solid rgba(80,200,140,0.3);">' +
        '<div style="display:flex;align-items:center;gap:6px;margin-bottom:5px;"><span style="font-size:16px;">🌅</span><b style="font-size:13px;color:#6ddfa0;">晨操摘要（東方日報）</b></div>' +
        '<div style="font-size:11px;color:var(--text);line-height:1.55;">' + (h.cc_trackwork_summary || '—') + '</div>' +
        (dailyRows.length ? '<div style="margin-top:6px;">' + dailyRows.join('') + '</div>' : '') +
        '</div>';
    }
    const ccSectionHtml = (ccChips.length || twHtml)
      ? ('<div style="display:flex;flex-direction:column;gap:6px;">' + ccChips.join('') + twHtml + '</div>')
      : '<div style="color:var(--text-dim);font-size:12px;">暫未匯入東方日報對應數據</div>';

    $('hdBody').innerHTML =
      '<div class="hd-section"><h4>📋 基本資料</h4>' + basicHtml + '</div>' +
      (extraHtml ? ('<div class="hd-section"><h4>💡 賽前情報</h4>' + extraHtml + '</div>') : '') +
      '<div class="hd-section"><h4>📰 東方日報情報</h4>' + ccSectionHtml + '</div>' +
      '<div class="hd-section"><h4>🧠 13 維度評分（+2 騎練加成）</h4>' + scoreHtml + '</div>' +
      '<div class="hd-section"><h4>📜 近三仗完整紀錄</h4>' + last3Html + '</div>';

    $('horseDetailModal').style.display = 'flex';
    document.body.style.overflow = 'hidden';
  }
  function closeHorseDetail() {
    $('horseDetailModal').style.display = 'none';
    document.body.style.overflow = '';
  }
  window.openHorseDetail = openHorseDetail;
  window.closeHorseDetail = closeHorseDetail;

  function bindHorseClick() {
    document.addEventListener('click', function (e) {
      const el = e.target.closest('.horse-click');
      if (!el) return;
      const no = el.dataset.number;
      const nm = el.dataset.name;
      if (no || nm) openHorseDetail(no || nm);
    });
    const mask = $('horseDetailModal');
    if (mask) {
      mask.addEventListener('click', function (e) {
        if (e.target === mask) closeHorseDetail();
      });
    }
    const jmask = $('jockeyDetailModal');
    if (jmask) {
      jmask.addEventListener('click', function (e) {
        if (e.target === jmask) closeJockeyDetail();
      });
    }
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        if (mask && mask.style.display === 'flex') closeHorseDetail();
        if (jmask && jmask.style.display === 'flex') closeJockeyDetail();
        const rp = $('racePickerModal');
        if (rp && rp.style.display === 'flex') closeRacePicker();
      }
    });
  }

  /* ========== 騎師詳細 Modal ========== */
  function finishBadge(finish) {
    if (!finish || finish === 0 || finish === '0') return '<span style="color:var(--text-dim);font-weight:600;">—</span>';
    const n = Number(finish);
    if (!Number.isFinite(n)) return '<span style="color:var(--text-dim);">' + finish + '</span>';
    if (n === 1) return '<span style="color:#fde68a;background:rgba(212,175,55,0.15);padding:2px 8px;border-radius:10px;font-weight:800;">🥇 第1</span>';
    if (n === 2) return '<span style="color:#cbd5e1;background:rgba(203,213,225,0.12);padding:2px 8px;border-radius:10px;font-weight:800;">🥈 第2</span>';
    if (n === 3) return '<span style="color:#fcd34d;background:rgba(180,83,9,0.15);padding:2px 8px;border-radius:10px;font-weight:800;">🥉 第3</span>';
    if (n <= 4) return '<span style="color:#60a5fa;background:rgba(59,130,246,0.12);padding:2px 8px;border-radius:10px;font-weight:700;">💎 第' + n + '</span>';
    if (n <= 6) return '<span style="color:#86efac;background:rgba(34,197,94,0.10);padding:2px 8px;border-radius:10px;font-weight:600;">第' + n + '</span>';
    return '<span style="color:var(--text-dim);font-weight:600;">第' + n + '</span>';
  }
  function openJockeyDetail(name) {
    if (!name) { toast('未指定騎師', 'warn'); return; }
    const j = (DB.jockeysDB && DB.jockeysDB[name]) || null;
    if (!j) { toast('騎師數據未備份，請稍後重試', 'warn'); return; }
    $('jdName').textContent = name + ' 騎師';
    const upcoming = (typeof getUpcomingCounts === 'function') ? getUpcomingCounts() : { jockeyRides: {} };
    const tonight = (upcoming.jockeyRides && upcoming.jockeyRides[name]) || 0;
    const wrPct = Math.round((typeof j.win_rate === 'number' ? j.win_rate : (j.starts ? (j.wins || 0) / j.starts : 0)) * 100);
    const prPct = Math.round((typeof j.q_rate === 'number' ? j.q_rate : (j.starts ? (j.q_count || 0) / j.starts : 0)) * 100);
    $('jdSub').textContent = '今季出賽 ' + (j.starts || 0) + ' 場 · 勝出 ' + (j.wins || 0) + ' 場 · 入Q ' + (j.q_count || 0) + ' 場 · 今晚 ' + tonight + ' 場';
    const rides = (j.rides && j.rides.length) ? j.rides : [];
    const last10 = rides.slice(0, 50);
    const recent10 = rides.slice(0, 10);
    const recentWins = recent10.filter(function (r) { return r.won || (Number(r.finish) === 1); }).length;
    const recentQ = recent10.filter(function (r) { return r.in_quinella || (Number(r.finish) >= 1 && Number(r.finish) <= 4); }).length;
    const avgFinRecent = (function () {
      var t = 0, cnt = 0;
      recent10.forEach(function (r) { var f = Number(r.finish); if (f && f > 0) { t += f; cnt++; } });
      return cnt ? (t / cnt).toFixed(1) : '—';
    })();
    const header = '<div class="score-grid" style="margin-bottom:14px;">' +
      '<div class="score-item"><div class="score-label">今季勝率</div><div class="score-value" style="color:var(--gold);">' + wrPct + '%</div></div>' +
      '<div class="score-item"><div class="score-label">今季入Q率</div><div class="score-value">' + prPct + '%</div></div>' +
      '<div class="score-item"><div class="score-label">近10場 勝/入Q</div><div class="score-value">' + recentWins + '/' + recentQ + '</div></div>' +
      '<div class="score-item"><div class="score-label">近10場 平均名次</div><div class="score-value">' + avgFinRecent + '</div></div>' +
      '</div>';
    let tbl = '';
    if (!last10.length) {
      tbl = '<div style="padding:40px;text-align:center;color:var(--text-dim);">暫無已完賽往績（剛剛加入數據）</div>';
    } else {
      tbl = '<h3 style="margin:18px 0 10px;font-size:14px;color:var(--gold);">📋 已完賽往績（最新 ' + last10.length + ' 場，共 ' + rides.length + ' 場）</h3>' +
        '<div style="max-height:55vh;overflow:auto;border:1px solid var(--border);border-radius:10px;">' +
        '<table class="data-table" style="border:none;">' +
        '<thead><tr>' +
        '<th>日期</th><th>場地/場次</th><th>距離/班次</th><th>馬匹</th><th>檔</th><th>負磅</th><th>評分</th><th>名次</th><th>獨贏賠率</th>' +
        '</tr></thead><tbody>' +
        last10.map(function (r) {
          var rd = (r.race_date || '').slice(5);
          var ven = r.venue || (r.venue_code === 'ST' ? '沙田' : (r.venue_code === 'HV' ? '跑馬地' : r.venue_code));
          var venueShort = (ven === '沙田' ? '沙' : (ven === '跑馬地' ? '谷' : ven));
          var r2 = r.distance_m + 'm';
          if (r.track) r2 += ' · ' + r.track;
          if (r.class) r2 += ' · ' + r.class;
          var hName = (r.horse_name || r.horse_code || '—');
          var clickable = r.race_id && (r.horse_code || r.horse_name)
            ? '<span style="cursor:pointer;text-decoration:underline dotted;text-decoration-color:rgba(212,175,55,0.45);text-underline-offset:3px;" ' +
              'onclick="closeJockeyDetail();setTimeout(function(){selectRaceId(\'' + r.race_id + '\');setTimeout(function(){openHorseDetail(\'' + (r.horse_name || r.horse_code || '').replace(/'/g,"\\'") + '\');}, 400);}, 120);">' + hName + '</span>'
            : hName;
          var dr = r.draw || '—';
          var wt = r.weight || '—';
          var rtg = r.rating || '—';
          var ow = (r.odds_win && Number(r.odds_win) > 0) ? ('$' + Number(r.odds_win).toFixed(1)) : '—';
          return '<tr>' +
            '<td>' + rd + '</td>' +
            '<td><b>' + venueShort + ' R' + (r.race_number || '?') + '</b></td>' +
            '<td style="font-size:12px;">' + r2 + '</td>' +
            '<td><b>' + clickable + '</b></td>' +
            '<td>' + dr + '</td>' +
            '<td>' + wt + '</td>' +
            '<td>' + rtg + '</td>' +
            '<td>' + finishBadge(r.finish) + '</td>' +
            '<td style="color:var(--gold);font-weight:700;">' + ow + '</td>' +
            '</tr>';
        }).join('') +
        '</tbody></table></div>';
    }
    $('jdBody').innerHTML = header + tbl;
    $('jockeyDetailModal').style.display = 'flex';
    document.body.style.overflow = 'hidden';
  }
  function closeJockeyDetail() {
    const m = $('jockeyDetailModal');
    if (m) m.style.display = 'none';
    document.body.style.overflow = '';
  }
  window.openJockeyDetail = openJockeyDetail;
  window.closeJockeyDetail = closeJockeyDetail;

  /* ========== 賽事選擇器 Modal ========== */
  let racePickerDate = null;
  function getRaceByDateMap() {
    const map = {};
    if (!DB.raceIndex || !DB.raceIndex.length) return map;
    DB.raceIndex.forEach(function (id) {
      const info = DB.races[id].race_info || {};
      const k = info.race_date;
      if (!k) return;
      if (!map[k]) map[k] = [];
      map[k].push(id);
    });
    Object.keys(map).forEach(function (k) {
      map[k].sort(function (a, b) {
        return (DB.races[a].race_info.race_number || 0) - (DB.races[b].race_info.race_number || 0);
      });
    });
    return map;
  }
  function todayStr() {
    const d = new Date();
    const pad = function (n) { return n < 10 ? '0' + n : n; };
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
  }
  function openRacePicker() {
    if (!DB.raceIndex || !DB.raceIndex.length) {
      toast('數據載入中，請稍後', 'warn'); return;
    }
    racePickerDate = null;
    renderRacePicker();
    $('racePickerModal').style.display = 'flex';
    document.body.style.overflow = 'hidden';
  }
  function closeRacePicker() {
    $('racePickerModal').style.display = 'none';
    document.body.style.overflow = '';
    racePickerDate = null;
  }
  function racePickerBack() {
    racePickerDate = null;
    renderRacePicker();
  }
  function selectRaceDate(dateKey) {
    racePickerDate = dateKey;
    renderRacePicker();
  }
  function selectRaceId(id) {
    closeRacePicker();
    const navItem = document.querySelector('.nav-item[data-tab="race"]');
    if (navItem) navItem.click();
    setTimeout(function () {
      DB.currentRaceId = id;
      renderRaceCards();
      const card = document.querySelector('.race-card[data-raceid="' + id + '"]');
      if (card) {
        card.classList.add('expanded');
        const bodyId = 'raceBody_' + id.replace(/[^a-zA-Z0-9]/g, '_');
        const body = document.getElementById(bodyId);
        if (body && !body.innerHTML.trim()) body.innerHTML = renderRaceBody(id);
        setTimeout(function () {
          card.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 120);
      }
    }, 150);
  }
  function renderRacePicker() {
    const map = getRaceByDateMap();
    const dates = Object.keys(map).sort().reverse();
    const today = todayStr();
    const title = $('rpTitle');
    const back = $('rpBackBtn');
    const body = $('rpBody');
    if (!racePickerDate) {
      title.textContent = '選擇日期';
      back.style.display = 'none';
      body.innerHTML = '<div class="rp-date-grid">' + dates.map(function (d) {
        const ids = map[d];
        const first = DB.races[ids[0]].race_info;
        const venue = first.venue === 'HV' ? '跑馬地' : '沙田';
        const finishedN = ids.filter(function (id) { return DB.races[id].race_info.result_available; }).length;
        const pendingN = ids.length - finishedN;
        const isToday = d === today;
        const statusBadge = pendingN > 0
          ? '<span class="badge">⏳ ' + pendingN + ' 場待賽</span>'
          : '<span class="badge" style="background:rgba(59,130,246,0.15);color:#93c5fd;">✓ ' + finishedN + ' 場已完賽</span>';
        return '<div class="rp-date-card ' + (isToday ? 'today' : '') + '" onclick="selectRaceDate(\'' + d + '\')">' +
          '<div class="left"><div class="d">' + d + (isToday ? '  <span style="color:var(--gold);">· 今日</span>' : '') + '</div>' +
          '<div class="sub">' + venue + ' · ' + ids.length + ' 場 · 第 ' + (DB.races[ids[0]].race_info.race_number || 1) + '-' + (DB.races[ids[ids.length-1]].race_info.race_number || ids.length) + ' 場</div></div>' +
          statusBadge + '</div>';
      }).join('') + '</div>';
    } else {
      const ids = map[racePickerDate] || [];
      const venue = ids.length ? (DB.races[ids[0]].race_info.venue === 'HV' ? '跑馬地' : '沙田') : '';
      title.textContent = racePickerDate + ' · ' + venue;
      back.style.display = 'inline-flex';
      body.innerHTML = '<div class="rp-race-grid">' + ids.map(function (id) {
        const info = DB.races[id].race_info;
        const done = info.result_available;
        const selected = DB.currentRaceId === id;
        const sub = (info.class || '') + ' · ' + (info.distance_m || '') + 'm' + (info.track ? ' · ' + info.track : '');
        const t = info.post_time || '--:--';
        return '<div class="rp-race-card ' + (done ? 'done' : '') + ' ' + (selected ? 'selected' : '') + '" onclick="selectRaceId(\'' + id + '\')">' +
          '<div class="left"><div class="r">第 ' + (info.race_number || '?') + ' 場 ' + (info.class || '') + '</div>' +
          '<div class="sub">' + sub + ' · ' + ((DB.races[id].horses && DB.races[id].horses.length) || info.num_horses || 0) + ' 匹</div></div>' +
          '<div class="time">' + t + '</div></div>';
      }).join('') + '</div>';
    }
  }
  window.openRacePicker = openRacePicker;
  window.closeRacePicker = closeRacePicker;
  window.racePickerBack = racePickerBack;
  window.selectRaceDate = selectRaceDate;
  window.selectRaceId = selectRaceId;

  /* ========== 底部導航 Tab 切換 ========== */
  function initNav() {
    const navItems = document.querySelectorAll('.bottom-nav .nav-item');
    navItems.forEach(function (t) {
      t.addEventListener('click', function () {
        navItems.forEach(function (x) { x.classList.remove('active'); });
        t.classList.add('active');
        const key = t.dataset.tab;
        document.querySelectorAll('.tab-panel').forEach(function (p) {
          p.classList.toggle('active', p.dataset.panel === key);
        });
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    });

    const subTabs = document.querySelectorAll('#raceSubTabs .sub-tab');
    subTabs.forEach(function (t) {
      t.addEventListener('click', function () {
        subTabs.forEach(function (x) { x.classList.remove('active'); });
        t.classList.add('active');
        DB.raceFilter = t.dataset.racefilter || 'all';
        try { renderRaceCards(); } catch (e) { console.error(e); }
      });
    });
  }

                                                                                                                                                                      const RACE_FILES = [
    'HV-20260610-01_race1_1800m_cls5.json',
    'HV-20260610-02_race2_1650m_cls4.json',
    'HV-20260610-03_race3_1200m_cls4.json',
    'HV-20260610-04_race4_1000m_cls4.json',
    'HV-20260610-05_race5_1650m_cls4.json',
    'HV-20260610-06_race6_1200m_cls4.json',
    'HV-20260610-07_race7_1800m_cls3.json',
    'HV-20260610-08_race8_1200m_cls3.json',
    'HV-20260610-09_race9_1200m_cls3.json',
    'HV-20260624-01_race1_2200m_cls5.json',
    'HV-20260624-02_race2_1650m_cls5.json',
    'HV-20260624-03_race3_1650m_cls4.json',
    'HV-20260624-04_race4_1650m_cls4.json',
    'HV-20260624-05_race5_1200m_cls4.json',
    'HV-20260624-06_race6_1200m_cls4.json',
    'HV-20260624-07_race7_1000m_cls3.json',
    'HV-20260624-08_race8_1200m_cls3.json',
    'HV-20260624-09_race9_1650m_cls3.json',
    'HV-20260708-01_race1_1000m_cls5.json',
    'HV-20260708-02_race2_1650m_cls4.json',
    'HV-20260708-03_race3_1000m_cls4.json',
    'HV-20260708-04_race4_1650m_cls4.json',
    'HV-20260708-05_race5_1200m_cls4.json',
    'HV-20260708-06_race6_1200m_cls4.json',
    'HV-20260708-07_race7_1000m_cls3.json',
    'HV-20260708-08_race8_1800m_cls2.json',
    'HV-20260708-09_race9_1200m_cls3.json',
    'HV-20260715-01_race1_1650m_cls5.json',
    'HV-20260715-02_race2_1200m_cls4.json',
    'HV-20260715-03_race3_1800m_cls4.json',
    'HV-20260715-04_race4_1650m_cls4.json',
    'HV-20260715-05_race5_1200m_cls4.json',
    'HV-20260715-06_race6_1200m_cls4.json',
    'HV-20260715-07_race7_1650m_cls3.json',
    'HV-20260715-08_race8_1200m_cls2.json',
    'HV-20260715-09_race9_1200m_cls3.json',
    'HV-20260909-01_race1_1200m_cls5.json',
    'HV-20260909-02_race2_1650m_cls4.json',
    'HV-20260909-03_race3_1200m_cls5.json',
    'HV-20260909-04_race4_1650m_cls4.json',
    'HV-20260909-05_race5_1650m_cls3.json',
    'HV-20260909-06_race6_1000m_cls4.json',
    'HV-20260909-07_race7_1200m_cls4.json',
    'HV-20260909-08_race8_1200m_cls3.json',
    'HV-20260916-01_race1_1000m_cls5.json',
    'HV-20260916-02_race2_1200m_cls4.json',
    'HV-20260916-03_race3_1800m_cls4.json',
    'HV-20260916-04_race4_1200m_cls4.json',
    'HV-20260916-05_race5_1200m_cls4.json',
    'HV-20260916-06_race6_1650m_cls3.json',
    'HV-20260916-07_race7_1000m_cls3.json',
    'HV-20260916-08_race8_1650m_cls2.json',
    'HV-20260923-01_race1_1650m_cls5.json',
    'HV-20260923-02_race2_1200m_cls4.json',
    'HV-20260923-03_race3_1650m_cls4.json',
    'HV-20260923-04_race4_1200m_cls4.json',
    'HV-20260923-05_race5_1650m_cls4.json',
    'HV-20260923-06_race6_1000m_cls4.json',
    'HV-20260923-07_race7_1200m_cls3.json',
    'HV-20260923-08_race8_1200m_cls3.json',
    'HV-20260923-09_race9_1800m_cls3.json',
    'ST-20260613-01_race1_1400m_cls5.json',
    'ST-20260613-02_race2_1200m_cls5.json',
    'ST-20260613-03_race3_1400m_cls4.json',
    'ST-20260613-04_race4_1800m_cls4.json',
    'ST-20260613-05_race5_1200m_cls4.json',
    'ST-20260613-06_race6_1400m_cls4.json',
    'ST-20260613-07_race7_1200m_cls4.json',
    'ST-20260613-08_race8_1600m_cls2.json',
    'ST-20260613-09_race9_1200m_cls3.json',
    'ST-20260613-10_race10_1600m_cls3.json',
    'ST-20260613-11_race11_1400m_cls3.json',
    'ST-20260621-01_race1_1000m_cls4.json',
    'ST-20260621-02_race2_1400m_cls5.json',
    'ST-20260621-03_race3_1200m_cls4.json',
    'ST-20260621-04_race4_1200m_cls4.json',
    'ST-20260621-05_race5_1600m_cls4.json',
    'ST-20260621-06_race6_1400m_cls4.json',
    'ST-20260621-07_race7_1400m_cls5.json',
    'ST-20260621-08_race8_2000m_cls3.json',
    'ST-20260621-09_race9_1400m_cls5.json',
    'ST-20260621-10_race10_1200m_cls3.json',
    'ST-20260621-11_race11_1400m_cls3.json',
    'ST-20260627-01_race1_1200m_cls5.json',
    'ST-20260627-02_race2_1200m_cls5.json',
    'ST-20260627-03_race3_1200m_cls4.json',
    'ST-20260627-04_race4_2000m_cls4.json',
    'ST-20260627-05_race5_1650m_cls4.json',
    'ST-20260627-06_race6_1200m_cls4.json',
    'ST-20260627-07_race7_1400m_cls4.json',
    'ST-20260627-08_race8_1000m_cls1.json',
    'ST-20260627-09_race9_1650m_cls3.json',
    'ST-20260627-10_race10_1200m_cls3.json',
    'ST-20260627-11_race11_1400m_cls3.json',
    'ST-20260701-01_race1_1600m_cls5.json',
    'ST-20260701-02_race2_1400m_cls5.json',
    'ST-20260701-03_race3_1400m_cls4.json',
    'ST-20260701-04_race4_1000m_cls4.json',
    'ST-20260701-05_race5_1400m_cls2.json',
    'ST-20260701-06_race6_1200m_cls4.json',
    'ST-20260701-07_race7_1000m_cls3.json',
    'ST-20260701-08_race8_1400m_cls4.json',
    'ST-20260701-09_race9_1600m_cls4.json',
    'ST-20260701-10_race10_1600m_cls3.json',
    'ST-20260701-11_race11_1200m_cls3.json',
    'ST-20260712-01_race1_1800m_cls5.json',
    'ST-20260712-02_race2_1400m_cls5.json',
    'ST-20260712-03_race3_1400m_cls4.json',
    'ST-20260712-04_race4_1400m_cls4.json',
    'ST-20260712-05_race5_1200m_cls4.json',
    'ST-20260712-06_race6_1200m_cls4.json',
    'ST-20260712-07_race7_1600m_cls4.json',
    'ST-20260712-08_race8_1600m_cls1.json',
    'ST-20260712-09_race9_1200m_cls3.json',
    'ST-20260712-10_race10_1600m_cls3.json',
    'ST-20260712-11_race11_1400m_cls3.json',
    'ST-20260906-01_race1_1200m_cls5.json',
    'ST-20260906-02_race2_1000m_cls4.json',
    'ST-20260906-03_race3_1200m_cls3.json',
    'ST-20260906-04_race4_1600m_cls5.json',
    'ST-20260906-05_race5_1200m_cls4.json',
    'ST-20260906-06_race6_1200m_cls4.json',
    'ST-20260906-07_race7_1400m_cls2.json',
    'ST-20260906-08_race8_1400m_cls4.json',
    'ST-20260906-09_race9_1400m_cls3.json',
    'ST-20260906-10_race10_1200m_cls3.json',
    'ST-20260913-01_race1_1400m_cls5.json',
    'ST-20260913-02_race2_1000m_cls4.json',
    'ST-20260913-03_race3_1400m_cls5.json',
    'ST-20260913-04_race4_1200m_cls4.json',
    'ST-20260913-05_race5_1200m_cls4.json',
    'ST-20260913-06_race6_1600m_cls4.json',
    'ST-20260913-07_race7_1400m_cls4.json',
    'ST-20260913-08_race8_1000m_cls3.json'
  ];

  async function loadAll(opts) {
    opts = opts || {};
    DB.races = {}; DB.raceIndex = [];
    const seen = {};
    let raceFiles = RACE_FILES.slice();
    let listSource = 'hardcoded';
    try {
      let list = await api('/api/list.json');
      if (!list || !list.race_files || !list.race_files.length) {
        list = await api('/data/list.json');
      }
      if (list && list.race_files && list.race_files.length) {
        raceFiles = list.race_files.slice();
        listSource = 'list.json (' + raceFiles.length + ')';
      }
    } catch (e) { console.warn('list.json load failed, fallback to hardcoded', e); }

    const racePool = [
      { files: raceFiles, label: listSource }
    ];
    if (listSource !== 'hardcoded') {
      racePool.push({ files: RACE_FILES.slice(), label: 'hardcoded-fallback' });
    }
    let ok = 0, miss = 0;
    for (let p = 0; p < racePool.length; p++) {
      const files = racePool[p].files;
      for (let i = 0; i < files.length; i++) {
        const f = files[i];
        let r = null;
        try {
          r = await api('/data/history/' + f);
          if (!r || !r.race_info) {
            const r2 = await api('/api/history/' + f);
            if (r2 && r2.race_info) r = r2;
          }
        } catch (e) { r = null; }
        if (!r || !r.race_info) { miss++; continue; }
        try {
          const id = r.race_info.race_id;
          if (seen[id]) continue;
          seen[id] = true;
          if (!r.horses && r.entries) r.horses = r.entries.slice();
          if (r.horses && r.horses.length && !r.horses[0].odds) {
            r.horses.forEach(function (h) {
              if (!h.odds) h.odds = { win: h.win_odds || 0, place: h.place_odds || 0 };
            });
          }
          if (r.horses && r.horses.length) {
            r.horses.forEach(function (h) {
              if (typeof h.win_odds === 'number' && !(typeof h.odds_win === 'number' && h.odds_win > 0)) h.odds_win = h.win_odds;
              if (typeof h.place_odds === 'number' && !(typeof h.odds_place === 'number' && h.odds_place > 0)) h.odds_place = h.place_odds;
              var hasL3 = Array.isArray(h.last_3) && h.last_3.length === 3;
              var noL6 = !h.last_6 || typeof h.last_6 !== 'string';
              if (!hasL3 && !noL6) {
                var m = h.last_6.match(/^(\d{1,2})\/(\d{1,2})\/(\d{1,2})\/(\d{1,2})\/(\d{1,2})\/(\d{1,2})$/);
                if (m) {
                  h.last_3 = [Math.max(1, Math.min(14, parseInt(m[1], 10) || 14)),
                              Math.max(1, Math.min(14, parseInt(m[2], 10) || 14)),
                              Math.max(1, Math.min(14, parseInt(m[3], 10) || 14))];
                } else {
                  var parts = h.last_6.split('/').map(function (p) { return parseInt(p, 10); }).filter(function (v) { return Number.isFinite(v) && v >= 1 && v <= 20; });
                  if (parts.length >= 3) {
                    h.last_3 = parts.slice(0, 3).map(function (v) { return Math.max(1, Math.min(14, v)); });
                  }
                }
              }
              const bt = h.best_time_sec;
              if (typeof bt !== 'number' || !isFinite(bt) || bt <= 0 || bt > 900) {
                h.best_time_sec = 999;
              }
              const ow = h.odds_win;
              if (typeof ow !== 'number' || !isFinite(ow) || ow <= 0 || ow >= 999) {
                h.odds_win = 999;
              }
              const op = h.odds_place;
              if (typeof op !== 'number' || !isFinite(op) || op <= 0 || op >= 999) {
                h.odds_place = 999;
              }
              ['draw', 'rating', 'weight', 'number'].forEach(function (k) {
                if (typeof h[k] !== 'number' || !isFinite(h[k])) {
                  h[k] = parseInt(h[k], 10) || 0;
                }
              });
              if (!Array.isArray(h.last_3)) h.last_3 = [];
            });
            if (r.entries && r.entries.length === r.horses.length) {
              r.horses.forEach(function (h, i) {
                if (r.entries[i]) {
                  r.entries[i].last_3 = h.last_3;
                  r.entries[i].best_time_sec = h.best_time_sec;
                  r.entries[i].odds_win = h.odds_win;
                  r.entries[i].odds_place = h.odds_place;
                }
              });
            } else {
              r.entries = r.horses.map(function (h) { return Object.assign({}, h); });
            }
          }
          DB.races[id] = r;
          DB.raceIndex.push(id);
          ok++;
        } catch (e) {
          console.warn('Race parse failed:', f, e);
          miss++;
        }
      }
      if (Object.keys(DB.races).length >= 20) break;
    }
    console.info('[loadAll] loaded=' + Object.keys(DB.races).length + ' ok=' + ok + ' miss=' + miss + ' source=' + listSource);
    DB.raceIndex.sort(function (a, b) {
      const da = (DB.races[a].race_info || {}).race_date || '';
      const db = (DB.races[b].race_info || {}).race_date || '';
      return da.localeCompare(db);
    });

    let horsesDB = await api('/data/profiles/horses_db.json') || await api('/api/profiles/horses');
    if (horsesDB && horsesDB.horses) {
      DB.horsesDB = horsesDB.horses;
      DB.raceIndex.forEach(function (rid) {
        const r = DB.races[rid];
        if (!r || !r.horses) return;
        r.horses.forEach(function (h) {
          if (!h.code) return;
          const pr = DB.horsesDB[h.code];
          if (!pr) return;
          if ((!h.best_time_sec || h.best_time_sec >= 999) && typeof pr.best_time === 'number' && pr.best_time > 0 && pr.best_time < 900) {
            h.best_time_sec = pr.best_time;
            if (r.entries && r.entries.length === r.horses.length) {
              const idx = r.horses.indexOf(h);
              if (idx >= 0 && r.entries[idx]) r.entries[idx].best_time_sec = pr.best_time;
            }
          }
          if (!h.name && pr.name) h.name = pr.name;
        });
      });
    }
    let jocks = await api('/data/stats/jockeys_db.json') || await api('/api/stats/jockeys');
    if (jocks && jocks.jockeys) DB.jockeysDB = jocks.jockeys;
    let trains = await api('/data/stats/trainers_db.json') || await api('/api/stats/trainers');
    if (trains && trains.trainers) DB.trainersDB = trains.trainers;

    buildAugmentedDatabases();
    computeHistoryStats();

    if (!DB.currentRaceId) {
      const pendingFirst = DB.raceIndex.find(function (id) { return !DB.races[id].race_info.result_available; });
      DB.currentRaceId = pendingFirst || DB.raceIndex[DB.raceIndex.length - 1];
    }

    try { renderDashboard(); } catch (e) { console.error(e); }
    try { renderRaceCards(); } catch (e) { console.error(e); }
    try { renderHistoryTable(); } catch (e) { console.error(e); }
    try { renderJockeysTable(); } catch (e) { console.error(e); }
    try { renderTrainersTable(); } catch (e) { console.error(e); }
    try { renderHorsesTable(); } catch (e) { console.error(e); }

    if ($('statsCount')) {
      $('statsCount').textContent = DB.raceIndex.length + ' 場';
    }
  }

  function buildAugmentedDatabases() {
    const jh = {};
    const hd = {};
    const cls = {};
    DB.raceIndex.forEach(function (id) {
      const d = DB.races[id];
      const info = d.race_info || {};
      if (!d.horses || !info.result_available) return;
      const venue = info.venue || '';
      const dist = info.distance_m || 0;
      const clsName = info.class || '';
      d.horses.forEach(function (h) {
        const code = h.code || '';
        if (!code) return;
        const fin = typeof h.finish === 'number' ? h.finish : 99;
        const jockey = h.jockey || '';
        if (jockey) {
          const key = jockey + '|' + code;
          if (!jh[key]) jh[key] = { rides: 0, wins: 0, places: 0, avgRank: 0, bestRank: 99, recentBest: 99 };
          const s = jh[key];
          s.rides++;
          if (fin <= 3) s.places++;
          if (fin === 1) s.wins++;
          s.avgRank = s.avgRank + fin;
          if (fin < s.bestRank) s.bestRank = fin;
          if (fin < s.recentBest) s.recentBest = fin;
        }
        if (dist > 0) {
          const dk = code + '|' + dist;
          if (!hd[dk]) hd[dk] = { starts: 0, wins: 0, places: 0, bestTime: 9999, venueMatches: 0, venue: venue };
          const sd = hd[dk];
          sd.starts++;
          if (fin <= 3) sd.places++;
          if (fin === 1) sd.wins++;
          const bt = typeof h.best_time_sec === 'number' ? h.best_time_sec : 9999;
          if (bt < sd.bestTime) sd.bestTime = bt;
          if (!sd.venue) sd.venue = venue;
          if (venue && sd.venue && sd.venue === venue) sd.venueMatches++;
        }
        if (clsName) {
          const ck = code + '|' + clsName;
          if (!cls[ck]) cls[ck] = { starts: 0, wins: 0, places: 0, bestFinish: 99, avgFinish: 0 };
          const sc = cls[ck];
          sc.starts++;
          if (fin <= 3) sc.places++;
          if (fin === 1) sc.wins++;
          if (fin < sc.bestFinish) sc.bestFinish = fin;
          sc.avgFinish = sc.avgFinish + fin;
        }
      });
    });
    Object.keys(jh).forEach(function (k) {
      const s = jh[k];
      s.win_rate = s.rides ? s.wins / s.rides : 0;
      s.place_rate = s.rides ? s.places / s.rides : 0;
      s.avg_rank = s.rides ? s.avgRank / s.rides : 99;
    });
    Object.keys(hd).forEach(function (k) {
      const s = hd[k];
      s.win_rate = s.starts ? s.wins / s.starts : 0;
      s.place_rate = s.starts ? s.places / s.starts : 0;
    });
    Object.keys(cls).forEach(function (k) {
      const s = cls[k];
      s.win_rate = s.starts ? s.wins / s.starts : 0;
      s.place_rate = s.starts ? s.places / s.starts : 0;
      s.avg_finish = s.starts ? s.avgFinish / s.starts : 99;
    });
    DB.jockeyHorseStats = jh;
    DB.horseDistanceStats = hd;
    DB.classStats = cls;
    DB.trackwork = {};
    const pendingIds = DB.raceIndex.filter(function (id) { return !(DB.races[id].race_info || {}).result_available; });
    const candidates = ['2026-09-23_HV', '2026-09-21_ST', '2026-09-20_HV', '2026-09-20_ST'];
    pendingIds.forEach(function (id) {
      DB.trackwork[id] = { loaded: false, records: [] };
    });
    const twFiles = candidates.slice();
    let twIndex = 0;
    function tryNext() {
      if (twIndex >= twFiles.length) return;
      const name = twFiles[twIndex] + '.json';
      twIndex++;
      const p1 = '/api/trackwork/' + name;
      const p2 = '/data/trackwork/' + name;
      fetch(p1, { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
        if (!j) return fetch(p2, { cache: 'no-store' }).then(function (r2) { return r2.ok ? r2.json() : null; });
        return j;
      }).then(function (j) {
        if (j && j.trackwork_records) {
          const recs = {};
          j.trackwork_records.forEach(function (r) {
            const c = r.code || '';
            if (!c) return;
            if (!recs[c]) recs[c] = [];
            recs[c].push(r);
          });
          pendingIds.forEach(function (id) { DB.trackwork[id] = { loaded: true, records: recs }; });
        }
        tryNext();
      }).catch(function () { tryNext(); });
    }
    tryNext();
  }

  function codeToHorseLabel(code, horses) {
    if (!code) return '—';
    if (!horses || !horses.length) return String(code);
    const h = horses.find(function (x) { return x && x.code === code; });
    if (!h) return String(code);
    const n = h.horse_number || h.number || '';
    const nm = h.name || h.horse_name || String(code);
    return (n ? '#' + n + ' ' : '') + nm;
  }

  function computeHistoryStats() {
    const finished = [];
    DB.raceIndex.forEach(function (id) {
      const d = DB.races[id];
      const info = d.race_info;
      if (info.result_available && (info.official_result || []).length) {
        const analysis = RacingAI.runFullAnalysis(d);
        const realWinnerCode = (info.official_result.find(function (r) { return r.finish === 1; }) || {}).code || '';
        const realTop3 = info.official_result.slice(0, 3).map(function (r) { return r.code; });
        const aiTop1Code = (analysis.top4_predictions[0] && analysis.top4_predictions[0].horse && analysis.top4_predictions[0].horse.code) || '';
        const aiTop4 = analysis.top4_predictions.slice(0, 4).map(function (p) { return (p.horse || {}).code || ''; });
        const hitTop1 = !!realWinnerCode && aiTop1Code === realWinnerCode;
        const top4InQ = aiTop4.filter(function (c) { return realTop3.indexOf(c) >= 0; }).length;
        let winOdds = 0, qOdds = 0;
        const horses = d.horses;
        if (hitTop1) {
          const hw = horses.find(function (h) { return h.code === realWinnerCode; });
          if (hw) winOdds = hw.odds_win;
        }
        if (aiTop4[0] && aiTop4[1]) {
          const s1 = realTop3.indexOf(aiTop4[0]);
          const s2 = realTop3.indexOf(aiTop4[1]);
          if (s1 >= 0 && s2 >= 0) {
            const h1 = horses.find(function (h) { return h.code === aiTop4[0]; });
            const h2 = horses.find(function (h) { return h.code === aiTop4[1]; });
            if (h1 && h2) qOdds = Math.round(h1.odds_win * h2.odds_win * 0.85 * 10) / 10;
          }
        }
        const aiTop1Label = aiTop1Code ? codeToHorseLabel(aiTop1Code, horses) : '—';
        const realWinnerLabel = realWinnerCode ? codeToHorseLabel(realWinnerCode, horses) : '<span style="color:var(--text-dim);">⚠️ 未錄入</span>';
        finished.push({
          id: id, info: info, analysis: analysis, realWinner: realWinnerCode, realTop3: realTop3,
          aiTop1: aiTop1Code, aiTop4: aiTop4, hitTop1: hitTop1, top4InQ: top4InQ,
          winOdds: winOdds, qOdds: qOdds,
          aiTop1Label: aiTop1Label, realWinnerLabel: realWinnerLabel
        });
      }
    });
    const n = finished.length;
    const hit1 = finished.filter(function (x) { return x.hitTop1; }).length;
    const avgQ = n ? finished.reduce(function (s, x) { return s + x.top4InQ; }, 0) / n : 0;
    const totalWinRet = finished.reduce(function (s, x) { return s + (x.winOdds ? x.winOdds - 1 : -1); }, 0);
    const totalQRet = finished.reduce(function (s, x) { return s + (x.qOdds ? x.qOdds - 1 : -1); }, 0);
    DB.historyStats = { finished: finished, n: n, hit1: hit1, top1Rate: n ? hit1 / n : 0, avgTop3InTop4: avgQ, totalWinRet: totalWinRet, totalQRet: totalQRet };
  }

  function last3Badge(card) {
    if (!card || !card.length) return '<span style="display:inline-block;padding:2px 8px;border-radius:6px;background:var(--bg-card3);color:var(--gold);font-size:11px;font-weight:700;">新馬</span>';
    function toFinish(r) {
      if (typeof r === 'number') return r || 99;
      if (r && typeof r === 'object' && typeof r.finish === 'number') return r.finish;
      return 99;
    }
    return '<span class="last3">' + card.slice(0, 3).map(function (r) {
      const finish = toFinish(r);
      const cls = (finish <= 3) ? 'good' : (finish <= 6 ? 'mid' : 'bad');
      return '<span class="' + cls + '">' + finish + '</span>';
    }).join('') + '</span>';
  }
  function last6Badge(h) {
    // 完整 6 段近績徽章：左邊=最近 1 仗 (色深權重高)，右邊=最舊第 6 仗 (色淺)。h.last_6 優先，否則 h.last_3[] 放左邊
    var segs = [];
    var srcRaw = (h && typeof h.last_6 === 'string') ? h.last_6 : '';
    if (srcRaw && /^\d{1,2}(\/\d{1,2}){5}$/.test(srcRaw)) {
      segs = srcRaw.split('/').map(function (x) { return parseInt(x, 10) || 14; });
    } else if (h && Array.isArray(h.last_3) && h.last_3.length) {
      // 只有 last_3，pad 右邊 3 格空
      segs = h.last_3.slice(0, 3).map(function (r) { return typeof r === 'number' ? r || 99 : (r && typeof r.finish === 'number' ? r.finish : 99); });
      while (segs.length < 6) segs.push(null);
    }
    if (!segs.length) return '<span style="padding:2px 6px;border-radius:5px;background:var(--bg-card3);color:var(--text-dim);font-size:11px;">--</span>';
    // 每格透明度 alpha 左 1.0 → 右 0.48 (最近最重視)
    function clsFor(f, idx) {
      if (f === null || f === undefined || f >= 99) return 'background:var(--bg-card3);color:var(--text-dim);';
      var base = (f <= 3) ? '#22c55e' : (f <= 6 ? '#eab308' : (f <= 10 ? '#f97316' : '#ef4444'));
      var textC = (f <= 10) ? '#0a0a0a' : '#fff7e0';
      var alpha = Math.max(0.42, 1.0 - idx * 0.11);
      return 'background:' + base + ';opacity:' + alpha.toFixed(2) + ';color:' + textC + ';font-weight:' + (idx === 0 ? '900' : (idx <= 2 ? '800' : '700')) + ';';
    }
    function lbl(f) {
      if (f === null || f === undefined || f >= 99) return '·';
      return '' + f;
    }
    return '<span class="last6" title="近績 6 仗：左邊=最近，右邊=最舊 (HKJC 排位慣例)">' +
      segs.slice(0, 6).map(function (f, i) {
        return '<span style="display:inline-block;min-width:20px;text-align:center;padding:1px 4px;margin:0 1px;border-radius:4px;font-size:11px;border:1px solid rgba(255,255,255,0.05);' + clsFor(f, i) + '">' + lbl(f) + '</span>';
      }).join('') + '</span>';
  }
  function ccExpertBadge(h, small) {
    if (!h || typeof h.cc_expert_count !== 'number' || h.cc_expert_count < 3) return '';
    const pad = small ? 'padding:1px 5px;font-size:10px;' : 'padding:1px 6px;font-size:11px;';
    return '<span style="display:inline-block;' + pad + 'border-radius:5px;background:linear-gradient(135deg,#7a1e1e,#c45828);color:#fff7e0;font-weight:800;margin-left:4px;vertical-align:middle;white-space:nowrap;">🔥' + h.cc_expert_count + '名家</span>';
  }

  function renderDashboard() {
    const S = DB.historyStats || { n: 0, hit1: 0, avgTop3InTop4: 0, totalWinRet: 0, totalQRet: 0 };
    const races = DB.raceIndex.map(function (id) { return DB.races[id]; });
    const finished = races.filter(function (r) { return r.race_info.result_available; });
    const pending = races.filter(function (r) { return !r.race_info.result_available; });
    const totalHorses = Object.keys(DB.horsesDB).length;
    const allEntries = races.reduce(function (s, r) { return s + ((r.horses && r.horses.length) || 0); }, 0);

    const sc = $('statCards');
    if (sc) {
      sc.innerHTML = [
        '<div class="stat-card"><div class="label">總賽事</div><div class="value">' + races.length + '</div><div class="delta">已完賽 ' + finished.length + ' / 待賽 ' + pending.length + '</div></div>',
        '<div class="stat-card"><div class="label">馬匹出戰</div><div class="value">' + allEntries + '</div><div class="delta">檔案馬 ' + totalHorses + ' 匹</div></div>',
        '<div class="stat-card"><div class="label">頭馬命中率</div><div class="value">' + Math.round(S.top1Rate * 100) + '%</div><div class="delta">' + S.hit1 + '/' + S.n + ' 命中</div></div>',
        '<div class="stat-card"><div class="label">頭4入Q</div><div class="value">' + S.avgTop3InTop4.toFixed(2) + '</div><div class="delta">場均三甲入頭4</div></div>'
      ].join('');
    }

    const acc = $('accuracyCard');
    if (acc) {
      acc.innerHTML =
        '<h4>🎯 AI 模型歷史表現（' + S.n + ' 場已完賽）</h4>' +
        '<div class="accuracy-grid">' +
        '<div class="accuracy-item"><div class="label">頭馬命中率</div><div class="value">' + Math.round(S.top1Rate * 100) + '%</div></div>' +
        '<div class="accuracy-item"><div class="label">三甲入頭4</div><div class="value">' + Math.round(S.avgTop3InTop4 / 3 * 100) + '%</div></div>' +
        '<div class="accuracy-item"><div class="label">場均Q佔中</div><div class="value">' + S.avgTop3InTop4.toFixed(2) + '</div></div>' +
        '<div class="accuracy-item"><div class="label">Q ROI</div><div class="value" style="color:' + (S.totalQRet >= 0 ? 'var(--green)' : 'var(--red)') + ';">' + (S.totalQRet >= 0 ? '正' : '負') + '回報</div></div>' +
        '</div>';
    }

    const at = document.querySelector('#accuracyTable tbody');
    const sel = $('accuracyDateSelect');
    if (at && sel) {
      const byDate = {};
      (S.finished || []).forEach(function (x) {
        const k = (x.info && x.info.race_date) || 'unknown';
        if (!byDate[k]) byDate[k] = [];
        byDate[k].push(x);
      });
      const dateKeys = Object.keys(byDate).sort().reverse();
      let defaultKey = dateKeys[0];
      if (defaultKey && defaultKey === todayStr()) defaultKey = dateKeys[1] || defaultKey;
      DB._accuracyByDate = byDate;
      sel.innerHTML = dateKeys.map(function (k) {
        const items = byDate[k] || [];
        const n = items.length;
        const hitN = items.filter(function (x) { return x.hitTop1; }).length;
        const venue = (items[0] && items[0].info && items[0].info.venue === 'HV') ? '跑馬地' : '沙田';
        const label = k + ' ' + venue + ' · ' + n + '場 · 命中' + hitN + '場' + (k === defaultKey ? '（預設）' : '');
        return '<option value="' + k + '"' + (k === defaultKey ? ' selected' : '') + '>' + label + '</option>';
      }).join('');
      window.changeAccuracyDate = function (k) {
        const list = DB._accuracyByDate && DB._accuracyByDate[k] ? DB._accuracyByDate[k].slice().reverse() : [];
        at.innerHTML = list.map(function (x) {
          const info = x.info;
          return '<tr>' +
            '<td><b>' + (info.race_date || '').slice(5) + ' R' + info.race_number + '</b></td>' +
            '<td>' + info.venue + '</td>' +
            '<td>' + info.distance_m + 'm</td>' +
            '<td>' + (x.aiTop1Label || '—') + '</td>' +
            '<td>' + (x.realWinnerLabel || '<span style="color:var(--text-dim);">⚠️ 未錄入</span>') + '</td>' +
            '<td>' + (x.hitTop1 ? '<span style="color:var(--green);font-weight:700;">✓</span>' : '<span style="color:var(--text-dim);">✗</span>') + '</td>' +
            '<td>' + x.top4InQ + '/3</td>' +
            '</tr>';
        }).join('') || '<tr><td colspan="7" style="color:var(--text-dim);text-align:center;padding:20px;">暫無該賽馬日紀錄</td></tr>';
      };
      changeAccuracyDate(defaultKey);
    }

    const sl = $('scheduleList');
    if (sl) {
      const byDate = {};
      DB.raceIndex.forEach(function (id) {
        const d = DB.races[id].race_info;
        const k = d.race_date;
        if (!byDate[k]) byDate[k] = [];
        byDate[k].push(id);
      });
      const dates = Object.keys(byDate).sort().reverse();
      const today = todayStr();
      // 今日日期優先（搵今日 或 最新 pending 嗰日）
      let todayKey = dates.find(function (d) { return d === today; }) || null;
      if (!todayKey) {
        todayKey = dates.find(function (d) {
          return byDate[d].some(function (id) { return !DB.races[id].race_info.result_available; });
        }) || dates[0];
      }
      const todayIds = byDate[todayKey] || [];
      const tInfo = DB.races[todayIds[0]].race_info;
      const finishedN = todayIds.filter(function (id) { return DB.races[id].race_info.result_available; }).length;
      const venue = tInfo.venue === 'HV' ? '跑馬地' : '沙田';
      const pickBtn = '<div class="schedule-item" style="background:linear-gradient(135deg,rgba(212,175,55,0.14),rgba(212,175,55,0.04));border:1px solid rgba(212,175,55,0.4);cursor:pointer;" onclick="openRacePicker()">' +
        '<div><div class="date" style="color:var(--gold);">📅 選擇其他賽事日期</div>' +
        '<div class="count">總共 ' + dates.length + ' 個賽馬日 · ' + DB.raceIndex.length + ' 場賽事</div></div>' +
        '<div style="color:var(--gold);font-size:18px;">›</div></div>';
      const todayCard = '<div class="schedule-item">' +
        '<div><div class="date">' + todayKey + ' ' + venue + (todayKey === today ? ' · 今日' : '') + '</div>' +
        '<div class="count">' + todayIds.length + ' 場 · 已完賽 ' + finishedN + ' / 待賽 ' + (todayIds.length - finishedN) + '</div></div>' +
        '<button class="btn primary" style="padding:6px 12px;font-size:12px;" onclick="selectRaceDate(\'' + todayKey + '\');openRacePicker();">選擇場次 ›</button>' +
        '</div>';
      sl.innerHTML = todayCard + pickBtn;
    }

    const distStat = {}, classStat = {};
    races.forEach(function (d) {
      const info = d.race_info;
      const k = info.distance_m + 'm';
      distStat[k] = (distStat[k] || 0) + 1;
      classStat[info.class] = (classStat[info.class] || 0) + 1;
    });
    const renderStat = function (obj) {
      return Object.entries(obj).map(function (kv) {
        const k = kv[0], v = kv[1];
        const w = Math.min(100, v / 10 * 100);
        return '<div style="margin-bottom:8px;">' +
          '<div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px;"><span>' + k + '</span><b style="color:var(--gold);">' + v + ' 場</b></div>' +
          '<div style="background:var(--bg-card3);height:6px;border-radius:999px;overflow:hidden;"><div style="height:100%;width:' + w + '%;background:linear-gradient(90deg,var(--gold-dark),var(--gold));"></div></div>' +
          '</div>';
      }).join('');
    };
    const dc = $('distClassStats');
    if (dc) {
      dc.innerHTML =
        '<h4 style="margin-bottom:10px;color:var(--gold);font-size:13px;">📏 路程分佈</h4>' + renderStat(distStat) +
        '<h4 style="margin:16px 0 10px;color:var(--gold);font-size:13px;">🏷️ 班次分佈</h4>' + renderStat(classStat);
    }

    const todayAI = $('todayAI');
    if (todayAI) {
      function _fmtOddsUI(o) { if (o == null || typeof o !== 'number' || !isFinite(o) || o >= 999 || o <= 0) return '--'; return (Math.round(o * 10) / 10).toFixed(1) + 'x'; }
      let pendingKey = null;
      let pendingIds = [];
      const byDate2 = {};
      DB.raceIndex.forEach(function (id) {
        const d = DB.races[id].race_info;
        const k = d.race_date;
        if (!byDate2[k]) byDate2[k] = [];
        byDate2[k].push(id);
      });
      const sortedK = Object.keys(byDate2).sort().reverse();
      for (let i = 0; i < sortedK.length; i++) {
        const k = sortedK[i];
        const has = byDate2[k].some(function (id) { return !DB.races[id].race_info.result_available; });
        if (has) { pendingKey = k; pendingIds = byDate2[k].slice(); break; }
      }
      pendingIds.sort(function (a, b) {
        return (DB.races[a].race_info.race_number || 0) - (DB.races[b].race_info.race_number || 0);
      });
      if (!pendingKey) {
        todayAI.innerHTML = '';
      } else {
        DB._analysisCache = DB._analysisCache || {};
        DB._scoredHorses = DB._scoredHorses || {};
        pendingIds.forEach(function (id) {
          if (DB._analysisCache[id]) return;
          try {
            if (window.RacingAI) {
              const ana = computeAdvancedScore(DB.races[id]);
              DB._analysisCache[id] = ana;
              DB._scoredHorses[id] = ana.all_ranked_horses;
            }
          } catch (e) { console.warn('todayAI err', id, e); }
        });
        const venue = (DB.races[pendingIds[0]].race_info.venue === 'HV') ? '跑馬地' : '沙田';
        const headerHtml = '<div class="card">' +
          '<div class="card-title"><h3><span class="emoji">🎯</span>黎緊賽馬日 AI 分析 · ' + pendingKey + ' ' + venue + '</h3></div>' +
          '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;padding:0 4px 16px;">' +
          '<div class="stat-card" style="padding:10px 12px;margin:0;"><div class="label" style="font-size:11px;">賽事數量</div><div class="value" style="font-size:20px;">' + pendingIds.length + '</div><div class="delta" style="font-size:10px;">' + (DB.races[pendingIds[0]].race_info.race_date === todayStr() ? '今日賽日' : '即將到來') + '</div></div>' +
          '<div class="stat-card" style="padding:10px 12px;margin:0;"><div class="label" style="font-size:11px;">出馬匹數</div><div class="value" style="font-size:20px;">' + pendingIds.reduce(function (s, id) { return s + ((DB.races[id].horses && DB.races[id].horses.length) || 0); }, 0) + '</div><div class="delta" style="font-size:10px;">全部賽事</div></div>' +
          '<div class="stat-card" style="padding:10px 12px;margin:0;"><div class="label" style="font-size:11px;">AI 重心場次</div><div class="value" style="font-size:20px;">' + Math.max(1, Math.round(pendingIds.length / 3)) + '</div><div class="delta" style="font-size:10px;">高命中率</div></div>' +
          '<div class="stat-card" style="padding:10px 12px;margin:0;"><div class="label" style="font-size:11px;">Backtest</div><div class="value" style="font-size:20px;color:var(--green);">' + (S.top1Rate ? Math.round(S.top1Rate * 100) : '—') + '%</div><div class="delta" style="font-size:10px;">歷史頭馬命中率</div></div>' +
          '</div>';

        let raceCardsHtml = '<div style="display:flex;flex-direction:column;gap:12px;">';
        let coreHorses = [];
        let qPicksBrief = [];
        pendingIds.forEach(function (id, idx) {
          const info = DB.races[id].race_info;
          const ana = DB._analysisCache[id];
          const top4 = ana && ana.top4_predictions ? ana.top4_predictions : [];
          const betting = ana && ana.betting_strategy ? ana.betting_strategy : {};
          if (top4[0] && top4[0].horse) {
            const h = top4[0].horse;
            if (!coreHorses.find(function (x) { return x.code === h.code; })) coreHorses.push(h);
          }
          if (betting && betting.budgetPlan && betting.budgetPlan.length) {
            betting.budgetPlan.forEach(function (bp) {
              if (bp && bp.type && (bp.type === '連贏 Q 穩健' || bp.type === '連贏 Q 進取')) {
                qPicksBrief.push({ race_no: info.race_number, raceId: id, bp: bp });
              }
            });
          }
          const r4 = top4.slice(0, 4).map(function (p, ri) {
            const h = p && p.horse ? p.horse : null;
            if (!h) return '';
            const scr = h.scores && typeof h.scores.total === 'number' ? h.scores.total.toFixed(1) : '—';
            const ow = _fmtOddsUI(h.odds_win);
            const rankCls = ri === 0 ? 'top1' : (ri === 1 ? 'top2' : (ri === 2 ? 'top3' : 'top4'));
            const adv = (p.core_advantage && p.core_advantage.detail) ? p.core_advantage.detail.slice(0, 24) + (p.core_advantage.detail.length > 24 ? '…' : '') : '';
            return '<div class="horse-click ' + rankCls + '" data-number="' + (h.number || '') + '" data-name="' + (h.name || '') + '" style="cursor:pointer;padding:8px;border-radius:8px;border:1px solid var(--border);background:var(--bg-card2);transition:background .15s,transform .15s;" onclick="event.stopPropagation();DB.currentRaceId=\'' + id + '\';openHorseDetail(\'' + (h.number || h.name || '') + '\');">' +
              '<div style="display:flex;align-items:center;gap:6px;"><span style="display:inline-block;min-width:18px;height:18px;line-height:18px;border-radius:4px;background:linear-gradient(135deg,var(--gold),var(--gold-dark));color:#000;font-weight:900;font-size:10px;text-align:center;">#' + (h.number || '?') + '</span>' +
              '<b style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + (h.name || '') + ccExpertBadge(h, true) + '</b>' +
              '<span style="font-size:10px;color:var(--gold);white-space:nowrap;">' + ow + '</span></div>' +
              '<div style="display:flex;justify-content:space-between;margin-top:4px;"><span style="font-size:10px;color:var(--text-dim);">' + (h.jockey || '') + '/' + (h.trainer || '') + '</span>' +
              '<span style="font-size:10px;color:var(--green);">AI ' + scr + '</span></div>' +
              (adv ? '<div style="font-size:10px;color:var(--gold);margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">💡 ' + adv + '</div>' : '') +
              '</div>';
          }).join('');
          const firstTime = info.post_time ? (info.post_time.slice(0, 5)) : '待公佈';
          const isDone = info.result_available;
          const statusBadge = isDone
            ? '<span style="display:inline-block;padding:2px 8px;border-radius:6px;background:var(--bg-card3);color:var(--text-dim);font-size:11px;">已完賽</span>'
            : '<span style="display:inline-block;padding:2px 8px;border-radius:6px;background:rgba(212,175,55,0.14);color:var(--gold);border:1px solid rgba(212,175,55,0.35);font-size:11px;">⏱ ' + firstTime + '</span>';
          raceCardsHtml += '<div class="card" style="margin:0;padding:12px;border:1px solid var(--border);"><div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">' +
            '<div><b style="font-size:15px;">第 ' + info.race_number + ' 場</b>' +
            '<div style="font-size:11px;color:var(--text-dim);margin-top:2px;">' + (info.class || '') + ' · ' + (info.distance_m || 0) + 'm · ' + ((info.venue === 'HV') ? '跑馬地' : '沙田') + '</div></div>' +
            '<div style="display:flex;gap:6px;align-items:center;">' + statusBadge +
            '<button class="btn secondary" style="padding:4px 10px;font-size:11px;" onclick="selectRaceId(\'' + id + '\');">詳細 ›</button></div></div>' +
            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">' + (r4 || '<div style="grid-column:1/-1;color:var(--text-dim);font-size:12px;padding:10px;text-align:center;">分析中…</div>') + '</div></div>';
        });
        raceCardsHtml += '</div>';

        const coreListHtml = coreHorses && coreHorses.length
          ? '<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px;">' + coreHorses.slice(0, 12).map(function (h) {
              const scr = h.scores && typeof h.scores.total === 'number' ? h.scores.total.toFixed(1) : '—';
              const ow = _fmtOddsUI(h.odds_win);
              const rd = h.draw ? (h.draw + '檔') : '';
              const rid = pendingIds.find(function (pid) {
                return DB.races[pid].horses && DB.races[pid].horses.some(function (hh) { return hh.code === h.code; });
              }) || pendingIds[0];
              return '<div class="horse-click" data-number="' + (h.number || '') + '" data-name="' + (h.name || '') + '" style="cursor:pointer;padding:8px 10px;border-radius:10px;border:1px solid var(--border);background:linear-gradient(135deg,rgba(212,175,55,0.06),transparent);" onclick="event.stopPropagation();DB.currentRaceId=\'' + rid + '\';openHorseDetail(\'' + (h.number || h.name || '') + '\');">' +
                '<div style="display:flex;justify-content:space-between;align-items:center;"><b>#' + (h.number || '') + ' ' + (h.name || '') + ccExpertBadge(h, true) + '</b>' +
                '<span style="color:var(--green);font-weight:800;">' + scr + '</span></div>' +
                '<div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text-dim);margin-top:2px;"><span>' + rd + ' ' + (h.jockey || '') + '</span><span style="color:var(--gold);">' + ow + '</span></div></div>';
            }).join('') + '</div>'
          : '<div style="color:var(--text-dim);font-size:12px;padding:10px;">暫無重心</div>';

        const qBriefHtml = qPicksBrief && qPicksBrief.length
          ? '<div style="display:flex;flex-direction:column;gap:6px;">' + qPicksBrief.slice(0, 6).map(function (q) {
              const bp = q.bp;
              const typeTag = bp.type.includes('穩健')
                ? '<span style="display:inline-block;padding:2px 6px;border-radius:4px;background:var(--bg-card3);color:var(--gold);font-size:10px;">Q穩健</span>'
                : '<span style="display:inline-block;padding:2px 6px;border-radius:4px;background:rgba(80,140,240,0.15);color:#8acfff;font-size:10px;">Q進取</span>';
              return '<div style="padding:8px 10px;border-radius:8px;border:1px solid var(--border);background:var(--bg-card2);display:flex;justify-content:space-between;align-items:center;">' +
                '<div style="display:flex;align-items:center;gap:8px;"><span style="font-weight:900;color:var(--gold);">R' + q.race_no + '</span>' + typeTag +
                '<span style="font-weight:700;">' + (bp.name || '') + '</span></div>' +
                '<div style="display:flex;align-items:center;gap:8px;"><span style="font-size:11px;color:var(--green);">' + (bp.returnText || '') + '</span>' +
                '<button class="btn secondary" style="padding:3px 8px;font-size:10px;" onclick="selectRaceId(\'' + q.raceId + '\');">入去</button></div></div>';
            }).join('') + '</div>'
          : '<div style="color:var(--text-dim);font-size:12px;padding:10px;">暫無連贏 Q 推薦</div>';

        todayAI.innerHTML = headerHtml +
          '<div style="padding:0 4px;"><div style="color:var(--gold);font-size:12px;font-weight:800;margin-bottom:8px;">🏇 每場賽事 AI 重心 Top4（點馬睇詳細報告）</div>' + raceCardsHtml + '</div>' +
          '<div style="padding:18px 4px 0;"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">' +
          '<h3 style="margin:0;font-size:15px;"><span class="emoji">⭐</span>核心重心馬匹名單（所有場次 AI #1）</h3>' +
          '<span style="font-size:11px;color:var(--text-dim);">' + coreHorses.length + ' 隻</span></div>' + coreListHtml + '</div>' +
          '<div style="padding:18px 4px 12px;"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">' +
          '<h3 style="margin:0;font-size:15px;"><span class="emoji">🧧</span>重心連贏 Q 推薦</h3>' +
          '<span style="font-size:11px;color:var(--text-dim);">精選 ' + Math.min(6, qPicksBrief.length) + ' 組</span></div>' + qBriefHtml + '</div>' +
          '</div>';
      }
    }
  }

  /* ========== 騎師 / 練馬師加成 ========== */
  function jockeyBonus(name, distance, trainerName) {
    const j = DB.jockeysDB[name];
    if (!j) return 50;
    const win_rate = typeof j.win_rate === 'number' ? j.win_rate : 0;
    const q_rate = typeof j.q_rate === 'number' ? j.q_rate : 0;
    const season = (j.season_stats && (j.season_stats['2025/26'] || j.season_stats['2024/25'])) || { win_rate: win_rate, place_rate: q_rate };
    const distWR = (j.distance_win_rate && j.distance_win_rate[distance + 'm']) || season.win_rate;
    const synergy = (j.trainer_synergy && j.trainer_synergy[trainerName]) || season.win_rate;
    const form = (typeof j.current_form === 'number' ? j.current_form : (win_rate ? Math.min(95, 40 + win_rate * 350) : 60)) / 100;
    const score = (season.win_rate * 0.3 + season.place_rate * 0.3 + distWR * 0.2 + synergy * 0.2) * 200 + form * 20;
    return Math.min(100, Math.max(0, Math.round(score * 10) / 10));
  }
  function trainerBonus(name, distance) {
    const t = DB.trainersDB[name];
    if (!t) return 50;
    const win_rate = typeof t.win_rate === 'number' ? t.win_rate : 0;
    const q_rate = typeof t.q_rate === 'number' ? t.q_rate : 0;
    const season = (t.season_stats && (t.season_stats['2025/26'] || t.season_stats['2024/25'])) || { win_rate: win_rate, place_rate: q_rate };
    const distWR = (t.distance_win_rate && t.distance_win_rate[distance + 'm']) || season.win_rate;
    const streak = (typeof t.hot_streak === 'number' ? t.hot_streak : (win_rate ? win_rate * 1.8 : 0.15));
    const form = (typeof t.recent_form === 'number' ? t.recent_form : (win_rate ? Math.min(95, 40 + win_rate * 350) : 60)) / 100;
    const score = (season.win_rate * 0.4 + season.place_rate * 0.3 + distWR * 0.3) * 220 + streak * 60 + form * 20;
    return Math.min(100, Math.max(0, Math.round(score * 10) / 10));
  }

  function computeAdvancedScore(race) {
    const analysis = RacingAI.runFullAnalysis(race);
    const info = race.race_info || {};
    const dist = info.distance_m;
    const scored = analysis.all_ranked_horses.map(function (h) {
      const jB = jockeyBonus(h.jockey, dist, h.trainer);
      const tB = trainerBonus(h.trainer, dist);
      const baseTotal = h.scores && (typeof h.scores.total === 'number') ? h.scores.total : 50;
      const jBscore = isNaN(jB) ? 50 : jB;
      const tBscore = isNaN(tB) ? 50 : tB;
      const newTotal = Math.round((baseTotal * 0.74 + jBscore * 0.14 + tBscore * 0.12) * 10) / 10;
      const s = Object.assign({}, h.scores, { jockey_bonus: jBscore, trainer_bonus: tBscore, total: newTotal });
      return Object.assign({}, h, { scores: s });
    });
    scored.sort(function (a, b) { return b.scores.total - a.scores.total; });
    scored.forEach(function (h, i) { h.ai_rank = i + 1; });
    const top4 = scored.slice(0, 4);
    const predictions = top4.map(function (h, i) {
      return { rank: i + 1, horse: h, core_advantage: RacingAI.coreAdvantage(h) };
    });
    const betting = RacingAI.generateBetting(top4, scored, info);
    return {
      generated_at: analysis.generated_at,
      race_info: info,
      pace_analysis: analysis.pace_analysis,
      top4_predictions: predictions,
      all_ranked_horses: scored,
      betting_strategy: betting
    };
  }

  /* ========== 賽事卡片列表渲染 ========== */
  function renderRaceCards() {
    const host = $('raceCardsContainer');
    if (!host) return;

    const byDate = getRaceByDateMap();
    const dates = Object.keys(byDate).sort().reverse();
    const today = todayStr();
    const defaultDateKey = dates.find(function (d) { return d === today; }) ||
      dates.find(function (d) { return byDate[d].some(function (id) { return !DB.races[id].race_info.result_available; }); }) ||
      dates[0];

    // 已選賽事 or 顯示日期範圍（預設：如果 currentRaceId 有就用嗰日 + 今日；否則今日）
    const selId = DB.currentRaceId;
    let targetIds = [];
    let headerLabel = '';
    if (selId && DB.races[selId]) {
      const sInfo = DB.races[selId].race_info;
      const sameDay = byDate[sInfo.race_date] || [];
      targetIds = sameDay.slice().sort(function (a, b) {
        return (DB.races[a].race_info.race_number || 0) - (DB.races[b].race_info.race_number || 0);
      });
      const venue = sInfo.venue === 'HV' ? '跑馬地' : '沙田';
      headerLabel = sInfo.race_date + ' · ' + venue + ' · 第 1-' + targetIds.length + ' 場';
    } else if (defaultDateKey) {
      targetIds = byDate[defaultDateKey].slice().sort(function (a, b) {
        return (DB.races[a].race_info.race_number || 0) - (DB.races[b].race_info.race_number || 0);
      });
      const vInfo = DB.races[targetIds[0]].race_info;
      const venue = vInfo.venue === 'HV' ? '跑馬地' : '沙田';
      headerLabel = defaultDateKey + (defaultDateKey === today ? ' · 今日' : '') + ' · ' + venue;
    }

    const filtered = targetIds.filter(function (id) {
      const done = DB.races[id].race_info.result_available;
      if (DB.raceFilter === 'pending') return !done;
      if (DB.raceFilter === 'finished') return done;
      return true;
    });

    const pickerCard = '<div class="card" style="padding:14px 16px;">' +
      '<div style="display:flex;align-items:center;justify-content:space-between;gap:10px;">' +
      '<div><div style="font-size:15px;font-weight:700;">📋 ' + (headerLabel || '請選擇賽事') + '</div>' +
      '<div style="color:var(--text-dim);font-size:12px;margin-top:3px;">點擊下方按鈕切換日期同場次</div></div>' +
      '<button class="btn primary" onclick="openRacePicker()" style="padding:6px 12px;font-size:12px;">🎯 選擇賽事</button></div></div>';

    if (!filtered.length) {
      host.innerHTML = pickerCard +
        '<div class="card" style="text-align:center;color:var(--text-dim);padding:28px 16px;">暫無符合條件的賽事（請切換 sub-tab 或重新選擇）</div>';
      return;
    }

    host.innerHTML = pickerCard + filtered.map(function (id) {
      const data = DB.races[id];
      const info = data.race_info;
      const isExpanded = (id === DB.currentRaceId);
      const done = info.result_available;
      const postTime = info.post_time || '--:--';
      const horseCount = (data.horses && data.horses.length) || info.num_horses || 0;
      return '<div class="race-card ' + (done ? 'finished' : 'pending') + (isExpanded ? ' expanded' : '') + '" data-raceid="' + id + '">' +
        '<div class="race-card-header">' +
          '<div class="race-header-main">' +
            '<span class="race-num-badge">第 ' + info.race_number + ' 場 ' + info.class + '</span>' +
            '<div class="race-name">' + (info.venue === 'HV' ? '跑馬地' : '沙田') + ' · ' + (info.track || '') + ' · ' + info.distance_m + 'm' + '</div>' +
            '<div class="race-meta-row">' +
              '<span>📅 <b>' + info.race_date + '</b></span>' +
              '<span>🕒 <b>' + postTime + '</b></span>' +
              '<span>🐎 <b>' + horseCount + ' 匹</b></span>' +
              (done ? '<span style="color:var(--blue);">✓ 已完賽</span>' : '<span style="color:var(--gold);">⏳ 待賽</span>') +
            '</div>' +
          '</div>' +
          '<div class="race-header-right">' +
            (done ? '' :
              '<div class="countdown-circle"><div class="time">' + postTime + '</div><div class="label">開跑</div></div>') +
            '<div class="race-chevron">▼</div>' +
          '</div>' +
        '</div>' +
        '<div class="race-card-body" id="raceBody_' + id.replace(/[^a-zA-Z0-9]/g, '_') + '">' +
          (isExpanded ? renderRaceBody(id) : '') +
        '</div>' +
      '</div>';
    }).join('');

    host.querySelectorAll('.race-card-header').forEach(function (h) {
      h.addEventListener('click', function () {
        const card = h.parentElement;
        const id = card.dataset.raceid;
        const wasExpanded = card.classList.contains('expanded');
        DB.currentRaceId = wasExpanded ? null : id;
        if (!wasExpanded) {
          const bodyId = 'raceBody_' + id.replace(/[^a-zA-Z0-9]/g, '_');
          const body = document.getElementById(bodyId);
          if (body && !body.innerHTML.trim()) {
            body.innerHTML = renderRaceBody(id);
          }
        }
        card.classList.toggle('expanded', !wasExpanded);
      });
    });
  }

  function renderRaceBody(id) {
    const data = DB.races[id];
    if (!data) return '';
    const info = data.race_info;
    const analysis = computeAdvancedScore(data);

    const metaCells = [
      ['場地', info.venue],
      ['距離', info.distance_m + 'm'],
      ['跑道', info.track || '—'],
      ['班次', info.class || '—'],
      ['評分', info.rating_range || '—'],
      ['場況', info.going || '—'],
      ['參賽', ((data.horses && data.horses.length) || 0) + ' 匹'],
      ['狀態', info.result_available ? '已完賽' : '待賽']
    ].map(function (kv) {
      return '<div class="meta-cell"><div class="label">' + kv[0] + '</div><div class="value">' + kv[1] + '</div></div>';
    }).join('');

    const pace = analysis.pace_analysis;
    const medals = ['🥇', '🥈', '🥉'];
    const frontHtml = (pace.front_leaders || []).map(function (l, i) {
      return '<div class="pace-item horse-click" data-number="' + (l.number || '') + '" data-name="' + (l.name || '') + '">' +
        '<div class="info"><b>' + (medals[i] || '•') + ' #' + l.number + ' ' + (l.name || '') + '</b>' +
        '<div class="small">' + (l.draw ? l.draw + '檔' : '') + '</div></div>' +
        '<span class="pace-score">' + l.score + '</span></div>';
    }).join('') || '<div class="pace-desc">—</div>';
    const beneHtml = (pace.beneficiaries || []).map(function (b) {
      return '<div class="pace-item horse-click" data-number="' + (b.number || '') + '" data-name="' + (b.name || '') + '">' +
        '<div class="info"><b>#' + b.number + ' ' + (b.name || '') + '</b></div>' +
        '<span class="pace-score">' + b.score + '</span></div>';
    }).join('') || '<div class="pace-desc">—</div>';

    function fmtOddsUI(o) {
      if (o == null || typeof o !== 'number' || !isFinite(o) || o >= 999 || o <= 0) return '--';
      return (Math.round(o * 10) / 10).toFixed(1) + 'x';
    }
    function fmtTimeUI(t) {
      if (t == null || typeof t !== 'number' || !isFinite(t) || t >= 999 || t <= 0) return '--';
      var m = Math.floor(t / 60);
      var s = (t - m * 60).toFixed(2);
      if (m > 0) return m + 'm' + (s.length < 5 ? '0' : '') + s + 's';
      return parseFloat(s).toFixed(2) + 's';
    }
    function fmtOddsRawUI(o) {
      if (o == null || typeof o !== 'number' || !isFinite(o) || o >= 999 || o <= 0) return '--';
      return String(o);
    }
    const top4Html = analysis.top4_predictions.map(function (p) {
      const h = p.horse, s = h.scores, rank = p.rank;
      const l3 = last6Badge(h);
      return '<div class="rank-card rank-' + rank + ' horse-click" data-number="' + h.number + '" data-name="' + h.name + '">' +
        '<div class="rank-medal">' + rank + '</div>' +
        '<div class="horse-num">#' + h.number + ' · ' + h.draw + '檔</div>' +
        '<div class="horse-name">#' + h.number + ' ' + (h.name || '') + ccExpertBadge(h) + '</div>' +
        '<div class="rank-stats">' +
        '<div class="stat"><div class="label">評分</div><div class="val">' + h.rating + '</div></div>' +
        '<div class="stat"><div class="label">最佳</div><div class="val">' + fmtTimeUI(h.best_time_sec) + '</div></div>' +
        '<div class="stat"><div class="label">獨贏</div><div class="val">' + fmtOddsUI(h.odds_win) + '</div></div>' +
        '</div>' +
        '<div style="margin-bottom:6px;">' + l3 + '</div>' +
        '<div class="ai-score-label"><span>AI 分</span><b>' + s.total.toFixed(1) + '</b></div>' +
        '<div class="ai-score-bar"><div class="fill" style="width:' + Math.min(100, s.total) + '%;"></div></div>' +
        '<div style="font-size:11px;color:var(--text-dim);margin:4px 0 6px;">' + h.jockey + '/' + h.trainer + '</div>' +
        '<div class="core-adv" style="font-size:12px;">✨ ' + p.core_advantage + '</div>' +
        '</div>';
    }).join('');

    const bet = analysis.betting_strategy;
    const hot = bet.overpriced_hot;
    const hotWarnHtml = (hot && hot.available === true && hot.code) ? (
      '<div class="hot-warn">' +
        '<div class="warn-title">⚠️ 過熱：#' + (hot.number || '') + ' ' + hot.name + ' <small style="font-weight:400;">賠率 ' + (hot.oddsDisplay || fmtOddsUI(hot.odds)) + '</small></div>' +
        '<ul>' + (hot.concerns || []).map(function (c) { return '<li>' + c + '</li>'; }).join('') + '</ul>' +
      '</div>') : '';

    function betReturnTag(text) {
      if (!text) return '';
      return '<div style="margin-top:4px;padding:2px 6px;border-radius:4px;background:rgba(80,200,140,0.1);color:#78e0a8;font-size:10.5px;font-weight:700;display:inline-block;">💵 ' + text + '</div>';
    }

    function aiDetailBlock(detail) {
      if (!detail) return '';
      return '<details style="margin-top:5px;"><summary style="cursor:pointer;font-size:11px;color:var(--gold);user-select:none;">🧠 AI 詳細分析（往績/檔位/騎師/場地/壯態）</summary>' +
        '<div style="margin-top:5px;padding:7px 10px;border-radius:6px;background:rgba(255,255,255,0.03);font-size:11.5px;line-height:1.65;color:var(--text-dim);white-space:pre-wrap;">' + detail + '</div></details>';
    }

    const winCard = '<div class="bet-card"><h4>🎯 獨贏</h4><div class="content">' +
      (bet.win_picks || []).map(function (w) {
        return '<div style="margin-bottom:10px;padding:6px 0;border-bottom:1px dashed rgba(255,255,255,0.06);">' +
          '<div style="display:flex;align-items:center;gap:6px;"><b class="odds" style="font-size:16px;">' + (w.oddsDisplay || fmtOddsUI(w.odds)) + '</b> ' +
          '<b style="font-size:14px;">#' + w.number + ' ' + w.name + '</b></div>' +
          '<div style="color:var(--text-dim);font-size:12px;margin-top:3px;">🧠 ' + w.reason + '</div>' +
          betReturnTag(w.returnText) +
          aiDetailBlock(w.detail) + '</div>';
      }).join('') + '</div></div>';

    const placeCard = '<div class="bet-card"><h4>📍 位置</h4><div class="content">' +
      (bet.place_picks && bet.place_picks.length ? bet.place_picks.map(function (p) {
        return '<div style="margin-bottom:10px;padding:6px 0;border-bottom:1px dashed rgba(255,255,255,0.06);">' +
          '<div style="display:flex;align-items:center;gap:6px;">' +
          '<span style="display:inline-block;min-width:22px;height:22px;line-height:22px;border-radius:50%;background:linear-gradient(135deg,#1e3a5f,#2f6fbf);color:#fff;font-weight:900;font-size:11px;text-align:center;">#' + p.rank + '</span>' +
          '<b style="font-size:14px;">#' + p.number + ' ' + p.name + '</b>' +
          '<span style="margin-left:auto;color:#9ecbff;font-weight:800;">位置 ' + (p.oddsDisplay || fmtOddsUI(p.odds_place)) + '</span>' +
          '</div>' +
          '<div style="color:var(--text-dim);font-size:12px;margin-top:3px;">🧠 ' + p.reason + '</div>' +
          betReturnTag(p.returnText) +
          aiDetailBlock(p.detail) + '</div>';
      }).join('') : '<div style="color:var(--text-dim);font-size:12px;">暫無位置推薦</div>') +
      '</div></div>';

    const qCard = '<div class="bet-card"><h4>🤝 連贏 Q</h4><div class="content">' +
      (bet.q_combos || []).map(function (q) {
        const cls = q.type && q.type.indexOf('核心') >= 0 ? 'core' : (q.type && q.type.indexOf('穩健') >= 0 ? 'safe' : '');
        return '<div style="margin-bottom:10px;padding:6px 0;border-bottom:1px dashed rgba(255,255,255,0.06);">' +
          '<span class="bet-tag ' + cls + '">' + q.type + '</span>' +
          '<div style="margin-top:4px;display:flex;align-items:center;gap:6px;">' +
          '<b style="color:var(--gold);">Q</b>' +
          '<b style="flex:1;">#' + q.a_number + ' ' + (q.a_name || q.a) + ' × #' + q.b_number + ' ' + (q.b_name || q.b) + '</b>' +
          '<span style="color:#ffd27a;font-weight:800;">~' + (q.oddsDisplay || fmtOddsUI(q.odds_quinella)) + '</span>' +
          '</div>' +
          betReturnTag(q.returnText) +
          '<div style="margin-top:4px;padding:4px 0;border-left:2px solid rgba(255,210,122,0.35);padding-left:8px;">' +
          '<div style="font-size:11px;color:var(--gold);font-weight:700;margin-bottom:2px;">🅰️ 馬 ' + '#' + q.a_number + ' ' + (q.a_name || q.a) + '</div>' +
          aiDetailBlock(q.a_detail) +
          '</div>' +
          '<div style="margin-top:4px;padding:4px 0;border-left:2px solid rgba(255,210,122,0.2);padding-left:8px;">' +
          '<div style="font-size:11px;color:var(--gold);font-weight:700;margin-bottom:2px;">🅱️ 馬 ' + '#' + q.b_number + ' ' + (q.b_name || q.b) + '</div>' +
          aiDetailBlock(q.b_detail) +
          '</div></div>';
      }).join('') + '</div></div>';

    const qplaceCard = '<div class="bet-card"><h4>🎪 位置 Q</h4><div class="content">' +
      (bet.qplace_combos && bet.qplace_combos.length ? bet.qplace_combos.map(function (q) {
        return '<div style="margin-bottom:10px;padding:6px 0;border-bottom:1px dashed rgba(255,255,255,0.06);">' +
          '<span class="bet-tag" style="background:rgba(100,180,130,0.2);border:1px solid rgba(80,200,140,0.35);color:#7ee0a8;">' + q.type + '</span>' +
          '<div style="margin-top:4px;display:flex;align-items:center;gap:6px;">' +
          '<b style="color:#7ee0a8;">QPl</b>' +
          '<b style="flex:1;">#' + q.a_number + ' ' + (q.a_name || q.a) + ' × #' + q.b_number + ' ' + (q.b_name || q.b) + '</b>' +
          '<span style="color:#a8f0c8;font-weight:800;">~' + (q.oddsDisplay || fmtOddsUI(q.odds_qplace)) + '</span>' +
          '</div>' +
          betReturnTag(q.returnText) +
          '<div style="margin-top:4px;padding:4px 0;border-left:2px solid rgba(126,224,168,0.35);padding-left:8px;">' +
          '<div style="font-size:11px;color:#7ee0a8;font-weight:700;margin-bottom:2px;">🅰️ 馬 ' + '#' + q.a_number + ' ' + (q.a_name || q.a) + '</div>' +
          aiDetailBlock(q.a_detail) +
          '</div>' +
          '<div style="margin-top:4px;padding:4px 0;border-left:2px solid rgba(126,224,168,0.2);padding-left:8px;">' +
          '<div style="font-size:11px;color:#7ee0a8;font-weight:700;margin-bottom:2px;">🅱️ 馬 ' + '#' + q.b_number + ' ' + (q.b_name || q.b) + '</div>' +
          aiDetailBlock(q.b_detail) +
          '</div></div>';
      }).join('') : '<div style="color:var(--text-dim);font-size:12px;">暫無位置Q推薦</div>') +
      '</div></div>';

    const trioCard = (function () {
      const t = bet.triple_chase;
      if (!t || !t.banker) return '<div class="bet-card"><h4>🧩 單 T 三重彩</h4><div class="content" style="color:var(--text-dim);font-size:12px;">暫無三重彩推薦</div></div>';
      const legs = t.legs || [];
      const legHtml = legs.map(function (l, i) {
        return '<div style="padding:3px 0;">' +
          '<div style="display:grid;grid-template-columns:22px 1fr auto;gap:6px;align-items:center;">' +
          '<span style="display:inline-block;width:22px;height:22px;line-height:22px;border-radius:5px;background:linear-gradient(135deg,#3a1e5f,#7a40d0);color:#fff;font-weight:900;font-size:11px;text-align:center;">T' + (i + 2) + '</span>' +
          '<b>#' + l.number + ' ' + l.name + '</b>' +
          '<span style="font-size:11px;color:var(--text-dim);">' + (l.oddsDisplay || fmtOddsUI(l.odds)) + '</span>' +
          '</div>' +
          aiDetailBlock(l.detail) +
          '</div>';
      }).join('');
      return '<div class="bet-card"><h4>🧩 單 T 三重彩</h4><div class="content">' +
        '<div style="padding:8px 10px;border-radius:8px;background:linear-gradient(135deg,rgba(200,100,50,0.12),rgba(120,70,30,0.05));border:1px solid rgba(240,160,80,0.35);margin-bottom:8px;">' +
        '<div style="display:grid;grid-template-columns:28px 1fr auto;gap:8px;align-items:center;">' +
        '<span style="display:inline-block;width:28px;height:28px;line-height:28px;border-radius:7px;background:linear-gradient(135deg,#c4471a,#ff8b3d);color:#fff;font-weight:900;font-size:13px;text-align:center;">膽</span>' +
        '<b style="font-size:14px;">#' + t.banker.number + ' ' + t.banker.name + '</b>' +
        '<span style="color:#ffae6a;font-weight:800;">主膽</span>' +
        '</div>' +
        aiDetailBlock(t.banker.detail) +
        '</div>' +
        (legs.length ? legHtml : '') +
        '<div style="margin-top:8px;padding:5px 8px;border-radius:5px;background:rgba(255,255,255,0.03);font-size:11px;color:var(--text-dim);">' +
        '💡 玩法：膽 #1 拖 ' + legs.length + ' 腳，任 3 匹入三甲（順序不限）即中。<br>' +
        (t.stake_text ? ('注碼：' + t.stake_text + '<br>') : '') +
        '預估賠率：<b style="color:var(--gold);">~' + (t.oddsDisplay || fmtOddsUI(t.estimated_odds)) + '</b>' +
        betReturnTag(t.returnText).replace(/^<div/, '<div style="margin-left:0;margin-top:6px;') +
        '</div></div></div>';
    })();

    const f4Card = (function () {
      const f = bet.first4_chase;
      if (!f || !f.banker) return '<div class="bet-card"><h4>🏆 四重彩</h4><div class="content" style="color:var(--text-dim);font-size:12px;">暫無四重彩推薦</div></div>';
      const legs = f.legs || [];
      const legsInline = legs.map(function (l) { return '#' + l.number + ' ' + l.name; }).join(' / ');
      const legDetails = legs.map(function (l, i) {
        return '<div style="margin-top:4px;padding:4px 0;border-left:2px solid rgba(100,160,240,0.25);padding-left:8px;">' +
          '<div style="font-size:11px;color:#9ecbff;font-weight:700;margin-bottom:2px;">拖腳 ' + (i + 1) + '：#' + l.number + ' ' + l.name + '</div>' +
          aiDetailBlock(l.detail) +
          '</div>';
      }).join('');
      return '<div class="bet-card"><h4>🏆 四重彩</h4><div class="content">' +
        '<div style="padding:8px 10px;border-radius:8px;background:linear-gradient(135deg,rgba(60,100,160,0.15),rgba(30,60,120,0.05));border:1px solid rgba(100,160,240,0.35);margin-bottom:8px;">' +
        '<div style="display:grid;grid-template-columns:28px 1fr auto;gap:8px;align-items:center;">' +
        '<span style="display:inline-block;width:28px;height:28px;line-height:28px;border-radius:7px;background:linear-gradient(135deg,#1e5fbf,#4a9cff);color:#fff;font-weight:900;font-size:13px;text-align:center;">膽</span>' +
        '<b style="font-size:14px;">#' + f.banker.number + ' ' + f.banker.name + '</b>' +
        '<span style="color:#7fb4ff;font-weight:800;">頭馬膽</span>' +
        '</div>' +
        aiDetailBlock(f.banker.detail) +
        '</div>' +
        (legsInline ? '<div style="font-size:12px;color:var(--text-dim);margin-bottom:6px;">🧩 拖腳：' + legsInline + '</div>' : '') +
        legDetails +
        '<div style="padding:5px 8px;border-radius:5px;background:rgba(255,255,255,0.03);font-size:11px;color:var(--text-dim);margin-top:8px;">' +
        '💡 玩法：膽 #1 拖 ' + legs.length + ' 腳，須中前四名（位置不限）。<br>' +
        (f.stake_text ? ('注碼：' + f.stake_text + '<br>') : '') +
        '預估賠率：<b style="color:#9ecbff;">~' + (f.oddsDisplay || fmtOddsUI(f.estimated_odds)) + '</b>' +
        betReturnTag(f.returnText).replace(/^<div/, '<div style="margin-left:0;margin-top:6px;') +
        '</div></div></div>';
    })();

    const coldCard = '<div class="bet-card"><h4>🧊 冷馬</h4><div class="content">' +
      (bet.cold_bets && bet.cold_bets.length ? bet.cold_bets.map(function (c) {
        return '<div style="margin-bottom:10px;padding:6px 0;border-bottom:1px dashed rgba(255,255,255,0.06);">' +
          '<div style="display:flex;align-items:center;gap:6px;">' +
          '<span class="bet-tag cold">冷門</span>' +
          '<b class="odds cold" style="font-size:16px;margin-left:4px;">' + (c.oddsDisplay || fmtOddsUI(c.odds)) + '</b> ' +
          '<b style="font-size:14px;">#' + c.number + ' ' + c.name + '</b>' +
          '</div>' +
          (c.odds_place_est && c.odds_place_est < 999 ? '<div style="font-size:11px;color:#9ecbff;margin-top:2px;">位置 ~' + c.odds_place_est + 'x（保底玩法）</div>' : '') +
          '<div style="color:var(--text-dim);font-size:12px;margin-top:3px;">🎯 ' + c.potential + '</div>' +
          aiDetailBlock(c.detail) +
          betReturnTag(c.returnText) + '</div>';
      }).join('') : '<div style="color:var(--text-dim);font-size:12px;">暫無明顯冷馬（需真實賠率數據）</div>') +
      '</div></div>';

    const budgetHtml = '';

    const horsesHtml = '<div class="table-scroll" style="margin-top:4px;">' +
      '<table class="data-table" style="min-width:1020px;"><thead><tr>' +
      '<th>排名</th><th>馬號</th><th>馬匹</th><th>檔</th><th>評分</th><th>體重</th><th>近績6</th><th>晨</th><th>醫</th><th>異</th><th>獨贏</th>' +
      '<th title="晨操狀態">操</th><th title="路程專長">路</th><th title="騎馬默契">契</th><th title="評分走勢/同班適應">勢</th>' +
      '<th>騎+</th><th>練+</th><th>AI總分</th>' +
      '</tr></thead><tbody>' +
      analysis.all_ranked_horses.map(function (h) {
        const s = h.scores;
        const aug = h.aug || {};
        const oddsCls = h.odds_win <= 5 ? 'hot' : (h.odds_win >= 20 ? 'cold' : '');
        let rpCls = '';
        if (h.ai_rank === 1) rpCls = 'top1';
        else if (h.ai_rank === 2) rpCls = 'top2';
        else if (h.ai_rank === 3) rpCls = 'top3';
        else if (h.ai_rank === 4) rpCls = 'top4';
        const l3 = last6Badge(h);
        const twScore = s.trackwork || 0;
        const twTitle = aug.trackwork ? (aug.trackwork.detail || '') : '';
        const twCls = twScore >= 80 ? 'good' : (twScore >= 60 ? 'mid' : 'bad');
        const formScore = (typeof s.form === 'number' && isFinite(s.form)) ? s.form : 50;
        const formCls = formScore >= 75 ? 'good' : (formScore >= 55 ? 'mid' : 'bad');
        const formTitle = (aug.form_detail && aug.form_detail.note) ? String(aug.form_detail.note).slice(0, 80) : '形勢評分（來源 Formline）';
        const vetScore = (typeof s.vet === 'number' && isFinite(s.vet)) ? s.vet : 90;
        const vetCls = vetScore >= 85 ? 'good' : (vetScore >= 65 ? 'mid' : 'bad');
        const vetTitle = (aug.vet_detail && aug.vet_detail.note) ? (aug.vet_detail.flags && aug.vet_detail.flags.length ? aug.vet_detail.flags.join('、') + ' · ' : '') + String(aug.vet_detail.note).slice(0, 80) : '獸醫健康評分（來源 VeterinaryRecord）';
        const exceptScore = (typeof s.except === 'number' && isFinite(s.except)) ? s.except : 80;
        const exceptCls = exceptScore >= 80 ? 'good' : (exceptScore >= 60 ? 'mid' : 'bad');
        const exceptTitle = (aug.except_detail && aug.except_detail.note) ? (aug.except_detail.flags && aug.except_detail.flags.length ? aug.except_detail.flags.join('、') + ' · ' : '') + String(aug.except_detail.note).slice(0, 80) : '異常因素評分（來源 ExceptionalFactors）';
        const distScore = s.distance || 0;
        const distTitle = aug.distance ? (aug.distance.detail || '') : '';
        const distCls = distScore >= 75 ? 'good' : (distScore >= 55 ? 'mid' : 'bad');
        const synScore = s.synergy || 0;
        const synTitle = aug.synergy ? (aug.synergy.detail || '') : '';
        const synCls = synScore >= 80 ? 'good' : (synScore >= 58 ? 'mid' : 'bad');
        const trScore = s.trend || 0;
        const trTitle = aug.trend ? (aug.trend.detail || '') : '';
        const trCls = trScore >= 70 ? 'good' : (trScore >= 55 ? 'mid' : 'bad');
        return '<tr class="horse-click" data-number="' + h.number + '" data-name="' + h.name + '">' +
          '<td><span class="rank-pill ' + rpCls + '">' + h.ai_rank + '</span></td>' +
          '<td><b>#' + h.number + '</b></td>' +
          '<td><div><b>' + (h.name || '') + ccExpertBadge(h, true) + '</b></div>' +
          '<div style="font-size:11px;color:var(--text-dim);">' + (h.jockey || '') + '/' + (h.trainer || '') + '</div></td>' +
          '<td>' + h.draw + '</td>' +
          '<td>' + h.rating + '</td>' +
          '<td>' + h.weight + '</td>' +
          '<td>' + l3 + '</td>' +
          '<td title="' + formTitle.replace(/"/g, '&quot;') + '" style="cursor:help;"><span class="mini-pill ' + formCls + '">' + Math.round(formScore) + '</span></td>' +
          '<td title="' + vetTitle.replace(/"/g, '&quot;') + '" style="cursor:help;"><span class="mini-pill ' + vetCls + '">' + Math.round(vetScore) + '</span></td>' +
          '<td title="' + exceptTitle.replace(/"/g, '&quot;') + '" style="cursor:help;"><span class="mini-pill ' + exceptCls + '">' + Math.round(exceptScore) + '</span></td>' +
          '<td class="odds ' + oddsCls + '">' + fmtOddsUI(h.odds_win) + '</td>' +
          '<td title="' + twTitle + '" style="cursor:help;"><span class="mini-pill ' + twCls + '">' + Math.round(twScore) + '</span></td>' +
          '<td title="' + distTitle + '" style="cursor:help;"><span class="mini-pill ' + distCls + '">' + Math.round(distScore) + '</span></td>' +
          '<td title="' + synTitle + '" style="cursor:help;"><span class="mini-pill ' + synCls + '">' + Math.round(synScore) + '</span></td>' +
          '<td title="' + trTitle + '" style="cursor:help;"><span class="mini-pill ' + trCls + '">' + Math.round(trScore) + '</span></td>' +
          '<td style="color:var(--green);font-weight:700;font-size:12px;">+' + (s.jockey_bonus || 0).toFixed(1) + '</td>' +
          '<td style="color:var(--blue);font-weight:700;font-size:12px;">+' + (s.trainer_bonus || 0).toFixed(1) + '</td>' +
          '<td><div style="display:flex;align-items:center;gap:6px;"><b style="color:var(--gold);">' + s.total.toFixed(1) + '</b>' +
          '<div class="mini-score"><div class="fill" style="width:' + Math.min(100, s.total) + '%;"></div></div></div></td>' +
          '</tr>';
      }).join('') + '</tbody></table></div>';

    return '<div class="race-section">' +
        '<div class="race-section-title">賽事資訊</div>' +
        '<div class="race-meta-grid">' + metaCells + '</div>' +
      '</div>' +
      '<div class="race-section">' +
        '<div class="race-section-title">步速預測 · ' + pace.pace_type + '</div>' +
        '<div class="pace-tag">' + pace.pace_type + ' PACE</div>' +
        '<div class="pace-desc">' + pace.pace_reason + '</div>' +
        '<div class="pace-grid">' +
          '<div class="pace-subcard"><h4>🏁 爭放頭馬</h4>' + frontHtml + '</div>' +
          '<div class="pace-subcard"><h4>🎯 受惠馬匹</h4>' + beneHtml + '</div>' +
        '</div>' +
      '</div>' +
      '<div class="race-section">' +
        '<div class="race-section-title">AI 頭 4 預測</div>' +
        '<div class="rank-grid">' + top4Html + '</div>' +
      '</div>' +
      '<div class="race-section">' +
        '<div class="race-section-title">投注策略</div>' +
        hotWarnHtml +
        '<div class="bet-grid" style="grid-template-columns:1fr 1fr;">' +
        winCard + placeCard + qCard + qplaceCard + trioCard + f4Card + coldCard +
        '</div>' +
      '</div>' +
      '<div class="race-section">' +
        '<div class="race-section-title">全馬評分一覽</div>' +
        horsesHtml +
      '</div>';
  }

  function reanalyzeCurrent() {
    if (!DB.currentRaceId) { toast('請先於「賽程」展開一場賽事', 'warn'); return; }
    toast('🧠 重新計算 ' + DB.currentRaceId + ' ...');
    const id = DB.currentRaceId;
    const bodyId = 'raceBody_' + id.replace(/[^a-zA-Z0-9]/g, '_');
    const body = document.getElementById(bodyId);
    if (body) body.innerHTML = renderRaceBody(id);
    if ($('lastUpdate')) $('lastUpdate').textContent = new Date().toLocaleString();
    toast('✅ 完成', 'success');
  }
  async function hardResetCacheAndReload() {
    toast('🔄 強制重置快取…', 'warn');
    try {
      if (window.caches && typeof caches.keys === 'function') {
        try {
          const ks = await caches.keys();
          for (let i = 0; i < ks.length; i++) { try { await caches.delete(ks[i]); } catch (_) {} }
        } catch (_) {}
      }
      if ('serviceWorker' in navigator) {
        try {
          const regs = await navigator.serviceWorker.getRegistrations();
          for (let i = 0; i < regs.length; i++) { try { await regs[i].unregister(); } catch (_) {} }
        } catch (_) {}
      }
    } finally {
      setTimeout(function () {
        try {
          if (window.location && typeof window.location.reload === 'function') {
            window.location.reload(true);
            return;
          }
        } catch (_) {}
        window.location.href = window.location.pathname + '?_=' + Date.now();
      }, 400);
    }
  }
  window.hardResetCacheAndReload = hardResetCacheAndReload;
  function manualRefresh() {
    if (window.location.search.indexOf('hardreset=1') >= 0) {
      return hardResetCacheAndReload();
    }
    loadAll();
  }
  async function triggerDataRefresh() {
    toast('🧹 正在同步最新數據，請稍候...');
    try {
      const r = await fetch('/api/refresh', { method: 'GET', cache: 'no-store' });
      const data = await r.json();
      if (!data || data.ok === false) {
        if (data && data.status === 'running') {
          toast('⏳ ' + (data.message || '同步進行中'), 'warn');
        } else {
          toast('❌ 同步失敗：' + ((data && data.error) || (data && data.message) || '未知錯誤'), 'warn');
        }
        return;
      }
      const copied = data.copied_files || 0;
      const races = data.total_races || 0;
      const newR = data.new_races || 0;
      const dur = data.duration_sec || 0;
      let msg = '✅ 同步完成：' + races + ' 場賽事';
      if (newR > 0) msg += ' (+' + newR + ' 新場)';
      msg += '，更新 ' + copied + ' 個檔案';
      if (dur > 0) msg += ' (' + dur + 's)';
      toast(msg, 'success');
      setTimeout(function () {
        window.location.reload(true);
      }, 1200);
    } catch (e) {
      toast('❌ 同步出錯：' + e.message, 'warn');
    }
  }
  window.reanalyzeCurrent = reanalyzeCurrent;
  window.manualRefresh = manualRefresh;
  window.triggerDataRefresh = triggerDataRefresh;

  function renderHistoryTable() {
    const host = document.querySelector('#historyTable tbody');
    if (!host) return;
    const S = DB.historyStats || { finished: [] };
    host.innerHTML = S.finished.slice().reverse().map(function (x) {
      const info = x.info;
      const horses = (DB.races[x.id] && DB.races[x.id].horses) ? DB.races[x.id].horses : [];
      const realTop3Label = (x.realTop3 || []).map(function (c) { return codeToHorseLabel(c, horses); }).join(' · ');
      return '<tr>' +
        '<td>' + info.race_date + '</td>' +
        '<td>' + info.venue + ' R' + info.race_number + '</td>' +
        '<td>' + (info.track || '') + ' · ' + info.distance_m + 'm · ' + info.class + '</td>' +
        '<td><b>' + (realTop3Label || '<span style="color:var(--text-dim);">—</span>') + '</b></td>' +
        '<td><span style="color:' + (x.hitTop1 ? 'var(--green)' : 'var(--text-dim)') + ';font-weight:700;">' + (x.aiTop1Label || x.aiTop1 || '—') + (x.hitTop1 ? ' ✓' : ' ✗') + '</span></td>' +
        '<td>' + (x.winOdds ? '<span style="color:var(--green);font-weight:700;">+$' + Math.round((x.winOdds - 1) * 100) + '</span>' : '<span style="color:var(--red);">-$100</span>') + '</td>' +
        '<td>' + (x.qOdds ? '<span style="color:var(--green);font-weight:700;">+$' + Math.round((x.qOdds - 1) * 50) + '</span>' : '<span style="color:var(--red);">-$50</span>') + '</td>' +
        '</tr>';
    }).join('');
  }

  function getUpcomingCounts() {
    const jockeyRides = {};
    const trainerEntries = {};
    if (DB.raceIndex && DB.raceIndex.length) {
      DB.raceIndex.forEach(function (id) {
        const r = DB.races[id];
        if (!r) return;
        const info = r.race_info || {};
        if (info.result_available) return;
        (r.horses || []).forEach(function (h) {
          if (h.jockey) jockeyRides[h.jockey] = (jockeyRides[h.jockey] || 0) + 1;
          if (h.trainer) trainerEntries[h.trainer] = (trainerEntries[h.trainer] || 0) + 1;
        });
      });
    }
    return { jockeyRides: jockeyRides, trainerEntries: trainerEntries };
  }
  function getHorseMetaMap() {
    const map = {};
    if (DB.raceIndex && DB.raceIndex.length) {
      DB.raceIndex.forEach(function (id) {
        const r = DB.races[id];
        if (!r || !r.horses) return;
        r.horses.forEach(function (h) {
          if (!h.code) return;
          map[h.code] = Object.assign({}, map[h.code] || {}, {
            trainer: h.trainer,
            rating: typeof h.rating === 'number' ? h.rating : null,
            last_3: h.last_3 || null,
            class: ((r.race_info || {}).class || null),
            draw: h.draw
          });
        });
      });
    }
    return map;
  }
  function renderJockeysTable() {
    const host = document.querySelector('#jockeysTable tbody');
    if (!host) return;
    const upcoming = getUpcomingCounts();
    const jocks = Object.entries(DB.jockeysDB || {}).map(function (entry) {
      const name = entry[0];
      const j = entry[1] || {};
      const wr = (typeof j.win_rate === 'number') ? j.win_rate : (j.starts ? (j.wins || 0) / j.starts : 0);
      const pr = (typeof j.q_rate === 'number') ? j.q_rate : (j.starts ? (j.q_count || 0) / j.starts : 0);
      const starts = j.starts || j.ride_count || 0;
      const wins = j.wins || 0;
      const places = typeof j.places === 'number' ? j.places : (j.q_count || 0);
      const form = (wr >= 0.18) ? 88 : (wr >= 0.14) ? 75 : (wr >= 0.10) ? 60 : 50;
      const upcomingN = upcoming.jockeyRides[name] || 0;
      const bestDistRaw = (typeof j.distance_win_rate === 'object' && j.distance_win_rate)
        ? Object.entries(j.distance_win_rate).sort(function (a, b) { return b[1] - a[1]; })[0] : null;
      const specialty = (wr * 100).toFixed(0) + '%勝 / ' + (pr * 100).toFixed(0) + '%入Q';
      return {
        name: name,
        starts: starts,
        wins: wins,
        places: places,
        win_rate: wr,
        place_rate: pr,
        current_form: form,
        best_dist: bestDistRaw ? (bestDistRaw[0] + ' ' + Math.round(bestDistRaw[1] * 100) + '%') : specialty,
        upcoming: upcomingN + ' 場'
      };
    }).sort(function (a, b) { return b.win_rate - a.win_rate; });
    host.innerHTML = jocks.map(function (j, i) {
      const wrPct = Math.round(j.win_rate * 100);
      const prPct = Math.round(j.place_rate * 100);
      const formCls = j.current_form >= 85 ? 'good' : (j.current_form >= 70 ? 'mid' : 'bad');
      const w = Math.min(100, wrPct * 5);
      const nameSafe = (j.name || '').replace(/'/g, "\\'");
      return '<tr>' +
        '<td><span class="rank-pill">' + (i + 1) + '</span></td>' +
        '<td><span class="jockey-click" data-name="' + nameSafe + '" style="cursor:pointer;text-decoration:underline dotted;text-underline-offset:3px;text-decoration-color:rgba(212,175,55,0.45);" onclick="event.stopPropagation();openJockeyDetail(\'' + nameSafe + '\');"><b>' + j.name + '</b></span><div style="font-size:11px;color:var(--text-dim);">今晚 ' + j.upcoming + '</div></td>' +
        '<td>' + j.starts + '</td>' +
        '<td>' + j.wins + '/' + j.places + '</td>' +
        '<td><div style="display:flex;align-items:center;gap:6px;"><div class="mini-score"><div class="fill" style="width:' + w + '%;"></div></div><b style="color:var(--gold);">' + wrPct + '%</b></div></td>' +
        '<td>' + prPct + '%</td>' +
        '<td><span class="last3"><span class="' + formCls + '">' + j.current_form + '</span></span></td>' +
        '<td>' + j.best_dist + '</td>' +
        '</tr>';
    }).join('');
  }

  function renderTrainersTable() {
    const host = document.querySelector('#trainersTable tbody');
    if (!host) return;
    const upcoming = getUpcomingCounts();
    const rows = Object.entries(DB.trainersDB || {}).map(function (entry) {
      const name = entry[0];
      const t = entry[1] || {};
      const wr = (typeof t.win_rate === 'number') ? t.win_rate : (t.starts ? (t.wins || 0) / t.starts : 0);
      const pr = (typeof t.q_rate === 'number') ? t.q_rate : (t.starts ? (t.q_count || 0) / t.starts : 0);
      const runners = t.starts || t.entry_count || 0;
      const wins = t.wins || 0;
      const places = typeof t.places === 'number' ? t.places : (t.q_count || 0);
      const recent = (wr >= 0.13) ? 85 : (wr >= 0.09) ? 72 : 58;
      const upcomingN = upcoming.trainerEntries[name] || 0;
      return {
        name: name,
        runners: runners,
        wins: wins,
        places: places,
        win_rate: wr,
        place_rate: pr,
        recent_form: recent,
        upcoming: upcomingN + ' 場'
      };
    }).sort(function (a, b) { return b.win_rate - a.win_rate; });
    host.innerHTML = rows.map(function (t, i) {
      const wrPct = Math.round(t.win_rate * 100);
      const prPct = Math.round(t.place_rate * 100);
      const cls = t.recent_form >= 80 ? 'good' : (t.recent_form >= 70 ? 'mid' : 'bad');
      const w = Math.min(100, wrPct * 5);
      return '<tr>' +
        '<td><span class="rank-pill">' + (i + 1) + '</span></td>' +
        '<td><b>' + t.name + '</b><div style="font-size:11px;color:var(--text-dim);">今晚 ' + t.upcoming + '</div></td>' +
        '<td>' + t.runners + '</td>' +
        '<td>' + t.wins + '/' + t.places + '</td>' +
        '<td><div style="display:flex;align-items:center;gap:6px;"><div class="mini-score"><div class="fill" style="width:' + w + '%;"></div></div><b style="color:var(--gold);">' + wrPct + '%</b></div></td>' +
        '<td>' + prPct + '%</td>' +
        '<td><span class="last3"><span class="' + cls + '">' + t.recent_form + '</span></span></td>' +
        '</tr>';
    }).join('');
  }

  function renderHorsesTable() {
    const host = document.querySelector('#horsesTable tbody');
    if (!host) return;
    const metaMap = getHorseMetaMap();
    const rows = Object.entries(DB.horsesDB || {}).map(function (entry) {
      const code = entry[0];
      const h = entry[1] || {};
      const meta = metaMap[code] || {};
      const rating = (typeof h.rating === 'number') ? h.rating : (typeof meta.rating === 'number' ? meta.rating : (h.rating_avg || 0));
      const change = (typeof h.rating_change === 'number') ? h.rating_change : 0;
      const starts = (typeof h.starts === 'number') ? h.starts : 0;
      const wins = (typeof h.wins === 'number') ? h.wins : 0;
      const placesCount = (typeof h.places === 'number') ? h.places : (h.q_count || 0);
      const name = h.name || meta.name || code;
      const trainer = h.trainer || meta.trainer || '—';
      const classTag = h.class || meta.class || '—';
      const last3Html = last6Badge(h);
      let lastInfo = '';
      if (h.last_run && h.last_place) lastInfo = h.last_run + ' 第' + h.last_place + '名';
      else if (h.last_place != null && h.last_place !== '') lastInfo = '近第' + h.last_place + '名';
      else lastInfo = '近期缺陣';
      const runnersUp = placesCount - wins;
      const wpRecord = wins + '冠/' + (runnersUp > 0 ? runnersUp : 0) + '亞季';
      return {
        code: code,
        name: name,
        class: classTag,
        trainer: trainer,
        starts: starts,
        record: wpRecord,
        latestRating: rating,
        trend: change,
        last3_html: last3Html,
        last_info: lastInfo
      };
    }).sort(function (a, b) { return b.latestRating - a.latestRating; });
    host.innerHTML = rows.map(function (h, i) {
      const trendTag = h.trend > 0 ? '<span style="color:var(--green);font-weight:700;">▲+' + h.trend + '</span>'
        : h.trend < 0 ? '<span style="color:var(--blue);">▼' + h.trend + '</span>'
        : '<span style="color:var(--text-dim);">→ 持平</span>';
      return '<tr>' +
        '<td><span class="rank-pill">' + (i + 1) + '</span></td>' +
        '<td><b>' + h.name + '</b><div style="font-size:11px;color:var(--text-dim);">練 ' + h.trainer + '</div></td>' +
        '<td>' + h.class + '</td>' +
        '<td>' + h.starts + '</td>' +
        '<td>' + h.record + '</td>' +
        '<td>' + h.last3_html + '</td>' +
        '<td><b>' + h.latestRating + '</b> ' + trendTag + '</td>' +
        '<td style="font-size:12px;color:var(--text-dim);">' + h.last_info + '</td>' +
        '</tr>';
    }).join('');
  }

  /* 倒計時自動刷新 */
  let countdown = 300;
  setInterval(function () {
    countdown--;
    if (countdown <= 0) { loadAll(); countdown = 300; }
    if ($('countdown')) $('countdown').textContent = countdown + 's';
  }, 1000);

  /* 啟動 */
  function boot() {
    initNav();
    bindHorseClick();
    loadAll();
    const now = new Date();
    const pad = function (n) { return n < 10 ? '0' + n : n; };
    if ($('lastUpdate')) {
      $('lastUpdate').textContent = now.getFullYear() + '/' + pad(now.getMonth() + 1) + '/' + pad(now.getDate()) + ' ' + pad(now.getHours()) + ':' + pad(now.getMinutes());
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    setTimeout(boot, 50);
  }
  window.__HorseLive = { DB: DB, RacingAI: (typeof window.RacingAI !== 'undefined' ? window.RacingAI : (typeof global !== 'undefined' ? global.RacingAI : null)),
    computeAdvancedScore: computeAdvancedScore, jockeyBonus: jockeyBonus, trainerBonus: trainerBonus,
    last3Badge: last3Badge, renderRaceBody: renderRaceBody };
  window.DB = DB;
})();
