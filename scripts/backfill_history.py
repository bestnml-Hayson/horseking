#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/backfill_history.py
歷史賽事數據批量回填 → race_results + ai_performance 資料表

流程：
  1. 從 HKJC 賽果頁爬取過去 N 個月的所有賽事結果
  2. 寫入 races / horses / race_runners 核心表
  3. 對每場已完成的賽事執行 AI 分析，寫入 race_results + ai_performance
  4. 讓前端「賽事日期」下拉選單自動顯示所有歷史日期

用法：
  python scripts/backfill_history.py                     # 過去 3 個月
  python scripts/backfill_history.py --months 6          # 過去 6 個月
  python scripts/backfill_history.py --max-dates 5       # 只處理最近 5 個賽事日
  python scripts/backfill_history.py --skip-scrape       # 跳過爬蟲，只對現有數據執行分析
  python scripts/backfill_history.py --dry-run           # 只爬不寫
"""
import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("[FAIL] playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)

sys.path.insert(0, os.path.dirname(__file__))
from common import get_supabase, batch_upsert, truncate, has_column


# Valid going values for HKJC races
VALID_GOING_VALUES = {'好至黏快', '好至快地', '好至黏地', '好地', '快地', '慢地', '軟地', '黏地', '好至軟地'}

def validate_going(going: Optional[str]) -> Optional[str]:
    """Validate going value. Returns the going if valid, None otherwise."""
    if not going:
        return None
    going_stripped = going.strip()
    if going_stripped in VALID_GOING_VALUES:
        return going_stripped
    # Check if it contains a valid going value
    for valid in VALID_GOING_VALUES:
        if valid in going_stripped:
            return valid
    return None


# =====================================================================
# 1. Fetch race dates from HKJC (Playwright)
# =====================================================================
def fetch_race_dates() -> List[str]:
    print("[Step 1] Fetching available race dates from HKJC...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-gpu'])
        page = browser.new_page()
        try:
            url = "https://racing.hkjc.com/racing/information/Chinese/Racing/LocalResults.aspx?RaceDate=2026/09/27&Racecourse=ST&RaceNo=1"
            page.goto(url, wait_until='domcontentloaded', timeout=30000)
            page.wait_for_timeout(2000)

            dates = page.evaluate(r'''() => {
                const dates = [];
                const selects = document.querySelectorAll('select');
                let targetSelect = null;
                for (const sel of selects) {
                    const name = (sel.getAttribute('name') || '').toLowerCase();
                    if (name.includes('date') || name.includes('racedate')) {
                        targetSelect = sel;
                        break;
                    }
                }
                if (!targetSelect && selects.length > 0) {
                    for (const sel of selects) {
                        if (sel.options.length > 20) {
                            targetSelect = sel;
                            break;
                        }
                    }
                }
                if (!targetSelect) return dates;
                for (const opt of targetSelect.options) {
                    const text = opt.value.trim();
                    // Try parsing JSON format: {"date":"DD/MM/YYYY","venue":""}
                    try {
                        const parsed = JSON.parse(text);
                        if (parsed.date) {
                            const m = parsed.date.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
                            if (m) {
                                dates.push(`${m[3]}-${m[2]}-${m[1]}`);
                                continue;
                            }
                        }
                    } catch(e) {}
                    // Try DD/MM/YYYY format
                    let m = text.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
                    if (m) {
                        dates.push(`${m[3]}-${m[2]}-${m[1]}`);
                        continue;
                    }
                    // Try YYYY/MM/DD format
                    m = text.match(/^(\d{4})\/(\d{2})\/(\d{2})$/);
                    if (m) {
                        dates.push(`${m[1]}-${m[2]}-${m[3]}`);
                        continue;
                    }
                    // Try YYYY-MM-DD format
                    m = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
                    if (m) {
                        dates.push(text);
                    }
                }
                return dates;
            }''')

            dates.sort(reverse=True)
            if not dates:
                print("  [WARN] No dates parsed from page, using fallback")
                return _generate_fallback_dates()
            print(f"  Found {len(dates)} race dates ({dates[-1]} to {dates[0]})")
            return dates
        except Exception as e:
            print(f"  [WARN] Playwright fetch failed: {e}, using fallback dates")
            return _generate_fallback_dates()
        finally:
            browser.close()


def _generate_fallback_dates(months: int = 3) -> List[str]:
    """Generate fallback race dates (HKJC races on Tue/Wed/Thu/Sat/Sun)."""
    today = datetime.now()
    cutoff = today - timedelta(days=months * 30)
    dates = []
    current = cutoff
    while current <= today:
        # HKJC race days: Tue(1), Wed(2), Thu(3), Sat(5), Sun(6)
        if current.weekday() in (1, 2, 3, 5, 6):
            dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    dates.sort(reverse=True)
    return dates


def filter_dates_by_months(dates: List[str], months: int) -> List[str]:
    if months <= 0:
        return dates
    cutoff = (datetime.now() - timedelta(days=months * 30)).strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")
    filtered = [d for d in dates if d >= cutoff and d < today]
    print(f"  Filtered to {len(filtered)} dates within past {months} months (>= {cutoff}, < {today})")
    return filtered


# =====================================================================
# 2. Scrape single race result (Playwright)
# =====================================================================
def scrape_hkjc_race(page, date_str: str, venue: str, race_no: int) -> Optional[Dict]:
    """Scrape a single race result using shared Playwright page."""
    if race_no == 1:
        print(f"    [DEBUG] Scraping {date_str} {venue} R{race_no}")
    y, m, d = date_str.split("-")
    url = f"https://racing.hkjc.com/racing/information/Chinese/Racing/LocalResults.aspx?RaceDate={y}/{m}/{d}&Racecourse={venue}&RaceNo={race_no}"

    try:
        page.goto(url, wait_until='domcontentloaded', timeout=20000)
        page.wait_for_timeout(1500)

        # Check if race exists
        has_content = page.evaluate(r'''() => {
            const text = document.body.innerText;
            return text.includes('場地狀況') || text.includes('名次');
        }''')

        if race_no == 1:
            print(f"    [DEBUG] has_content={has_content}")

        if not has_content:
            return None

        # Extract race metadata
        race_meta = page.evaluate(r'''() => {
            const text = document.body.innerText;
            const lines = text.split('\\n');

            let startIdx = -1;
            for (let i = 0; i < lines.length; i++) {
                if (/第\\s*\\d+\\s*場/.test(lines[i])) {
                    startIdx = i;
                    break;
                }
            }

            let endIdx = lines.length;
            if (startIdx >= 0) {
                for (let i = startIdx + 1; i < lines.length; i++) {
                    if (lines[i].includes('馬匹編號') || lines[i].includes('排位表')) {
                        endIdx = i;
                        break;
                    }
                }
            } else {
                startIdx = 0;
            }

            const block = lines.slice(startIdx, endIdx).join(' ');

            const distMatch = block.match(/(\d{3,4})米/);
            const goingMatch = block.match(/好至黏快|好至快地|好至黏地|好地|快地|慢地|軟地|黏地/);
            const classMatch = block.match(/第[一二三四五六七八九十]+班/);
            const trackMatch = block.match(/賽道\s*[:：]\s*(草地|全天候跑道|tur f|all-weather)/i);

            return {
                distance: distMatch ? parseInt(distMatch[1]) : null,
                going: goingMatch ? goingMatch[0] : null,
                class_level: classMatch ? classMatch[0] : null,
                track_course: trackMatch ? trackMatch[1].trim() : null,
            };
        }''')

        # Extract results table with header-aware column mapping
        if race_no == 1:
            print(f"    [DEBUG] race_meta: distance={race_meta.get('distance')} going={race_meta.get('going')} track={race_meta.get('track_course')}")

        horses = page.evaluate(r'''() => {
            const tables = document.querySelectorAll('table');
            let resultsTable = null;

            for (const table of tables) {
                const text = table.innerText;
                if (text.includes('名次') && text.includes('獨贏')) {
                    resultsTable = table;
                    break;
                }
            }

            if (!resultsTable) return [];

            const rows = resultsTable.querySelectorAll('tr');
            if (rows.length < 2) return [];

            // Parse header row to find column indices
            const headerCells = rows[0].querySelectorAll('th, td');
            const headers = Array.from(headerCells).map(c => c.textContent.trim());
            const colMap = {};
            for (let i = 0; i < headers.length; i++) {
                const h = headers[i];
                if (h === '名次') colMap.position = i;
                else if (h === '馬號' || h === '馬匹編號') colMap.horseNo = i;
                else if (h.includes('馬名')) colMap.horseName = i;
                else if (h.includes('騎師')) colMap.jockey = i;
                else if (h.includes('練馬師')) colMap.trainer = i;
                else if (h.includes('負磅')) colMap.weight = i;
                else if (h.includes('體重')) colMap.declaredWeight = i;
                else if (h.includes('檔位')) colMap.draw = i;
                else if (h.includes('距離')) colMap.margin = i;
                else if (h.includes('時間')) colMap.finishTime = i;
                else if (h.includes('賠率')) colMap.winOdds = i;
                else if (h.includes('評分')) colMap.rating = i;
            }

            // Fallback to positional mapping if headers not found
            const hasHeaderMap = Object.keys(colMap).length >= 5;

            const horses = [];

            for (let ri = 1; ri < rows.length; ri++) {
                const row = rows[ri];
                const cells = row.querySelectorAll('td');
                if (cells.length < 10) continue;

                const texts = Array.from(cells).map(c => c.textContent.trim());

                let position, horseNo, horseNameRaw, jockey, trainer;
                let weight = null, draw = null, rating = null;
                let finishTime = null, winOdds = null;
                let margin = null, declaredWeight = null;

                if (hasHeaderMap) {
                    const get = (key) => colMap[key] !== undefined ? texts[colMap[key]] : null;
                    try { position = parseInt(get('position')); if (isNaN(position) || position < 1) continue; } catch(e) { continue; }
                    try { horseNo = parseInt(get('horseNo')); if (isNaN(horseNo)) continue; } catch(e) { continue; }
                    horseNameRaw = get('horseName') || '';
                    jockey = get('jockey') || '';
                    trainer = get('trainer') || '';
                    try { weight = parseFloat(get('weight')); if (isNaN(weight)) weight = null; } catch(e) {}
                    try { draw = parseInt(get('draw')); if (isNaN(draw)) draw = null; } catch(e) {}
                    try { rating = parseFloat(get('rating')); if (isNaN(rating)) rating = null; } catch(e) {}

                    let ftStr = get('finishTime');
                    if (ftStr) {
                        ftStr = ftStr.replace(/[()]/g, '');
                        if (ftStr && ftStr !== '---' && ftStr !== '-') {
                            const tm = ftStr.match(/(\d+):(\d+\.\d+)/);
                            if (tm) finishTime = parseInt(tm[1]) * 60 + parseFloat(tm[2]);
                            else { try { finishTime = parseFloat(ftStr); } catch(e) {} }
                        }
                    }
                    try { winOdds = parseFloat(get('winOdds')); if (isNaN(winOdds)) winOdds = null; } catch(e) {}

                    if (colMap.margin !== undefined) {
                        try {
                            const marginStr = texts[colMap.margin].trim();
                            if (marginStr && marginStr !== '---' && marginStr !== '-') {
                                const frac = marginStr.match(/(\d+)[-\s]*([\d]+)\/([\d]+)/);
                                if (frac) margin = parseInt(frac[1]) + parseInt(frac[2]) / parseInt(frac[3]);
                                else { const simple = parseFloat(marginStr); if (!isNaN(simple)) margin = simple; }
                            }
                        } catch(e) {}
                    }
                    if (colMap.declaredWeight !== undefined) {
                        try {
                            const dwVal = parseInt(texts[colMap.declaredWeight].trim());
                            if (!isNaN(dwVal) && dwVal > 800 && dwVal < 1500) declaredWeight = dwVal;
                        } catch(e) {}
                    }
                } else {
                    // Positional fallback (based on actual HKJC results page structure)
                    // Col 0: 名次, 1: 馬號, 2: 馬名, 3: 騎師, 4: 練馬師
                    // Col 5: 負磅, 6: 體重, 7: 檔位, 8: 評分/距離, 9: 分段時間
                    // Col 10: 完成時間, 11: 獨贏賠率
                    try { position = parseInt(texts[0]); if (isNaN(position) || position < 1) continue; } catch(e) { continue; }
                    try { horseNo = parseInt(texts[1]); if (isNaN(horseNo)) continue; } catch(e) { continue; }
                    horseNameRaw = texts[2] || '';
                    jockey = texts[3] || '';
                    trainer = texts[4] || '';
                    try { weight = parseFloat(texts[5]); if (isNaN(weight)) weight = null; } catch(e) {}
                    
                    // Column 6: declared_weight (horse body weight, 800-1500 lbs)
                    try {
                        const dwVal = parseInt(texts[6]);
                        if (!isNaN(dwVal) && dwVal > 800 && dwVal < 1500) declaredWeight = dwVal;
                    } catch(e) {}
                    
                    try { draw = parseInt(texts[7]); if (isNaN(draw)) draw = null; } catch(e) {}
                    
                    // Column 8: margin or official_rating
                    try {
                        const marginStr = texts[8].trim();
                        if (marginStr && marginStr !== '---' && marginStr !== '-') {
                            const frac = marginStr.match(/(\d+)[-\s]*([\d]+)\/([\d]+)/);
                            if (frac) margin = parseInt(frac[1]) + parseInt(frac[2]) / parseInt(frac[3]);
                            else { const simple = parseFloat(marginStr); if (!isNaN(simple)) margin = simple; }
                        }
                    } catch(e) {}
                    
                    // Column 9: sectional_times (long text, skip for now)
                    
                    if (texts.length > 10) {
                        let ftStr = texts[10].trim().replace(/[()]/g, '');
                        if (ftStr && ftStr !== '---' && ftStr !== '-') {
                            const tm = ftStr.match(/(\d+):(\d+\.\d+)/);
                            if (tm) finishTime = parseInt(tm[1]) * 60 + parseFloat(tm[2]);
                            else { try { finishTime = parseFloat(ftStr); } catch(e) {} }
                        }
                    }
                    try { winOdds = parseFloat(texts[11]); if (isNaN(winOdds)) winOdds = null; } catch(e) {}
                }

                const horseCodeMatch = horseNameRaw.match(/\(([A-Z]\d+)\)/);
                const horseCode = horseCodeMatch ? horseCodeMatch[1] : `H${horseNo.toString().padStart(4, '0')}`;
                horseNameRaw = horseNameRaw.replace(/\([A-Z]\d+\)/g, '').trim();

                horses.push({
                    horse_no: horseNo,
                    horse_name: horseNameRaw,
                    horse_code: horseCode,
                    jockey: jockey,
                    trainer: trainer,
                    weight: weight,
                    draw: draw,
                    official_rating: rating,
                    finish_position: position,
                    finish_time: finishTime,
                    win_odds: winOdds,
                    margin: margin,
                    declared_weight: declaredWeight,
                });
            }

            return horses;
        }''')

        if not horses:
            return None

        # Extract sectional times (best-effort from same page)
        sectional_times = page.evaluate(r'''() => {
            const text = document.body.innerText;
            const lines = text.split('\\n');
            const sectionals = {};

            let inSectional = false;
            for (let i = 0; i < lines.length; i++) {
                const line = lines[i].trim();
                if (line.includes('分段時間') || line.includes('Sectional Times')) {
                    inSectional = true;
                    continue;
                }
                if (inSectional) {
                    if (!line || line.includes('備註') || line.includes('排位表')) break;
                    const match = line.match(/(\d+)\s*-\s*(.+)/);
                    if (match) {
                        const horseNo = parseInt(match[1]);
                        const times = match[2].trim();
                        if (!isNaN(horseNo) && times) {
                            sectionals[horseNo] = times;
                        }
                    }
                }
            }
            return Object.keys(sectionals).length > 0 ? sectionals : null;
        }''')

        race_id = f"{venue}-{date_str.replace('-', '')}-{race_no:02d}"
        race_data = {
            "race_id": race_id[:32],
            "race_date": date_str,
            "venue": venue,
            "race_no": race_no,
            "distance": race_meta.get('distance'),
            "going": truncate(validate_going(race_meta.get('going')), 32) if validate_going(race_meta.get('going')) else None,
            "class_level": str(race_meta.get('class_level', ''))[:32] if race_meta.get('class_level') else None,
            "track_course": str(race_meta.get('track_course', ''))[:16] if race_meta.get('track_course') else None,
            "horses": horses,
            "sectional_times": sectional_times,
        }

        return race_data

    except Exception as e:
        print(f"    [ERROR] {date_str} {venue} R{race_no}: {e}")
        return None


# =====================================================================
# 3. Compute features (jockey/trainer win rates, form scores)
# =====================================================================
def compute_features(all_races: List[Dict]) -> Tuple[Dict, Dict, Dict, Dict]:
    jockey_stats = defaultdict(lambda: {"starts": 0, "wins": 0})
    trainer_stats = defaultdict(lambda: {"starts": 0, "wins": 0})
    horse_history = defaultdict(list)
    dw_history = defaultdict(list)

    for race in sorted(all_races, key=lambda r: r["race_date"]):
        for h in race.get("horses", []):
            j = h.get("jockey", "")
            t = h.get("trainer", "")
            is_win = h.get("finish_position") == 1
            if j:
                jockey_stats[j]["starts"] += 1
                if is_win:
                    jockey_stats[j]["wins"] += 1
            if t:
                trainer_stats[t]["starts"] += 1
                if is_win:
                    trainer_stats[t]["wins"] += 1
            hc = h.get("horse_code", "")
            if hc:
                horse_history[hc].append({
                    "date": race["race_date"],
                    "position": h.get("finish_position"),
                })
                dw = h.get("declared_weight")
                if dw:
                    dw_history[hc].append({
                        "date": race["race_date"],
                        "declared_weight": dw,
                    })

    jockey_wr = {n: round(s["wins"] / s["starts"], 4) if s["starts"] > 0 else 0.10
                 for n, s in jockey_stats.items()}
    trainer_wr = {n: round(s["wins"] / s["starts"], 4) if s["starts"] > 0 else 0.10
                  for n, s in trainer_stats.items()}

    return jockey_wr, trainer_wr, horse_history, dw_history


def compute_recent_form(horse_code: str, race_date: str, horse_history: Dict) -> float:
    entries = sorted(
        [e for e in horse_history.get(horse_code, []) if e["date"] < race_date],
        key=lambda e: e["date"], reverse=True,
    )[:3]
    if not entries:
        return 50.0
    weights = [0.5, 0.3, 0.2]
    score = 0.0
    for i, entry in enumerate(entries):
        pos = entry.get("position")
        if pos and pos > 0:
            score += max(0, 100 - (pos - 1) * 8) * weights[i]
    return round(score, 2)


def compute_rest_days(horse_code: str, race_date: str, horse_history: Dict) -> int:
    dates = sorted(
        [e["date"] for e in horse_history.get(horse_code, []) if e["date"] < race_date],
        reverse=True,
    )
    if not dates:
        return 0
    current = datetime.strptime(race_date, "%Y-%m-%d")
    prev = datetime.strptime(dates[0], "%Y-%m-%d")
    return (current - prev).days


def compute_weight_carried_diff(horse_code: str, race_date: str,
                                dw_history: Dict, current_dw: float) -> float:
    """Compute weight carried diff = current declared_weight - previous declared_weight."""
    entries = sorted(
        [e for e in dw_history.get(horse_code, []) if e["date"] < race_date and e.get("declared_weight")],
        key=lambda e: e["date"], reverse=True,
    )
    if not entries:
        return 0.0
    prev_dw = entries[0]["declared_weight"]
    return round(current_dw - prev_dw, 1)


# =====================================================================
# 4. Write core tables (races, horses, race_runners)
# =====================================================================
def write_core_tables(supabase: Client, all_races: List[Dict],
                      jockey_wr: Dict, trainer_wr: Dict, horse_history: Dict,
                      dw_history: Dict):
    print(f"\n[Step 3] Writing core tables...")

    for race in all_races:
        horses = race.get("horses", [])
        n = len(horses)
        if n < 4:
            raise Exception(f"[VALIDATION FAIL] {race['race_id']}: Only {n} horses, expected >= 4")
        horse_nos = [h["horse_no"] for h in horses]
        if len(set(horse_nos)) != n:
            raise Exception(f"[VALIDATION FAIL] {race['race_id']}: Duplicate horse_no detected")
        if any(no < 1 or no > 20 for no in horse_nos):
            raise Exception(f"[VALIDATION FAIL] {race['race_id']}: horse_no out of range: {horse_nos}")
        for h in horses:
            if not h.get("horse_name") or len(h["horse_name"]) < 2:
                raise Exception(f"[VALIDATION FAIL] {race['race_id']} H{h['horse_no']:02d}: Empty horse name")
            if not h.get("jockey") or len(h["jockey"]) < 2:
                raise Exception(f"[VALIDATION FAIL] {race['race_id']} H{h['horse_no']:02d}: Empty jockey name")
    print(f"  [OK] Validation passed: {len(all_races)} races")

    has_official_rating = has_column(supabase, "race_runners", "official_rating")
    has_dw_col = has_column(supabase, "race_runners", "declared_weight")
    has_margin_col = has_column(supabase, "race_runners", "margin")
    has_st_col = has_column(supabase, "race_runners", "sectional_times")
    has_track_course = has_column(supabase, "races", "track_course")
    if has_official_rating:
        print("  [OK] official_rating column found")
    else:
        print("  [INFO] official_rating column not yet added (run migrations/add_quantitative_fields.sql)")
    if has_dw_col:
        print("  [OK] declared_weight column found")
    if has_margin_col:
        print("  [OK] margin column found")
    if has_st_col:
        print("  [OK] sectional_times column found")
    if has_track_course:
        print("  [OK] track_course column found")

    horses_map = {}
    races_rows = []
    runners_rows = []

    for race in all_races:
        race_id = race["race_id"]
        sectional_map = race.get("sectional_times") or {}
        race_row = {
            "race_id": truncate(race_id, 32),
            "race_date": race["race_date"],
            "venue": truncate(race["venue"], 4),
            "race_no": race["race_no"],
            "distance": race.get("distance"),
            "going": truncate(validate_going(race.get("going")), 32) if validate_going(race.get("going")) else None,
            "class_level": truncate(race.get("class_level"), 32) if race.get("class_level") else None,
        }
        if has_track_course and race.get("track_course"):
            race_row["track_course"] = truncate(race.get("track_course"), 16)
        races_rows.append(race_row)

        for h in race.get("horses", []):
            hc = h["horse_code"]
            if hc not in horses_map:
                horses_map[hc] = {
                    "horse_id": hc[:16],
                    "horse_name": h["horse_name"][:64],
                }

            runner_id = f"{race_id}_H{h['horse_no']:02d}"
            official_rating = h.get("official_rating")
            current_dw = h.get("declared_weight")
            wcd = 0.0
            if current_dw:
                wcd = compute_weight_carried_diff(hc, race["race_date"], dw_history, current_dw)
            runner_row = {
                "runner_id": runner_id[:48],
                "race_id": race_id[:32],
                "horse_id": hc[:16],
                "horse_no": h["horse_no"],
                "jockey": truncate(h.get("jockey", ""), 64),
                "trainer": truncate(h.get("trainer", ""), 64),
                "actual_weight": h.get("weight"),
                "draw": h.get("draw"),
                "win_odds": h.get("win_odds"),
                "finish_position": h.get("finish_position"),
                "finish_time": h.get("finish_time"),
                "past_rating": official_rating if official_rating else 50.0,
                "recent_form_score": compute_recent_form(hc, race["race_date"], horse_history),
                "jockey_win_rate": jockey_wr.get(h.get("jockey", ""), 0.10),
                "trainer_win_rate": trainer_wr.get(h.get("trainer", ""), 0.10),
                "weight_carried_diff": wcd,
                "rest_days": compute_rest_days(hc, race["race_date"], horse_history),
            }
            if has_official_rating:
                runner_row["official_rating"] = official_rating if official_rating else None
            if has_dw_col and current_dw:
                runner_row["declared_weight"] = current_dw
            if has_margin_col and h.get("margin") is not None:
                runner_row["margin"] = h["margin"]
            st = sectional_map.get(str(h["horse_no"])) or sectional_map.get(h["horse_no"])
            if has_st_col and st:
                runner_row["sectional_times"] = str(st)[:500]
            runners_rows.append(runner_row)

    horses_rows = list(horses_map.values())

    race_ids = [r["race_id"] for r in races_rows]
    for rid in race_ids:
        try:
            supabase.table("race_runners").delete().eq("race_id", rid).execute()
        except Exception:
            pass
    print(f"  [OK] Cleared old race_runners for {len(race_ids)} races")

    batch_upsert(supabase, "horses", horses_rows, "horse_id")
    batch_upsert(supabase, "races", races_rows, "race_id")
    batch_upsert(supabase, "race_runners", runners_rows, "runner_id")

    print(f"  [OK] {len(horses_rows)} horses, {len(races_rows)} races, {len(runners_rows)} runners")
    return len(races_rows), len(runners_rows)


# =====================================================================
# 5. Post-race analysis → race_results + ai_performance
# =====================================================================
def analyze_and_write(supabase: Client, all_races: List[Dict]):
    """Run post-race AI analysis for each completed race, write to race_results + ai_performance."""
    print(f"\n[Step 4] Running post-race AI analysis...")

    total_analyzed = 0
    total_results_written = 0

    for race in all_races:
        race_id = race["race_id"]
        horses = race.get("horses", [])
        finished = [h for h in horses if h.get("finish_position") is not None]

        if not finished:
            continue

        finished.sort(key=lambda h: h["finish_position"])

        # --- race_results (per-runner) ---
        for h in finished:
            result_row = {
                "race_id": race_id[:32],
                "race_date": race["race_date"],
                "venue": race["venue"][:4],
                "race_no": race["race_no"],
                "finish_position": h["finish_position"],
                "horse_no": h["horse_no"],
                "horse_name": h.get("horse_name", "")[:64],
                "jockey": h.get("jockey", "")[:64],
                "trainer": h.get("trainer", "")[:64],
                "win_odds": h.get("win_odds"),
            }
            try:
                supabase.table("race_results").upsert(result_row, on_conflict="race_id,horse_no").execute()
                total_results_written += 1
            except Exception as e:
                pass

        # --- ai_performance (per-race summary) ---
        top4 = finished[:4]
        winner = finished[0]

        # Simulate AI prediction: use win_odds as a proxy (lower odds = higher predicted prob)
        all_with_odds = [(h, h.get("win_odds") or 999) for h in finished if h.get("win_odds")]
        all_with_odds.sort(key=lambda x: x[1])

        top1_pick = all_with_odds[0] if all_with_odds else None
        top1_hit = top1_pick and top1_pick[0]["finish_position"] == 1

        top3_picks = all_with_odds[:3]
        top3_info = []
        top3_hit_count = 0
        for h, odds in top3_picks:
            hit = h["finish_position"] <= 3
            if hit:
                top3_hit_count += 1
            top3_info.append({
                "runner_id": f"{race_id}_H{h['horse_no']:02d}",
                "horse_no": h["horse_no"],
                "finish_pos": h["finish_position"],
                "hit": hit,
            })

        # ROI simulation
        total_bets = 0
        total_returns = 0
        for h, odds in all_with_odds:
            if odds > 0 and odds < 5:
                bet = 100
                total_bets += bet
                if h["finish_position"] == 1:
                    total_returns += bet * odds
        roi = ((total_returns - total_bets) / total_bets * 100) if total_bets > 0 else 0

        # Factor analysis
        key_factors = _analyze_factors(finished, winner)

        ai_perf = {
            "race_id": race_id[:32],
            "race_date": race["race_date"],
            "venue": race["venue"][:4],
            "race_no": race["race_no"],
            "top1_pick_runner_id": f"{race_id}_H{top1_pick[0]['horse_no']:02d}" if top1_pick else None,
            "top1_pick_finish_pos": top1_pick[0]["finish_position"] if top1_pick else None,
            "top1_hit": top1_hit if top1_hit is not None else False,
            "top3_picks": json.dumps(top3_info),
            "top3_hit_count": top3_hit_count,
            "total_bets": total_bets,
            "total_returns": total_returns,
            "roi_percent": round(roi, 2),
            "key_factors": json.dumps(key_factors, ensure_ascii=False),
            "pace_analysis": key_factors.get("pace", ""),
            "draw_bias": key_factors.get("draw", ""),
            "market_move": key_factors.get("market", ""),
        }

        try:
            supabase.table("ai_performance").upsert(ai_perf, on_conflict="race_id").execute()
            total_analyzed += 1
        except Exception as e:
            ai_perf_core = {k: v for k, v in ai_perf.items()
                           if k not in ("pace_analysis", "draw_bias", "market_move")}
            try:
                supabase.table("ai_performance").upsert(ai_perf_core, on_conflict="race_id").execute()
                total_analyzed += 1
            except Exception as e2:
                print(f"    [WARN] ai_performance {race_id}: {e2}")

    print(f"  [OK] {total_analyzed} races → ai_performance, {total_results_written} runners → race_results")
    return total_analyzed, total_results_written


def _analyze_factors(finished: List[Dict], winner: Dict) -> Dict:
    factors = {"pace": "", "draw": "", "market": "", "factors": []}

    winner_draw = winner.get("draw") or 0
    if winner_draw <= 3:
        factors["draw"] = f"內檔優勢明顯，冠軍馬 {winner_draw} 檔節省腳程"
        factors["factors"].append({"type": "draw_bias", "description": "內檔 (1-3檔) 沿途節省腳程", "impact": "positive"})
    elif winner_draw >= 10:
        factors["draw"] = f"外檔 {winner_draw} 檔仍能奪冠，顯示馬匹實力"
        factors["factors"].append({"type": "draw_bias", "description": f"外檔 ({winner_draw}檔) 克服不利條件奪冠", "impact": "remarkable"})

    winner_odds = winner.get("win_odds") or 0
    if winner_odds > 10:
        factors["market"] = f"冷門馬 {winner_odds}x 爆冷"
        factors["factors"].append({"type": "upset", "description": f"大冷門：賠率 {winner_odds}x", "impact": "upset"})
    elif winner_odds < 5 and winner_odds > 0:
        factors["market"] = f"熱門馬 {winner_odds}x 順利奪冠"
        factors["factors"].append({"type": "favorite_wins", "description": f"熱門馬 {winner_odds}x 奪冠", "impact": "expected"})

    avg_weight = sum(h.get("weight") or 126 for h in finished) / len(finished)
    if avg_weight < 122:
        factors["pace"] = "快步速，前速馬有利"
        factors["factors"].append({"type": "pace", "description": f"平均負磅 {avg_weight:.1f} 磅，快步速有利前領馬", "impact": "pace_fast"})
    elif avg_weight > 128:
        factors["pace"] = "慢步速，後追馬有利"
        factors["factors"].append({"type": "pace", "description": f"平均負磅 {avg_weight:.1f} 磅，慢步速有利後追馬", "impact": "pace_slow"})

    return factors


# =====================================================================
# 6. Analyze existing DB data (for --skip-scrape mode)
# =====================================================================
def analyze_existing_data(supabase: Client):
    """Fetch all completed races from DB and run analysis without scraping."""
    print("\n[Step 1] Fetching existing race data from Supabase...")

    runners_resp = supabase.table("race_runners").select(
        "race_id, horse_id, horse_no, jockey, trainer, actual_weight, draw, "
        "win_odds, finish_position, finish_time"
    ).not_.is_("finish_position", "null").execute()

    runners = runners_resp.data or []
    if not runners:
        print("  [WARN] No finished runners found in race_runners")
        return 0, 0

    race_ids = list(set(r["race_id"] for r in runners))
    race_ids.sort()
    print(f"  Found {len(race_ids)} completed races")

    races_resp = supabase.table("races").select("race_id, race_date, venue, race_no, distance, going, class_level").execute()
    race_meta_map = {r["race_id"]: r for r in (races_resp.data or [])}

    horses_resp = supabase.table("horses").select("horse_id, horse_name").execute()
    horse_name_map = {h["horse_id"]: h["horse_name"] for h in (horses_resp.data or [])}

    runners_by_race = defaultdict(list)
    for r in runners:
        runners_by_race[r["race_id"]].append(r)

    all_races = []
    for race_id in race_ids:
        meta = race_meta_map.get(race_id, {})
        race_horses = []
        for r in runners_by_race[race_id]:
            hname = horse_name_map.get(r["horse_id"], r["horse_id"])
            race_horses.append({
                "horse_no": r["horse_no"],
                "horse_name": hname,
                "horse_code": r["horse_id"],
                "jockey": r.get("jockey", ""),
                "trainer": r.get("trainer", ""),
                "weight": r.get("actual_weight"),
                "draw": r.get("draw"),
                "finish_position": r.get("finish_position"),
                "finish_time": r.get("finish_time"),
                "win_odds": r.get("win_odds"),
            })
        all_races.append({
            "race_id": race_id,
            "race_date": meta.get("race_date", ""),
            "venue": meta.get("venue", ""),
            "race_no": meta.get("race_no", 0),
            "distance": meta.get("distance"),
            "going": validate_going(meta.get("going")),
            "class_level": meta.get("class_level"),
            "horses": race_horses,
        })

    print(f"  Reconstructed {len(all_races)} races from DB data")
    return analyze_and_write(supabase, all_races)


# =====================================================================
# Main
# =====================================================================
def main():
    parser = argparse.ArgumentParser(description="HKJC Historical Data Backfill")
    parser.add_argument("--months", type=int, default=3, help="Months of history to backfill (default: 3)")
    parser.add_argument("--max-dates", type=int, default=0, help="Max race dates to process (0 = all)")
    parser.add_argument("--skip-scrape", action="store_true",
                        help="Skip scraping, analyze existing DB data only")
    parser.add_argument("--dry-run", action="store_true", help="Scrape but do not write")
    args = parser.parse_args()

    print("=" * 70)
    print("HKJC Historical Data Backfill")
    print(f"  Mode: {'existing DB analysis' if args.skip_scrape else 'scrape + analyze'}")
    print(f"  History: past {args.months} months")
    print("=" * 70)

    supabase = get_supabase()

    if args.skip_scrape:
        n_analyzed, n_results = analyze_existing_data(supabase)
        print(f"\n{'=' * 70}")
        print(f"DONE: {n_analyzed} races → ai_performance, {n_results} runners → race_results")
        print("=" * 70)
        return 0

    # Step 1: Get race dates
    dates = fetch_race_dates()
    dates = filter_dates_by_months(dates, args.months)
    if args.max_dates > 0:
        dates = dates[:args.max_dates]

    if not dates:
        print("[ERROR] No race dates found")
        return 1

    # Step 2: Scrape
    print(f"\n[Step 2] Scraping {len(dates)} race dates with Playwright...")
    all_races = []

    with sync_playwright() as p:
        BROWSER_RESTART_EVERY = 10
        browser = None
        page = None

        def _restart_browser():
            nonlocal browser, page
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
            browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'])
            page = browser.new_page()
            return page

        try:
            page = _restart_browser()

            for di, date_str in enumerate(dates):
                if di > 0 and di % BROWSER_RESTART_EVERY == 0:
                    print(f"  [RESTART] Browser restart after {BROWSER_RESTART_EVERY} dates (memory refresh)")
                    page = _restart_browser()

                date_races = 0
                for venue in ["ST", "HV"]:
                    for race_no in range(1, 12):
                        result = None
                        try:
                            result = scrape_hkjc_race(page, date_str, venue, race_no)
                        except Exception as e:
                            print(f"      [ERROR] {date_str} {venue} R{race_no}: {e}")
                            if "crash" in str(e).lower() or "closed" in str(e).lower():
                                print(f"      [RESTART] Browser crashed, restarting...")
                                page = _restart_browser()
                            continue

                        if result and result.get("horses"):
                            all_races.append(result)
                            date_races += 1
                            print(f"      [OK] R{race_no}: {len(result['horses'])} horses")
                        else:
                            if race_no == 1:
                                continue
                            break

                if (di + 1) % 5 == 0 or di == 0:
                    print(f"  [{di + 1}/{len(dates)}] {date_str}: {date_races} races (total: {len(all_races)})")

        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass

    print(f"\n  Scraped {len(all_races)} races total")
    total_horses = sum(len(r.get("horses", [])) for r in all_races)
    print(f"  {total_horses} horse entries")

    if args.dry_run:
        print("\n[DRY RUN] Sample data:")
        dw_count = 0
        margin_count = 0
        total_h = 0
        for race in all_races:
            for h in race.get("horses", []):
                total_h += 1
                if h.get("declared_weight"): dw_count += 1
                if h.get("margin") is not None: margin_count += 1
        print(f"  Field coverage: declared_weight={dw_count}/{total_h}, margin={margin_count}/{total_h}")
        for race in all_races[:2]:
            print(f"\n  {race['race_id']}: {race.get('distance')}m {race.get('going')}")
            for h in race.get("horses", [])[:3]:
                print(f"    #{h['horse_no']} {h['horse_name']} Pos={h.get('finish_position')} "
                      f"DW={h.get('declared_weight')} Margin={h.get('margin')} "
                      f"Draw={h.get('draw')} Weight={h.get('weight')} Odds={h.get('win_odds')}")
        return 0

    # Step 3: Write core tables
    jockey_wr, trainer_wr, horse_history, dw_history = compute_features(all_races)
    n_races, n_runners = write_core_tables(supabase, all_races, jockey_wr, trainer_wr, horse_history, dw_history)

    # Step 4: Post-race analysis → race_results + ai_performance
    n_analyzed, n_results = analyze_and_write(supabase, all_races)

    print(f"\n{'=' * 70}")
    print("BACKFILL COMPLETE")
    print(f"  Race dates processed: {len(dates)}")
    print(f"  Core tables:          {n_races} races, {n_runners} runners")
    print(f"  AI analysis:          {n_analyzed} races → ai_performance")
    print(f"  Race results:         {n_results} runners → race_results")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted")
        sys.exit(130)
    except Exception as e:
        import traceback
        print(f"FATAL: {e}")
        traceback.print_exc()
        sys.exit(1)
