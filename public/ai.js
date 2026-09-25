/* =========================================================
   賽馬 AI 評分引擎 v2 - 10 維度（基礎 6 + 新 4）
   基礎層權重調整：舊 6 維合共 58% (原本74%)
   新增 4 個階段一因子合共 16%：晨操7%+路程3%+騎馬默契3%+評分走勢3%
   + 騎師加成 12% + 練馬師加成 10% = 100%
   ========================================================= */
(function (global) {
    'use strict';

    // ===== 加呢段：預先加載你手動輸入嘅專家貼士 expert_notes.json =====
    let expertNotes = {};
    try {
        if (typeof fetch === 'function') {
            fetch('./data/profiles/expert_notes.json')
                .then(function (r) { return r.ok ? r.json() : {}; })
                .then(function (d) { if (d) expertNotes = d; })
                .catch(function () { expertNotes = {}; });
        }
    } catch (e) { expertNotes = {}; }

    function minMax(values, reverse) {
        if (!values || values.length === 0) return {};
        const mn = Math.min.apply(null, values);
        const mx = Math.max.apply(null, values);
        const out = {};
        values.forEach(function (v) {
            if (mn === mx) { out[v] = Number(Math.round(v * 100) / 100); return; }
            const s = reverse ? (1 - (v - mn) / (mx - mn)) : ((v - mn) / (mx - mn));
            out[v] = Math.round(s * 10000) / 100;
        });
        return out;
    }

    function analyzeLast3(last3) {
        if (!last3 || last3.length === 0) return 0;
        const weights = [0.5, 0.3, 0.2];
        let sum = 0;
        for (let i = 0; i < Math.min(last3.length, 3); i++) {
            const el = last3[i];
            let rank = 99;
            if (typeof el === 'number') {
                rank = el || 99;
            } else if (el && typeof el === 'object') {
                rank = (typeof el.finish === 'number') ? el.finish : 99;
            }
            const score = Math.max(0, 100 - (rank - 1) * 8);
            sum += score * weights[i];
        }
        return Math.round(sum * 100) / 100;
    }

    function parseTimeToSeconds(timeStr) {
        if (!timeStr || typeof timeStr !== 'string') return null;
        let s = timeStr.trim().replace(/秒|s|Sec/gi, '');
        if (!s) return null;
        const parts = s.split('.');
        try {
            if (parts.length === 3) {
                const m = parseInt(parts[0], 10) || 0;
                const sec1 = parseInt(parts[1], 10) || 0;
                const sec2 = parseFloat('0.' + parts[2]) || 0;
                return m * 60 + sec1 + sec2;
            } else if (parts.length === 2) {
                if (parseInt(parts[0], 10) >= 60) {
                    const m = Math.floor(parseInt(parts[0], 10) / 60);
                    const rs = parseInt(parts[0], 10) % 60;
                    return m * 60 + rs + (parseFloat('0.' + parts[1]) || 0);
                }
                return parseFloat(parts[0] + '.' + parts[1]) || 0;
            } else {
                return parseFloat(s) || 0;
            }
        } catch (e) { return null; }
    }

    function analyzeTrackwork(code, raceId, currentJockey, raceVenue) {
        let score = 50;
        let detail = '無操練數據';
        try {
            const tw = global.RacingAugmented && global.RacingAugmented.trackwork ? global.RacingAugmented.trackwork : (global.window && window.DB ? window.DB.trackwork : {});
            const data = tw ? tw[raceId] : null;
            if (!data || !data.loaded || !data.records || !data.records[code]) {
                return { score: 50, detail: detail, rec: null };
            }
            const list = data.records[code];
            if (!list || !list.length) return { score: 50, detail: detail, rec: null };
            let bestSecPer200 = 999;
            let mainJockeyRide = false;
            let venueMatch = false;
            let lastDate = 0;
            let splitAccel = 0;
            let hasFast = false;
            let sumSec = 0;
            let count = 0;
            list.forEach(function (r) {
                const dist = parseInt(String(r.distance || '').replace(/[^0-9]/g, ''), 10) || 0;
                const tSec = parseTimeToSeconds(r.time || '');
                if (dist > 0 && tSec) {
                    const per = tSec / (dist / 200);
                    if (per < bestSecPer200) { bestSecPer200 = per; }
                    sumSec += per;
                    count++;
                }
                const remark = (r.remark || '').toString();
                if (remark.indexOf('快操') >= 0 || remark.indexOf('跳欄') >= 0) {
                    hasFast = true;
                    const segs = remark.match(/(\d+\.\d+)/g) || [];
                    if (segs && segs.length >= 2) {
                        const nums = segs.map(function (x) { return parseFloat(x) || 99; });
                        const mid = nums.slice(1, -1);
                        const last = nums[nums.length - 1];
                        if (mid.length) {
                            const avgMid = mid.reduce(function (a, b) { return a + b; }, 0) / mid.length;
                            if (last < avgMid) splitAccel++;
                        }
                    }
                }
                const remLower = remark.toLowerCase();
                if (currentJockey && (r.jockey || '').indexOf(currentJockey) >= 0 && r.jockey !== '助手') {
                    mainJockeyRide = true;
                }
                const venue = r.track || '';
                if (raceVenue === 'HV' && venue.indexOf('跑馬地') >= 0) venueMatch = true;
                if (raceVenue === 'ST' && venue.indexOf('沙田') >= 0) venueMatch = true;
                if (r.date) {
                    const dt = new Date(String(r.date).replace(/-/g, '/'));
                    const dn = dt.getTime();
                    if (dn > lastDate) lastDate = dn;
                }
            });
            const avgSec = count ? sumSec / count : 99;
            let speedScore = 50;
            if (bestSecPer200 < 900) {
                if (bestSecPer200 <= 12.5) speedScore = 100;
                else if (bestSecPer200 <= 13.0) speedScore = 90;
                else if (bestSecPer200 <= 13.5) speedScore = 78;
                else if (bestSecPer200 <= 14.0) speedScore = 65;
                else if (bestSecPer200 <= 15.0) speedScore = 55;
                else speedScore = 45;
            }
            score = speedScore;
            const boosts = [];
            if (hasFast) { score += 8; boosts.push('快操'); }
            if (mainJockeyRide) { score += 12; boosts.push('主騎親操'); }
            if (venueMatch) { score += 10; boosts.push('場地合拍'); }
            if (splitAccel > 0) { score += Math.min(8, splitAccel * 4); boosts.push('尾段留力'); }
            const daysAgo = lastDate ? Math.floor((Date.now() - lastDate) / 86400000) : 30;
            if (daysAgo <= 2) { score += 10; boosts.push('新鮮操'); }
            else if (daysAgo <= 5) { score += 5; boosts.push('近期操'); }
            else if (daysAgo >= 14) { score -= 10; }
            score = Math.max(0, Math.min(100, score));
            if (boosts.length) detail = boosts.join(' + ') + '，平均每200m ' + (avgSec < 900 ? avgSec.toFixed(1) + 's' : '—');
            else detail = (hasFast ? '快操紀錄' : '一般操練') + '，每200m ' + (avgSec < 900 ? avgSec.toFixed(1) + 's' : '—');
            const best = list[0];
            return { score: score, detail: detail, rec: best, best_per_200m: bestSecPer200 < 900 ? Number(bestSecPer200.toFixed(2)) : null, days_ago: daysAgo };
        } catch (e) {
            return { score: 50, detail: 'Error' };
        }
    }

    function analyzeDistanceSpecialty(code, raceDistance, raceVenue) {
        const hd = global.RacingAugmented && global.RacingAugmented.horseDistance ? global.RacingAugmented.horseDistance : (global.window && window.DB ? window.DB.horseDistanceStats : {});
        const cls = global.RacingAugmented && global.RacingAugmented.classStats ? global.RacingAugmented.classStats : (global.window && window.DB ? window.DB.classStats : {});
        let score = 50;
        let detail = '新馬或首次出戰此路程';
        const win = 0, place = 0, starts = 0;
        const candidates = [raceDistance, raceDistance - 100, raceDistance + 100, raceDistance - 200, raceDistance + 200];
        let bestWR = -1;
        let bestStarts = 0;
        let bestVenueMatch = 0;
        candidates.forEach(function (cd) {
            const k = code + '|' + cd;
            const d = hd ? hd[k] : null;
            if (d && d.starts > bestStarts) { bestStarts = d.starts; }
            if (d && d.win_rate > bestWR) { bestWR = d.win_rate; }
            if (d && d.venueMatches) bestVenueMatch = Math.max(bestVenueMatch, d.venueMatches);
        });
        let clsOK = null;
        if (cls) {
            Object.keys(cls).forEach(function (k) {
                const parts = k.split('|');
                if (parts[0] !== code) return;
                const s = cls[k];
                if (s.starts >= 2 && s.win_rate > bestWR) { bestWR = s.win_rate; bestStarts = Math.max(bestStarts, s.starts); }
            });
        }
        if (bestWR >= 0) {
            if (bestWR >= 0.50 && bestStarts >= 2) { score = 100; detail = '專長路程 (' + bestStarts + '戰勝出率' + Math.round(bestWR * 100) + '%)'; }
            else if (bestWR >= 0.33 && bestStarts >= 2) { score = 85; detail = '此路程優勢 (' + bestStarts + '戰 ' + Math.round(bestWR * 100) + '%勝)'; }
            else if (bestWR >= 0.20 && bestStarts >= 3) { score = 72; detail = '路程慣性 (' + bestStarts + '戰 ' + Math.round(bestWR * 100) + '%勝)'; }
            else if (bestStarts >= 4) { score = 58; detail = '路程有經驗 (' + bestStarts + '戰)'; }
            else if (bestStarts >= 1) { score = 52; detail = '路程見過'; }
            else { score = 48; detail = '路程新嘗試'; }
        }
        if (bestVenueMatch > 0) {
            score = Math.min(100, score + bestVenueMatch * 3);
            detail += ' · ' + bestVenueMatch + '次同場地';
        }
        return { score: Math.max(0, Math.min(100, Math.round(score))), detail: detail, win_rate: bestWR < 0 ? 0 : Number(bestWR.toFixed(3)), starts: bestStarts };
    }

    function analyzeJockeyHorseSynergy(code, jockeyName) {
        const jh = global.RacingAugmented && global.RacingAugmented.jockeyHorse ? global.RacingAugmented.jockeyHorse : (global.window && window.DB ? window.DB.jockeyHorseStats : {});
        const jocks = global.RacingAugmented && global.RacingAugmented.jockeys ? global.RacingAugmented.jockeys : (global.window && window.DB ? window.DB.jockeysDB : {});
        let score = 50;
        let detail = '騎馬新配合';
        const rides = 0, wins = 0, places = 0;
        let bestRank = 99, avgRank = 99;
        if (jockeyName) {
            const k = jockeyName + '|' + code;
            const j = jh ? jh[k] : null;
            if (j && j.rides > 0) {
                const wr = j.win_rate || 0;
                const pr = j.place_rate || 0;
                if (j.rides >= 3 && wr >= 0.40) { score = 100; detail = '黃金組合 (' + j.rides + '戰勝出率' + Math.round(wr * 100) + '%)'; }
                else if (j.rides >= 3 && wr >= 0.25) { score = 85; detail = '合拍 (' + j.rides + '戰 ' + Math.round(wr * 100) + '%勝)'; }
                else if (j.rides >= 2 && pr >= 0.50) { score = 70; detail = '穩定入Q (' + j.rides + '戰 ' + Math.round(pr * 100) + '%入Q)'; }
                else if (j.rides >= 1) { score = 58; detail = '騎過 ' + j.rides + ' 次 (最佳第' + j.bestRank + ')'; }
                bestRank = j.bestRank || 99;
                avgRank = j.avg_rank || 99;
            } else {
                const jData = jocks ? jocks[jockeyName] : null;
                if (jData) {
                    const wr = typeof jData.win_rate === 'number' ? jData.win_rate : 0;
                    if (wr < 0.10) {
                        score = 40;
                        detail = '新配合 + 騎師勝率偏低 (' + Math.round(wr * 100) + '%)';
                    } else {
                        score = 55;
                        detail = '新配合（騎師整體勝率 ' + Math.round(wr * 100) + '%）';
                    }
                }
            }
        }
        return { score: Math.max(0, Math.min(100, Math.round(score))), detail: detail, best_rank: bestRank, avg_rank: avgRank };
    }

    function analyzeRatingTrend(code, rating, currentClass, profileData) {
        const horsesDB = global.RacingAugmented && global.RacingAugmented.horses ? global.RacingAugmented.horses : (global.window && window.DB ? window.DB.horsesDB : {});
        const clsDB = global.RacingAugmented && global.RacingAugmented.classStats ? global.RacingAugmented.classStats : (global.window && window.DB ? window.DB.classStats : {});
        const p = (profileData && profileData.code === code) ? profileData : (horsesDB ? horsesDB[code] : null);
        let score = 55;
        let detail = '評分平穩';
        const trend3 = 0;
        let classChange = 0;
        if (p) {
            const rc = typeof p.rating_change === 'number' ? p.rating_change : 0;
            const lp = typeof p.last_place === 'number' ? p.last_place : 99;
            const last3Arr = p.last_3 || [];
            const last3Score = last3Arr.reduce(function (s, x) { const sc = typeof x === 'number' ? Math.max(0, 100 - (x - 1) * 8) : 0; return s + sc; }, 0) / Math.max(1, last3Arr.length);
            let delta = 0;
            delta += rc * 5;
            if (rc >= 3) { detail = '評分持續上升 +' + rc + '分'; }
            else if (rc <= -3) { detail = '評分下滑 ' + rc + '分'; }
            delta += (last3Score - 50) * 0.25;
            score = 55 + delta;
        }
        if (currentClass && clsDB) {
            let startsInClass = 0;
            let wrInClass = 0;
            let bestInClass = 99;
            Object.keys(clsDB).forEach(function (k) {
                const parts = k.split('|');
                if (parts[0] !== code || parts[1] !== currentClass) return;
                const s = clsDB[k];
                if (s.starts > startsInClass) startsInClass = s.starts;
                if (s.win_rate > wrInClass) wrInClass = s.win_rate;
                if (s.bestFinish < bestInClass) bestInClass = s.bestFinish;
            });
            if (startsInClass >= 3) {
                if (wrInClass >= 0.25) { score = Math.min(100, score + 20); detail += ' · 同班戰績佳 (' + startsInClass + '戰 ' + Math.round(wrInClass * 100) + '%勝)'; }
                else if (wrInClass >= 0.10) { score = Math.min(100, score + 10); detail += ' · 同班有經驗 (' + startsInClass + '戰)'; }
                else if (startsInClass >= 4) { score -= 5; detail += ' · 同班潛力待發掘'; }
            }
        }
        score = Math.max(0, Math.min(100, Math.round(score)));
        return { score: score, detail: detail, class_change: classChange };
    }

    function analyzePace(raceInfo, horses) {
        const distance = raceInfo.distance_m || 1000;
        let paceType = '中步速';
        if (distance <= 1200) paceType = '快步速';
        const leaders = horses.map(function (h) {
            let s = 0;
            const draw = h.draw || 0;
            if (draw && draw <= 3) s += 40;
            const last3 = h.last_3 || [];
            if (last3[0] && last3[0] <= 3) s += 30;
            if (last3[1] && last3[1] <= 3) s += 20;
            const bt = h.best_time_sec || 999;
            if (bt <= 58.0) s += 10;
            return { number: h.number, code: h.code, name: h.name || '', score: s, draw: draw };
        });
        leaders.sort(function (a, b) { return b.score - a.score; });
        const frontLeaders = leaders.filter(function (x) { return x.score >= 60; }).slice(0, 3);
        const beneficiaries = horses.map(function (h) {
            let s = 0;
            const draw = h.draw || 0;
            if (draw >= 3 && draw <= 5) s += 40;
            const bt = h.best_time_sec || 999;
            if (bt <= 58.0) s += 30;
            const rating = h.rating || 0;
            if (rating >= 128) s += 20;
            return { number: h.number, code: h.code, name: h.name || '', score: s };
        }).filter(function (x) { return x.score >= 50; });
        beneficiaries.sort(function (a, b) { return b.score - a.score; });
        return {
            pace_type: paceType,
            pace_reason: distance + '米短途賽，' + frontLeaders.length + '匹前列馬爭放頭，預計步速偏急',
            front_leaders: frontLeaders,
            beneficiaries: beneficiaries
        };
    }

    function coreAdvantage(h, raceInfo) {
        const reasons = [];
        const sc = h.scores || {};
        const last3 = h.last_3 || [];
        function l3Finish(r) {
            if (typeof r === 'number') return r || 99;
            if (r && typeof r === 'object' && typeof r.finish === 'number') return r.finish;
            return 99;
        }
        const fins = last3.map(l3Finish).filter(function (x) { return x <= 20; });
        const good = fins.reduce(function (n, r) { return n + (r <= 3 ? 1 : 0); }, 0);
        const bestFin = fins.length ? Math.min.apply(null, fins) : 99;
        if (good === 3 && fins.length === 3) reasons.push('近3仗全入三甲，走勢穩步上揚');
        else if (good >= 2) reasons.push('近況 ' + good + ' 次入Q，保持上遊水準');
        else if (bestFin <= 2) reasons.push('早前曾跑第' + bestFin + '，具備爭標質素');
        else if (fins.length) reasons.push('近期走勢平穩，若步速配合可爆冷');
        const draw = h.draw || 0;
        const venue = (raceInfo && raceInfo.venue) ? raceInfo.venue : '';
        const track = (raceInfo && raceInfo.track) ? raceInfo.track : '';
        const dist = (raceInfo && raceInfo.distance_m) ? raceInfo.distance_m : 0;
        const vName = venue === 'HV' ? '跑馬地' : (venue === 'ST' ? '沙田' : '當前場地');
        if (draw <= 2 && dist <= 1200) reasons.push('短途 ' + draw + ' 檔內檔起步，唔會捱捲');
        else if (draw <= 4) reasons.push(vName + (track ? ' ' + track : '') + ' ' + draw + ' 檔內檔佔地利');
        else if (draw >= 3 && draw <= 6) reasons.push(draw + ' 檔中檔進退皆宜，跟車靈活');
        else if (draw >= 9 && dist >= 1650) reasons.push('長途 ' + draw + ' 檔外檔避擠塞，有機會留後上前');
        const rating = h.rating || 0;
        if (rating >= 130) reasons.push('評分 ' + rating + ' 分，班底超班有力衛冕');
        else if (rating >= 118) reasons.push('評分 ' + rating + ' 分，屬班中上遊份子');
        const jockey = h.jockey ? h.jockey.replace(/\s/g, '') : '';
        if (sc.synergy && sc.synergy >= 85) reasons.push('騎師 ' + jockey + ' 黃金組合，默契極佳');
        else if (sc.synergy && sc.synergy >= 70) reasons.push('騎師 ' + jockey + ' 長期合作合拍');
        else if (jockey) reasons.push('騎師 ' + jockey + ' 掌舵形勢穩陣');
        if (sc.distance && sc.distance >= 85) reasons.push('呢個路程專家級，贏面極高');
        else if (sc.distance && sc.distance >= 70) reasons.push(dist + 'm 路程慣性勝出，跟車有力');
        if (sc.trackwork && sc.trackwork >= 85) reasons.push('晨操狀態超班，臨場有料到');
        else if (sc.trackwork && sc.trackwork >= 72) reasons.push('晨操態度認真，體能準備充足');
        if (typeof h.cc_expert_count === 'number' && h.cc_expert_count >= 3) reasons.push('🔥 東方 ' + h.cc_expert_count + ' 位名家一致推介');
        const odds = h.odds_win || 1;
        if (odds >= 8 && odds <= 20 && (sc.total || 0) >= 62) reasons.push('市場低估 (' + odds + 'x)，冷馬值博率高');
        const total = sc.total || 0;
        if (total >= 78) reasons.push('AI 總分 ' + total.toFixed(1) + ' 分頂尖級');
        else if (total >= 68) reasons.push('AI 總分 ' + total.toFixed(1)  + ' 分高質上遊');
        if (reasons.length === 0) reasons.push('整體條件均衡，步速合適有機會');
        return reasons.slice(0, 3).join('，');
    }

    function detailedAiBreakdown(h, raceInfo) {
        const sc = h.scores || {};
        const aug = h.aug || {};
        const last3 = h.last_3 || [];
        function l3Finish(r) {
            if (typeof r === 'number') return r || 99;
            if (r && typeof r === 'object' && typeof r.finish === 'number') return r.finish;
            return 99;
        }
        const fins = last3.map(l3Finish).filter(function (x) { return x <= 20; });
        const number = h.number || h.horse_number || '';
        const name = h.name || h.horse_name || '（馬名待補）';
        const total = sc.total || 0;
        const tier = total >= 78 ? '頂尖級' : (total >= 68 ? '高質上遊' : (total >= 58 ? '中上游力爭上游' : (total >= 48 ? '條件均衡若步速配合可爭' : '冷門潛力')));
        const odds = h.odds_win || 0;
        const isCold = odds >= 8 && odds <= 20 && total >= 58;

        const lines = [];
        lines.push('<b style="color:var(--gold);font-size:13px;">📌 我分析咗 #' + number + ' ' + name + ' 嘅 13 維度之後，綜合評級屬「' + tier + '」，AI 總分 ' + total.toFixed(1) + ' 分。</b>');

        if (fins.length) {
            const good = fins.filter(function (r) { return r <= 3; }).length;
            const bestFin = Math.min.apply(null, fins);
            let comment = '';
            if (fins.length === 3 && good === 3) comment = '近況持續升溫，3仗全入三甲，狀態穩定得嚟有進步空間，今場再跑入Q 機會極高。';
            else if (good >= 2) comment = '近況 ' + good + ' 次入Q，保持上遊水準，步速跟住嘅話有力再衝前。';
            else if (bestFin <= 2) comment = '早前曾跑第 ' + bestFin + ' 名，證明佢有爭標質素，今場復甦機會唔細。';
            else comment = '近期走勢平穩中游，若步速有利隨時爆冷上名。';
            lines.push('🏇 <b>近3仗走勢：</b>' + fins.join(' → ') + ' → ' + comment);
        } else {
            lines.push('🏇 <b>近3仗走勢：</b>數據待補，用同班評分 + 路程適性間接分析。');
        }

        const venue = (raceInfo && raceInfo.venue) ? (raceInfo.venue === 'HV' ? '跑馬地' : '沙田') : '';
        const track = (raceInfo && raceInfo.track) ? raceInfo.track : '';
        const dist = (raceInfo && raceInfo.distance_m) || 0;
        const raceClass = (raceInfo && raceInfo.class) || '';
        const vt = venue + (track ? ' · ' + track : '') + (dist ? ' · ' + dist + 'm' : '') + (raceClass ? ' / ' + raceClass : '');
        if (vt) {
            const vScore = sc.venue || 50;
            let vComment = '場地評分 ' + vScore.toFixed(0) + ' 分，屬中性。';
            if (vScore >= 75) vComment = '呢個場地班次組合累積表現理想，路程適性極高，隨時有加成。';
            else if (vScore >= 62) vComment = '呢個場地班次經驗充足，路程適性唔錯，預計發揮穩定。';
            lines.push('🏟️ <b>場地班次路程：</b>' + vt + ' → ' + vComment);
        }

        const draw = h.draw || 0;
        if (draw) {
            let dComment = '';
            if (draw <= 2 && dist <= 1200) dComment = '短途 ' + draw + ' 檔內檔起步，貼欄慳腳程，只要步速唔太慢就有極大優勢。';
            else if (draw <= 4) dComment = draw + ' 檔內檔位置，' + venue + ' ' + track + ' 跑道呢個檔一向食位，跟車入閘有利。';
            else if (draw >= 3 && draw <= 6) dComment = draw + ' 檔中檔進退皆宜，騎師靈活控制步速同跟車位置都唔會有大問題。';
            else if (draw >= 9 && dist >= 1650) dComment = '長途 ' + draw + ' 檔外檔起步，反而避開內檔大擠塞，留後上前嘅跑法隨時有驚喜。';
            else dComment = draw + ' 檔位置視乎步速，若步速開得適中就跟車冇問題。';
            lines.push('🚦 <b>檔位分析：</b>' + draw + ' 檔 → ' + dComment);
        }

        const jockey = h.jockey ? h.jockey.replace(/\s/g, '') : '';
        const trainer = h.trainer ? h.trainer.replace(/\s/g, '') : '';
        const jb = sc.jockey_bonus || 0;
        const tb = sc.trainer_bonus || 0;
        const syn = sc.synergy || 0;
        if (jockey || trainer) {
            let com = '';
            if (syn >= 85) com = '騎師 ' + jockey + ' 同呢隻馬長期合作，默契極佳（' + syn.toFixed(0) + ' 分），騎師加成 ' + jb.toFixed(1) + ' 分 + 練馬師 ' + trainer + ' 加成 ' + tb.toFixed(1) + ' 分，三者配合係今場嘅強項。';
            else if (syn >= 70) com = '騎師 ' + jockey + ' 同呢隻馬默契唔錯（' + syn.toFixed(0) + ' 分），加上練馬師 ' + trainer + ' 佈陣穩陣，騎練加成整體合理。';
            else com = '騎師 ' + jockey + ' 掌舵（加成 ' + jb.toFixed(1) + ' 分）、練馬師 ' + trainer + '（加成 ' + tb.toFixed(1) + ' 分），騎練組合屬穩打穩陣派。';
            lines.push('🎖️ <b>騎師 + 練馬師：</b>' + com);
        }

        const rating = h.rating || '—';
        const weight = h.weight || '—';
        const bt = h.best_time_sec || 0;
        const timeScore = sc.time || 50;
        {
            let com = '';
            const rNum = typeof rating === 'number' ? rating : 0;
            if (rNum >= 120) com = '評分 ' + rNum + ' 分屬班中頂尖，體重 ' + weight + ' 磅負荷合理。';
            else if (rNum >= 105) com = '評分 ' + rNum + ' 分班底夠硬淨，體重 ' + weight + ' 磅屬正常範圍，壯態冇大問題。';
            else if (typeof rating === 'number') com = '評分 ' + rNum + ' 分偏低，但體重 ' + weight + ' 磅唔重，若步速配合有機會超值。';
            else com = '評分 ' + rating + ' 分（待補），體重 ' + weight + ' 磅。';
            if (bt > 0) {
                if (timeScore >= 75) com += '同路程最佳時間 ' + bt.toFixed(2) + ' 秒（步速特強 ' + timeScore.toFixed(0) + ' 分），一旦步速開得就即時發揮。';
                else if (timeScore >= 60) com += '同路程最佳時間 ' + bt.toFixed(2) + ' 秒（步速中上 ' + timeScore.toFixed(0) + ' 分），後段有力上前。';
                else com += '同路程最佳時間 ' + bt.toFixed(2) + ' 秒，步速屬中性。';
            }
            lines.push('💪 <b>壯態 + 步速：</b>' + com);
        }

        const augLines = [];
        const twScore = sc.trackwork || 50;
        if (h.cc_trackwork_summary) augLines.push('🌅 晨操摘要：' + String(h.cc_trackwork_summary).slice(0, 100) + '（評分 ' + twScore.toFixed(0) + ' 分）');
        else if (aug.trackwork && aug.trackwork.detail) augLines.push('🌅 晨操：' + aug.trackwork.detail + '（評分 ' + twScore.toFixed(0) + ' 分）');
        else augLines.push('🌅 晨操：暫無詳細數據（評分 ' + twScore.toFixed(0) + ' 分，屬中性）');
        // === Step I 新增 5 項補充分析文字 ===
        const fSc = typeof sc.form === 'number' ? sc.form : 50;
        if (aug.form_detail && (aug.form_detail.note || aug.form_detail.trend || fSc)) {
            const fl = aug.form_detail.flags || [];
            const t = aug.form_detail.trend;
            const tm = t === 1 ? '（上升走勢📈）' : (t === -1 ? '（回落走勢📉）' : '（平穩）');
            augLines.push('🎯 近績形勢：' + fSc.toFixed(0) + ' 分' + tm + (aug.form_detail.note ? ' · ' + String(aug.form_detail.note).slice(0, 70) : ''));
        } else {
            augLines.push('🎯 近績形勢：暫無 formline 數據（中性 50 分）');
        }
        const xSc = typeof sc.except === 'number' ? sc.except : 80;
        if (aug.except_detail && (aug.except_detail.flags && aug.except_detail.flags.length || aug.except_detail.note)) {
            const fl = Array.isArray(aug.except_detail.flags) ? aug.except_detail.flags : [];
            augLines.push('⚠️ 異常因素：' + xSc.toFixed(0) + ' 分' + (fl.length ? '（' + fl.join('、') + '）' : '（異常較少）') + (aug.except_detail.note ? ' · ' + String(aug.except_detail.note).slice(0, 60) : ''));
        } else {
            augLines.push('⚠️ 異常因素：' + xSc.toFixed(0) + ' 分（無明顯異常）');
        }
        const vSc = typeof sc.vet === 'number' ? sc.vet : 90;
        if (aug.vet_detail && (aug.vet_detail.flags && aug.vet_detail.flags.length || aug.vet_detail.note)) {
            const fl = Array.isArray(aug.vet_detail.flags) ? aug.vet_detail.flags : [];
            augLines.push('🏥 獸醫狀態：' + vSc.toFixed(0) + ' 分' + (fl.length ? '（' + fl.join('、') + '）' : '（健康合格）') + (aug.vet_detail.note ? ' · ' + String(aug.vet_detail.note).slice(0, 60) : ''));
        } else {
            augLines.push('🏥 獸醫狀態：' + vSc.toFixed(0) + ' 分（無傷患記錄，假設合格）');
        }
        if (aug.report_detail && (aug.report_detail.last_run_rank || aug.report_detail.note)) {
            const n = aug.report_detail.last_run_rank;
            const s = n ? ('上仗名次 第' + n + '名') : '上仗名次待補';
            augLines.push('📋 賽事報告：' + s + (aug.report_detail.note ? ' · ' + String(aug.report_detail.note).slice(0, 80) : ''));
        }
        const dScore = sc.distance || 50;
        if (aug.distance && aug.distance.detail) augLines.push('🛣️ 路程適性：' + aug.distance.detail + '（評分 ' + dScore.toFixed(0) + ' 分）');
        else augLines.push('🛣️ 路程適性：評分 ' + dScore.toFixed(0) + ' 分' + (dScore >= 70 ? '，路程專家級，今場有利。' : (dScore >= 60 ? '，路程適性中上。' : '，路程適性中性，若步速合適有機會。')));
        if (aug.synergy && aug.synergy.detail) augLines.push('🤝 騎馬默契：' + aug.synergy.detail + '（評分 ' + syn.toFixed(0) + ' 分）');
        const tScore = sc.trend || 50;
        if (aug.trend && aug.trend.detail) augLines.push('📈 同班走勢：' + aug.trend.detail + '（評分 ' + tScore.toFixed(0) + ' 分）');
        else augLines.push('📈 同班走勢：評分 ' + tScore.toFixed(0) + ' 分' + (tScore >= 70 ? '，近同班表現持續進步。' : (tScore >= 58 ? '，同班走勢平穩。' : '，同班走勢需要步速配合先有發揮。')));
        lines.push('🔎 <b>情報深入分析：</b>' + augLines.join('<br>　　'));

        if (typeof h.cc_expert_count === 'number' && h.cc_expert_count > 0) {
            const exps = Array.isArray(h.cc_experts) ? h.cc_experts.filter(Boolean).join('、') : '';
            lines.push('🔥 <b>東方馬經外部情報：</b>一共有 ' + h.cc_expert_count + ' 位名家最後來料推介' + (exps ? '（名單：' + exps + '）' : '') + '，外部情報同 AI 評分方向一致，信心再加。');
        }
        const gRaceDateKey = (raceInfo && raceInfo.race_date) ? String(raceInfo.race_date).replace(/\//g, '-') : '';
        const gVenueKey = (raceInfo && raceInfo.venue) ? raceInfo.venue : '';
        const gTrackKey = gVenueKey ? (gVenueKey + '_草地') : '';
        if (gRaceDateKey && expertNotes.global_tips && expertNotes.global_tips[gRaceDateKey + '_' + gVenueKey]) {
            lines.push('🧠 <b>賽馬日重點提示：</b>' + expertNotes.global_tips[gRaceDateKey + '_' + gVenueKey]);
        } else if (gRaceDateKey && expertNotes.global_tips && expertNotes.global_tips[gRaceDateKey]) {
            lines.push('🧠 <b>賽馬日重點提示：</b>' + expertNotes.global_tips[gRaceDateKey]);
        } else if (expertNotes.global_tips && expertNotes.global_tips.default) {
            lines.push('🧠 <b>今場通用提示：</b>' + expertNotes.global_tips.default);
        }
        if (gTrackKey && expertNotes.track_bias && expertNotes.track_bias[gTrackKey]) {
            lines.push('🏟️ <b>場地偏差情報：</b>' + expertNotes.track_bias[gTrackKey]);
        } else if (expertNotes.track_bias && gVenueKey && expertNotes.track_bias[gVenueKey]) {
            lines.push('🏟️ <b>場地偏差情報：</b>' + expertNotes.track_bias[gVenueKey]);
        }
        if (jockey && expertNotes.jockey_notes && expertNotes.jockey_notes[jockey]) {
            lines.push('👤 <b>騎師情報：</b>' + expertNotes.jockey_notes[jockey]);
        }
        if (trainer && expertNotes.trainer_notes && expertNotes.trainer_notes[trainer]) {
            lines.push('🏋️ <b>練馬師情報：</b>' + expertNotes.trainer_notes[trainer]);
        }
        if (odds) {
            if (isCold) lines.push('🎯 <b>值博率評估：</b>現時獨贏賠率 ' + odds + 'x，市場明顯低估咗 AI 總分 ' + total.toFixed(1) + ' 分嘅質素，屬 8~20 倍冷馬值博區，值得投注。');
            else if (odds < 4) lines.push('🎯 <b>值博率評估：</b>現時 ' + odds + 'x 大熱門，市場同 AI 評分方向一致，雖然值博率唔高但勝在穩陣。');
            else lines.push('🎯 <b>值博率評估：</b>現時 ' + odds + 'x 屬中賠區，AI 評分 ' + total.toFixed(1) + ' 分反映實力有數得計。');
        }

        lines.push('✅ <b>總結：</b>AI 綜合考慮晒以上全部因素，最後俾 #' + number + ' ' + name + ' 嘅總評分係 <b style="color:var(--gold);">' + total.toFixed(1) + ' 分</b>，歸類為「' + tier + '」級。');
        return lines.join('<br>');
    }

    function scoreHorses(horses, raceInfo) {
        const raceId = raceInfo ? (raceInfo.race_id || '') : '';
        const raceVenue = raceInfo ? (raceInfo.venue || '') : '';
        const raceDist = raceInfo ? (raceInfo.distance_m || 0) : 0;
        const raceClass = raceInfo ? (raceInfo.class || '') : '';
        const horsesDB = global.RacingAugmented && global.RacingAugmented.horses ? global.RacingAugmented.horses : (global.window && window.DB ? window.DB.horsesDB : {});
        const horsesSafe = (horses || []).map(function (h) {
            if (!h) return h;
            if (h.odds_win == null || typeof h.odds_win !== 'number' || !isFinite(h.odds_win) || h.odds_win <= 0) {
                h.odds_win = 999;
            }
            if (h.odds_place == null || typeof h.odds_place !== 'number' || !isFinite(h.odds_place) || h.odds_place <= 0) {
                h.odds_place = 999;
            }
            if (!h.code) {
                h.code = '_X' + (h.number || Math.floor(Math.random() * 9000 + 1000));
            }
            if (typeof h.rating !== 'number' || !isFinite(h.rating)) h.rating = 30;
            if (typeof h.best_time_sec !== 'number' || !isFinite(h.best_time_sec) || h.best_time_sec <= 0) h.best_time_sec = 999;
            if (typeof h.draw !== 'number' || !isFinite(h.draw) || h.draw <= 0) h.draw = 100;
            if (typeof h.weight !== 'number' || !isFinite(h.weight) || h.weight <= 0) h.weight = 127;
            return h;
        });
        const last3Scores = horsesSafe.map(function (h) { return analyzeLast3(h.last_3); });
        const ratings = horsesSafe.map(function (h) { return h.rating || 0; });
        const bestTimes = horsesSafe.map(function (h) { return h.best_time_sec || 999; });
        const draws = horsesSafe.map(function (h) { return h.draw || 100; });
        const weights = horsesSafe.map(function (h) { return h.weight || 0; });
        const oddsList = horsesSafe.map(function (h) { return h.odds_win || 999; });
        const twRaw = horsesSafe.map(function (h) { return analyzeTrackwork(h.code, raceId, h.jockey, raceVenue); });
        const twScores = twRaw.map(function (x) { return x.score; });
        const distRaw = horsesSafe.map(function (h) { return analyzeDistanceSpecialty(h.code, raceDist, raceVenue); });
        const distScores = distRaw.map(function (x) { return x.score; });
        const synRaw = horsesSafe.map(function (h) { return analyzeJockeyHorseSynergy(h.code, h.jockey); });
        const synScores = synRaw.map(function (x) { return x.score; });
        const trendRaw = horsesSafe.map(function (h) { return analyzeRatingTrend(h.code, h.rating, raceClass, horsesDB ? horsesDB[h.code] : null); });
        const trendScores = trendRaw.map(function (x) { return x.score; });

        // === NEW Step I fetch 5 項補充分數 (15 維度升級) ===
        //   h.trackwork_score / h.form_score / h.except_score / h.vet_score 全部 0..100
        //   若冇 (舊 JSON) → fallback twScores[] 同 50 中位數
        function sNum0(v, fallback) { const n = typeof v === 'number' && isFinite(v) ? v : NaN; return (Number.isFinite(n) && n >= 0 && n <= 100) ? n : (Number.isFinite(fallback) ? fallback : 50); }
        const formScores = horsesSafe.map(function (h) { return sNum0(h.form_score, 50); });
        const exceptScores = horsesSafe.map(function (h) { return sNum0(h.except_score, 80); }); // 冇異常=80 分（除了 parser 唔 work 嗰陣 fallback）
        const vetScores = horsesSafe.map(function (h) { return sNum0(h.vet_score, 90); }); // 冇 vet info → 假設健康 90
        const twHorsesheetScores = horsesSafe.map(function (h) { return sNum0(h.trackwork_score, null); }); // null → 用返 analyzeTrackwork 真實分數
        const twFinal = horsesSafe.map(function (_h, i) {
            const a = twScores[i] || 0; const b = twHorsesheetScores[i];
            if (b === null || !Number.isFinite(b)) return a;
            return (a * 0.45 + b * 0.55); // 馬匹晨操紙比分量更重
        });

        const ratingMap = minMax(ratings);
        const _btCandidates = bestTimes.filter(function (t) { return Number.isFinite(t) && t > 0 && t < 900; });
        const _btNeutral = _btCandidates.length ? _btCandidates.slice().sort(function (a, b) { return a - b; })[Math.max(0, Math.floor(_btCandidates.length / 2))] : 90;
        const bestTimesNeutral = bestTimes.map(function (t) { return Number.isFinite(t) && t > 0 && t < 900 ? t : _btNeutral; });
        const timeMap = minMax(bestTimesNeutral, true);
        const drawMap = minMax(draws, true);
        const weightMap = minMax(weights);
        const _oddsCandidates = oddsList.filter(function (o) { return Number.isFinite(o) && o > 0 && o < 900; });
        const _invOddsNeutral = _oddsCandidates.length ? (function () {
            const arr = _oddsCandidates.map(function (o) { return 100 / (o > 0 ? o : 1); }).sort(function (a, b) { return a - b; });
            return arr[Math.max(0, Math.floor(arr.length / 2))];
        })() : 4;
        const invOdds = oddsList.map(function (o) { return (Number.isFinite(o) && o > 0 && o < 900) ? (100 / o) : _invOddsNeutral; });
        const oddsMap = minMax(invOdds);

        const scored = horsesSafe.map(function (h, idx) {
            const sLast3 = last3Scores[idx];
            const sRating = ratingMap[h.rating] || 0;
            const _bt = (Number.isFinite(h.best_time_sec) && h.best_time_sec > 0 && h.best_time_sec < 900) ? h.best_time_sec : _btNeutral;
            const sTime = timeMap[_bt] || 0;
            const sDraw = drawMap[h.draw] || 0;
            const sWeight = weightMap[h.weight] || 0;
            const _invO = (Number.isFinite(h.odds_win) && h.odds_win > 0 && h.odds_win < 900) ? (100 / h.odds_win) : _invOddsNeutral;
            const sOdds = oddsMap[_invO] || 0;
            const sTW = twFinal[idx] || 0;
            const sDist = distScores[idx] || 0;
            const sSyn = synScores[idx] || 0;
            const sTrend = trendScores[idx] || 0;
            // 新增 Step I 5 項補充分數 0..100 → minMax 去全距
            const formAll = (formScores[idx] || 50) / 100 * 100;
            const exceptAll = (exceptScores[idx] || 50) / 100 * 100;
            const vetAll = (vetScores[idx] || 50) / 100 * 100;
            const sForm = formAll;
            const sExcept = exceptAll;
            const sVet = vetAll;
            // ==== Base 6 (58%) ← 不變 (近績30%/評分20%/步速15%/檔15%/體重10%/賠率10%)
            const base6 = sLast3 * 0.30 + sRating * 0.20 + sTime * 0.15 + sDraw * 0.15 + sWeight * 0.10 + sOdds * 0.10;
            // ==== Augment 42% = baseAug + newInfo
            //   舊 Aug 原來 16% (0.07+0.03+0.03+0.03) → 壓縮到 10%；餘下 32% 俾新補充 5 項
            //   晨操 12% (tw 新) + 形勢 form 10% + 異常 except 10% + 獸醫 vet 8% + distance/synergy/trend 壓縮後 4%
            const baseAug = sTW * 0.12 + sForm * 0.10 + sExcept * 0.10 + sVet * 0.08 + sDist * 0.03 + sSyn * 0.03 + sTrend * 0.03;
            // 加權總和 = base6 * 0.54 + aug * 0.46 = 1.00
            const baseTotal = base6 * 0.54 + baseAug;
            const total = Math.round(baseTotal * 100) / 100;
            return {
                number: h.number,
                code: h.code,
                name: h.name || '',
                jockey: h.jockey || '',
                trainer: h.trainer || '',
                draw: h.draw,
                rating: h.rating,
                weight: h.weight,
                last_3: h.last_3 || [],
                best_time_sec: h.best_time_sec,
                odds_win: h.odds_win,
                odds_place: h.odds_place,
                third_party_refs: h.third_party_refs,
                finish: typeof h.finish === 'number' ? h.finish : null,
                aug: {
                    trackwork: twRaw[idx],
                    distance: distRaw[idx],
                    synergy: synRaw[idx],
                    trend: trendRaw[idx],
                    form_detail: { score: sForm, note: h.form_note, trend: h.form_trend },
                    except_detail: { score: sExcept, flags: Array.isArray(h.except_flags) ? h.except_flags.slice(0, 4) : [], note: h.except_note },
                    vet_detail: { score: sVet, flags: Array.isArray(h.vet_flags) ? h.vet_flags.slice(0, 4) : [], note: h.vet_note },
                    report_detail: { note: h.report_note, last_run_rank: h.last_run_rank, last_run_note: h.last_run_note }
                },
                scores: {
                    last3: sLast3, rating: sRating, time: sTime,
                    draw: sDraw, weight: sWeight, odds: sOdds,
                    trackwork: sTW, distance: sDist, synergy: sSyn, trend: sTrend,
                    form: Math.round(sForm * 100) / 100, except: Math.round(sExcept * 100) / 100, vet: Math.round(sVet * 100) / 100,
                    base6: Math.round(base6 * 100) / 100,
                    total: total
                },
                value_ratio: Math.round(total / (h.odds_win > 0 ? h.odds_win : 1) * 1000) / 100
            };
        });
        scored.sort(function (a, b) { return b.scores.total - a.scores.total; });
        scored.forEach(function (s, i) { s.ai_rank = i + 1; });
        return scored;
    }

    function generateBetting(top4, allRanked, raceInfo) {
        const mainPick = top4[0];
        const secondPick = top4[1];
        const allClean = (allRanked || []).map(function (h) {
            if (!h) return h;
            if (h.odds_win == null || typeof h.odds_win !== 'number' || !isFinite(h.odds_win) || h.odds_win <= 0) {
                h.odds_win = 999;
            }
            if (h.odds_place == null || typeof h.odds_place !== 'number' || !isFinite(h.odds_place) || h.odds_place <= 0) {
                h.odds_place = 999;
            }
            return h;
        });
        const realOddsList = allClean.filter(function (h) { return h && h.odds_win < 999; });
        const sortedByOdds = allClean.slice().sort(function (a, b) { return (a.odds_win || 999) - (b.odds_win || 999); });
        const hottest = realOddsList.length > 0 ? realOddsList.sort(function (a, b) { return a.odds_win - b.odds_win; })[0] : null;
        const hasRealOdds = realOddsList.length > 0;

        function fmtOdds(o) {
            if (o == null || typeof o !== 'number' || o >= 999 || o <= 0) return '--';
            return (Math.round(o * 10) / 10).toFixed(1) + 'x';
        }
        function fmtTimeSec(t) {
            if (t == null || typeof t !== 'number' || !isFinite(t) || t >= 999 || t <= 0) return '--';
            var m = Math.floor(t / 60);
            var s = (t - m * 60).toFixed(2);
            if (m > 0) return m + 'm' + (s.length < 5 ? '0' : '') + s + 's';
            return parseFloat(s).toFixed(2) + 's';
        }
        function fmtWinName(h) { if (!h) return ''; return '#' + (h.number || '?') + ' ' + (h.name || ''); }

        const concerns = [];
        if (hottest && hasRealOdds && hottest.code !== (mainPick && mainPick.code)) {
            const last3 = hottest.last_3 || [];
            function l3Finish(r) {
                if (typeof r === 'number') return r || 99;
                if (r && typeof r === 'object' && typeof r.finish === 'number') return r.finish;
                return 99;
            }
            const good = last3.reduce(function (n, r) { return n + (l3Finish(r) <= 3 ? 1 : 0); }, 0);
            if (good < 2 && last3.length > 0) concerns.push('近績三仗僅 ' + good + ' 次入三甲，狀態不穩');
            if ((hottest.draw || 0) > 6) concerns.push('檔位 ' + hottest.draw + ' 偏外，短途賽疊罰較重');
            if ((hottest.best_time_sec || 999) > 58.0 && (hottest.best_time_sec && hottest.best_time_sec < 999)) concerns.push('最佳時間 ' + fmtTimeSec(hottest.best_time_sec) + ' 僅屬中游，爆頭難度高');
            if ((hottest.scores && hottest.scores.trackwork) < 60 && hottest.scores) concerns.push('晨操狀態一般');
            if ((hottest.scores && hottest.scores.distance) < 55 && hottest.scores) concerns.push('路程並非專長');
        }
        if (hasRealOdds && concerns.length === 0 && hottest) concerns.push('大熱門整體條件不俗，但值博率因低賠率而下降');

        function winToPlaceOdds(w, placeRank) {
            if (!w || w >= 999 || w <= 1) return null;
            const base = (placeRank === 1) ? 1.6 : (placeRank === 2 ? 2.2 : 2.8);
            return Math.max(1.1, Math.round((1 + (w - 1) / base) * 10) / 10);
        }
        function quinellaOdds(a, b) {
            if (!a || !b || a >= 999 || b >= 999 || a <= 1 || b <= 1) return null;
            const raw = (a * b) / (a + b) * 1.35;
            return Math.max(3, Math.round(raw * 10) / 10);
        }
        function trioOdds(a, b, c) {
            if (!a || !b || !c || a >= 999 || b >= 999 || c >= 999) return null;
            const raw = (a * b * c) / Math.max(6, (a + b + c)) * 2.6;
            return Math.max(15, Math.round(raw));
        }
        function first4Odds(a, b, c, d) {
            if (!a || !b || !c || !d || a >= 999 || b >= 999 || c >= 999 || d >= 999) return null;
            const raw = (a * b * c * d) / Math.max(24, (a + b + c + d)) * 6;
            return Math.max(60, Math.round(raw));
        }
        function formatReturn(mult, stake) {
            if (mult == null || typeof mult !== 'number' || mult >= 999 || mult <= 0) return '賠率待更新';
            if (mult <= 1) return '$' + stake + ' 注';
            const profit = Math.round((mult - 1) * stake);
            return '回本 +$' + profit + '（' + mult.toFixed(1) + 'x）';
        }

        const winPicks = [{
            code: mainPick.code, number: mainPick.number, name: mainPick.name, odds: mainPick.odds_win, oddsDisplay: fmtOdds(mainPick.odds_win),
            reason: coreAdvantage(mainPick, raceInfo),
            detail: detailedAiBreakdown(mainPick, raceInfo),
            returnText: formatReturn(mainPick.odds_win, 100)
        }];
        if (secondPick && secondPick.odds_win < 999 && secondPick.odds_win <= 15) {
            winPicks.push({
                code: secondPick.code, number: secondPick.number, name: secondPick.name, odds: secondPick.odds_win, oddsDisplay: fmtOdds(secondPick.odds_win),
                reason: coreAdvantage(secondPick, raceInfo),
                detail: detailedAiBreakdown(secondPick, raceInfo),
                returnText: formatReturn(secondPick.odds_win, 50)
            });
        }
        const thirdPick = top4[2];
        const fourthPick = top4[3];
        const placePicks = [];
        [mainPick, secondPick, thirdPick].forEach(function (h, i) {
            if (!h || !h.code) return;
            const po = winToPlaceOdds(h.odds_win, i + 1);
            placePicks.push({
                code: h.code, number: h.number, name: h.name, odds: h.odds_win, odds_place: po, oddsDisplay: fmtOdds(po), rank: (i + 1),
                reason: coreAdvantage(h, raceInfo),
                detail: detailedAiBreakdown(h, raceInfo),
                returnText: formatReturn(po, 50)
            });
        });

        const qCombosInitial = [
            {
                a_code: mainPick.code, a_number: mainPick.number, a_name: mainPick.name, a_horse: mainPick,
                b_code: secondPick.code, b_number: secondPick.number, b_name: secondPick.name, b_horse: secondPick,
                type: '核心 Q 超值之選'
            }
        ];
        if (hottest && hottest.code && hottest.code !== mainPick.code) {
            qCombosInitial.push({
                a_code: mainPick.code, a_number: mainPick.number, a_name: mainPick.name, a_horse: mainPick,
                b_code: hottest.code, b_number: hottest.number, b_name: hottest.name, b_horse: hottest,
                type: '穩健 Q 大熱保護'
            });
        }
        if (secondPick && thirdPick && secondPick.code && thirdPick.code) {
            qCombosInitial.push({
                a_code: secondPick.code, a_number: secondPick.number, a_name: secondPick.name, a_horse: secondPick,
                b_code: thirdPick.code, b_number: thirdPick.number, b_name: thirdPick.name, b_horse: thirdPick,
                type: '進取 Q 高回報'
            });
        }
        const seenPairs = {};
        const qCombos = [];
        const pickBackups = [secondPick, thirdPick, fourthPick, sortedByOdds[1], sortedByOdds[2]].filter(function (x) { return x && x.code; });
        qCombosInitial.forEach(function (q) {
            if (!q.a_code || !q.b_code) return;
            let b_code = q.b_code, b_name = q.b_name, b_number = q.b_number, b_horse = q.b_horse;
            let backupIdx = 0;
            while (q.a_code === b_code && backupIdx < pickBackups.length) {
                const alt = pickBackups[backupIdx];
                if (alt.code !== q.a_code) { b_code = alt.code; b_name = alt.name; b_number = alt.number; b_horse = alt; }
                backupIdx++;
            }
            if (q.a_code !== b_code) {
                const key = [q.a_code, b_code].sort().join('|');
                if (!seenPairs[key]) {
                    seenPairs[key] = true;
                    const aH = q.a_horse || allRanked.find(function (x) { return x.code === q.a_code; });
                    const bH = b_horse || allRanked.find(function (x) { return x.code === b_code; });
                    const ao = aH ? aH.odds_win : 999;
                    const bo = bH ? bH.odds_win : 999;
                    const qo = quinellaOdds(ao, bo);
                    const a_reason = aH ? coreAdvantage(aH, raceInfo) : '';
                    const b_reason = bH ? coreAdvantage(bH, raceInfo) : '';
                    const a_detail = aH ? detailedAiBreakdown(aH, raceInfo) : '';
                    const b_detail = bH ? detailedAiBreakdown(bH, raceInfo) : '';
                    qCombos.push({
                        a: q.a_code, a_number: q.a_number, a_name: q.a_name, a_reason: a_reason, a_detail: a_detail,
                        b: b_code, b_number: b_number, b_name: b_name, b_reason: b_reason, b_detail: b_detail,
                        type: q.type, odds_quinella: qo, oddsDisplay: fmtOdds(qo),
                        returnText: formatReturn(qo, 50)
                    });
                }
            }
        });

        const qPlaceCombos = [];
        const qpSeen = {};
        function addQP(a, b, typeTag) {
            if (!a || !b || a.code === b.code) return;
            const k = [a.code, b.code].sort().join('|');
            if (qpSeen[k]) return;
            qpSeen[k] = true;
            const qo = quinellaOdds(a.odds_win, b.odds_win);
            const qpo = qo ? Math.max(2.5, Math.round(qo / 1.8 * 10) / 10) : null;
            qPlaceCombos.push({
                a: a.code, a_number: a.number, a_name: a.name, a_reason: coreAdvantage(a, raceInfo), a_detail: detailedAiBreakdown(a, raceInfo),
                b: b.code, b_number: b.number, b_name: b.name, b_reason: coreAdvantage(b, raceInfo), b_detail: detailedAiBreakdown(b, raceInfo),
                type: typeTag,
                odds_qplace: qpo, oddsDisplay: fmtOdds(qpo),
                returnText: formatReturn(qpo, 40)
            });
        }
        if (mainPick && secondPick) addQP(mainPick, secondPick, '位置Q 穩健');
        if (mainPick && thirdPick) addQP(mainPick, thirdPick, '位置Q 進取');
        if (secondPick && thirdPick) addQP(secondPick, thirdPick, '位置Q 博冷');

        const tripleLegs = [secondPick, thirdPick, fourthPick].filter(function (x) {
            return x && x.code && x.code !== mainPick.code;
        }).slice(0, 3);
        const tripleEstOdds = trioOdds(mainPick.odds_win,
            (tripleLegs[0] ? tripleLegs[0].odds_win : 999),
            (tripleLegs[1] ? tripleLegs[1].odds_win : 999));
        const tripleChase = {
            banker: { code: mainPick.code, number: mainPick.number, name: mainPick.name, odds: mainPick.odds_win, oddsDisplay: fmtOdds(mainPick.odds_win),
                reason: coreAdvantage(mainPick, raceInfo), detail: detailedAiBreakdown(mainPick, raceInfo) },
            legs: tripleLegs.map(function (x) { return {
                code: x.code, number: x.number, name: x.name, odds: x.odds_win, oddsDisplay: fmtOdds(x.odds_win),
                reason: coreAdvantage(x, raceInfo), detail: detailedAiBreakdown(x, raceInfo)
            }; }),
            estimated_odds: tripleEstOdds,
            oddsDisplay: fmtOdds(tripleEstOdds),
            returnText: ''
        };
        const trioStake = 10 * Math.max(1, tripleLegs.length);
        tripleChase.stake_text = '$10 × ' + tripleLegs.length + ' 組 = $' + trioStake;
        tripleChase.returnText = formatReturn(tripleEstOdds, trioStake);

        const fourLegs = [secondPick, thirdPick, fourthPick, sortedByOdds[2]].filter(function (x) {
            return x && x.code && x.code !== mainPick.code;
        }).slice(0, 4);
        const fourEstOdds = first4Odds(mainPick.odds_win,
            (fourLegs[0] ? fourLegs[0].odds_win : 999),
            (fourLegs[1] ? fourLegs[1].odds_win : 999),
            (fourLegs[2] ? fourLegs[2].odds_win : 999));
        const fourChase = {
            banker: { code: mainPick.code, number: mainPick.number, name: mainPick.name, oddsDisplay: fmtOdds(mainPick.odds_win),
                reason: coreAdvantage(mainPick, raceInfo), detail: detailedAiBreakdown(mainPick, raceInfo) },
            legs: fourLegs.map(function (x) { return {
                code: x.code, number: x.number, name: x.name, oddsDisplay: fmtOdds(x.odds_win),
                reason: coreAdvantage(x, raceInfo), detail: detailedAiBreakdown(x, raceInfo)
            }; }),
            estimated_odds: fourEstOdds,
            oddsDisplay: fmtOdds(fourEstOdds)
        };
        const f4Stake = 5 * Math.max(1, (fourLegs.length * (fourLegs.length - 1)) / 2);
        fourChase.stake_text = '膽拖 ' + fourLegs.length + ' 腳 × $5 注，約 $' + Math.round(f4Stake);
        fourChase.returnText = formatReturn(fourEstOdds, Math.round(f4Stake));

        const coldBets = allRanked.filter(function (h) {
            if (!h || h.odds_win >= 999) return false;
            const sc = h.scores || {};
            const goodBT = (h.best_time_sec && h.best_time_sec < 999 && h.best_time_sec <= 58.0);
            return h.odds_win >= 15 && (goodBT || (sc.trackwork >= 75) || (sc.distance >= 75));
        }).slice(0, 2).map(function (c) {
            const sc = c.scores || {};
            let pot = '';
            if (sc.trackwork >= 75 && c.aug && c.aug.trackwork) pot = '晨操 ' + c.aug.trackwork.detail;
            else if (sc.distance >= 75 && c.aug && c.aug.distance) pot = c.aug.distance.detail;
            else if (c.best_time_sec && c.best_time_sec < 999) pot = '最佳時間 ' + fmtTimeSec(c.best_time_sec) + ' 屬頂尖水準';
            else pot = '晨操 + 路程評分不俗，值博率高';
            return {
                code: c.code, number: c.number, name: c.name, odds: c.odds_win, oddsDisplay: fmtOdds(c.odds_win),
                odds_place_est: winToPlaceOdds(c.odds_win, 3),
                reason: coreAdvantage(c, raceInfo),
                detail: detailedAiBreakdown(c, raceInfo),
                potential: pot + '，小注怡情有驚喜',
                returnText: formatReturn(c.odds_win, 20)
            };
        });

        const safeB_code = (qCombos.length >= 2 ? qCombos[1].b : (sortedByOdds[1] && sortedByOdds[1].code !== mainPick.code ? sortedByOdds[1].code : (secondPick && secondPick.code)));
        const safeB_name = (qCombos.length >= 2 ? qCombos[1].b_name : (sortedByOdds[1] && sortedByOdds[1].code !== mainPick.code ? sortedByOdds[1].name : (secondPick && secondPick.name)));
        const budgetPlan = [].filter(function (x) { return false; });
        const totalBudget = 0;

        const hotObj = { code: null, number: null, name: null, odds: null, concerns: [], available: false };
        if (hottest && hottest.code && hasRealOdds) {
            hotObj.code = hottest.code;
            hotObj.number = hottest.number;
            hotObj.name = hottest.name;
            hotObj.odds = hottest.odds_win;
            hotObj.oddsDisplay = fmtOdds(hottest.odds_win);
            hotObj.concerns = concerns;
            hotObj.available = true;
        }
        return {
            overpriced_hot: hotObj,
            win_picks: winPicks,
            place_picks: placePicks,
            q_combos: qCombos,
            qplace_combos: qPlaceCombos,
            triple_chase: tripleChase,
            first4_chase: fourChase,
            cold_bets: coldBets,
            budget_plan: budgetPlan,
            total_budget: totalBudget,
            has_real_odds: hasRealOdds
        };
    }

    function runFullAnalysis(raceData) {
        const raceInfo = raceData.race_info || {};
        const horses = raceData.horses || [];
        const pace = analyzePace(raceInfo, horses);
        const scored = scoreHorses(horses, raceInfo);
        const top4 = scored.slice(0, 4);
        const predictions = top4.map(function (h, i) {
            return { rank: i + 1, horse: h, core_advantage: coreAdvantage(h) };
        });
        const betting = generateBetting(top4, scored, raceInfo);
        const now = new Date();
        const pad = function (n) { return n < 10 ? '0' + n : '' + n; };
        const ts = now.getFullYear() + '-' + pad(now.getMonth() + 1) + '-' + pad(now.getDate()) +
            ' ' + pad(now.getHours()) + ':' + pad(now.getMinutes()) + ':' + pad(now.getSeconds());
        return {
            generated_at: ts,
            race_info: raceInfo,
            meta: raceData.meta || {},
            pace_analysis: pace,
            top4_predictions: predictions,
            all_ranked_horses: scored,
            betting_strategy: betting
        };
    }

    global.RacingAI = {
        analyzeLast3: analyzeLast3,
        analyzePace: analyzePace,
        scoreHorses: scoreHorses,
        coreAdvantage: coreAdvantage,
        generateBetting: generateBetting,
        runFullAnalysis: runFullAnalysis,
        analyzeTrackwork: analyzeTrackwork,
        analyzeDistanceSpecialty: analyzeDistanceSpecialty,
        analyzeJockeyHorseSynergy: analyzeJockeyHorseSynergy,
        analyzeRatingTrend: analyzeRatingTrend,
        parseTimeToSeconds: parseTimeToSeconds,
        minMax: minMax
    };
})(typeof window !== 'undefined' ? window : (typeof global !== 'undefined' ? global : this));
