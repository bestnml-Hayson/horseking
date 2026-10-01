#!/usr/bin/env python3
"""
scripts/auto_scraper.py
HKJC 官方網站即時爬蟲 + Supabase 寫入
-----------------------------------------------------------
流程：
  1. 使用 Playwright 瀏覽器渲染 HKJC bet.hkjc.com SPA 頁面
  2. 提取每場賽事的真實排位表（馬號、馬名、騎師、練馬師、檔位、負磅、賠率）
  3. 清空 Supabase 舊資料
  4. 寫入 races, race_runners, horses 表
  5. 執行 Benter 模型計算

環境變數：
  SUPABASE_URL
  SUPABASE_SERVICE_KEY

CLI：
  python scripts/auto_scraper.py                          # auto-detect today
  python scripts/auto_scraper.py --date 2026-09-27 --venue ST
  python scripts/auto_scraper.py --fetch-live             # auto-detect + write to Supabase
  python scripts/auto_scraper.py --dry-run                # scrape but do not write
"""
import os
import sys
import json
import re
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

HKT = ZoneInfo('Asia/Hong_Kong')

try:
    from supabase import create_client, Client
except ImportError:
    print("[FAIL] supabase-py not installed. Run: pip install supabase")
    sys.exit(1)

sys.path.insert(0, os.path.dirname(__file__))
from common import get_supabase, batch_upsert, truncate, has_column, retry_supabase

# Re-export for live_high_frequency_pacing.py compatibility
get_supabase_client = get_supabase

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


def clear_old_data(supabase: Client, race_date: str, venue: str):
    print(f"\n[Clear] Clearing old data for {race_date} {venue}...")
    races_resp = retry_supabase(
        lambda: supabase.table('races').select('race_id').eq('race_date', race_date).eq('venue', venue).execute()
    )
    race_ids = [r['race_id'] for r in (races_resp.data or [])]

    if race_ids:
        for race_id in race_ids:
            retry_supabase(lambda rid=race_id: supabase.table('model_predictions').delete().eq('race_id', rid).execute())
            retry_supabase(lambda rid=race_id: supabase.table('race_runners').delete().eq('race_id', rid).execute())
        retry_supabase(
            lambda: supabase.table('races').delete().eq('race_date', race_date).eq('venue', venue).execute()
        )
        print(f"  [OK] Cleared {len(race_ids)} races + runners + predictions")
    else:
        print("  [OK] No old data found")


# =====================================================================
# Dynamic feature computation from Supabase history
# =====================================================================
def compute_jockey_trainer_win_rates(supabase) -> tuple:
    """Query Supabase historical race_runners to compute real jockey/trainer win rates."""
    print("  [WinRate] Computing jockey/trainer win rates from Supabase history...")
    result = retry_supabase(
        lambda: supabase.table('race_runners').select(
            'jockey, trainer, finish_position'
        ).not_.is_('finish_position', 'null').execute()
    )
    rows = result.data or []

    jockey_stats = {}
    trainer_stats = {}
    for r in rows:
        j = (r.get('jockey') or '').strip()
        t = (r.get('trainer') or '').strip()
        pos = r.get('finish_position')
        if j:
            if j not in jockey_stats:
                jockey_stats[j] = [0, 0]
            jockey_stats[j][0] += 1
            if pos == 1:
                jockey_stats[j][1] += 1
        if t:
            if t not in trainer_stats:
                trainer_stats[t] = [0, 0]
            trainer_stats[t][0] += 1
            if pos == 1:
                trainer_stats[t][1] += 1

    jockey_wr = {n: round(s[1] / s[0], 4) for n, s in jockey_stats.items() if s[0] >= 3}
    trainer_wr = {n: round(s[1] / s[0], 4) for n, s in trainer_stats.items() if s[0] >= 3}
    print(f"  [WinRate] {len(jockey_wr)} jockeys, {len(trainer_wr)} trainers (min 3 starts)")
    return jockey_wr, trainer_wr


def compute_weight_diffs(supabase, horse_entries: list) -> dict:
    """Query Supabase for each horse's previous declared_weight to compute weight_carried_diff."""
    diffs = {}
    has_dw_col = has_column(supabase, 'race_runners', 'declared_weight')
    if not has_dw_col:
        return diffs

    for entry in horse_entries:
        horse_id = entry['horse_id']
        current_dw = entry.get('declared_weight')
        if not current_dw:
            continue
        prev = retry_supabase(
            lambda hid=horse_id: supabase.table('race_runners').select('declared_weight').eq(
                'horse_id', hid
            ).not_.is_('declared_weight', 'null').order(
                'race_id', desc=True
            ).limit(1).execute()
        )
        if prev.data and prev.data[0].get('declared_weight'):
            prev_dw = float(prev.data[0]['declared_weight'])
            diffs[horse_id] = round(current_dw - prev_dw, 1)
    return diffs


# =====================================================================
# HKJC Scraper (Playwright headless browser)
# =====================================================================
def scrape_hkjc_races(date_str: str, venue: str) -> List[Dict]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[FAIL] playwright not installed. Run: pip install playwright && playwright install chromium")
        sys.exit(1)

    date_path = date_str.replace('-', '')
    date_slash = date_str.replace('-', '/')
    venue_cn = '沙田' if venue == 'ST' else '跑馬地'

    all_races = []
    print(f"\n[Scraper] Starting HKJC scraper for {date_str} {venue_cn}...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-gpu'])
        page = browser.new_page()

        for race_no in range(1, 13):
            print(f"  Scraping R{race_no}...")

            try:
                racecard_url = f"https://racing.hkjc.com/racing/information/Chinese/Racing/RaceCard.aspx?RaceDate={date_slash}&Racecourse={venue}&RaceNo={race_no}"
                page.goto(racecard_url, wait_until='domcontentloaded', timeout=30000)
                page.wait_for_timeout(4000)

                horses = page.evaluate('''() => {
                    const horses = [];
                    const tables = document.querySelectorAll('table');
                    let targetTable = null;
                    let colMap = {};

                    for (const t of tables) {
                        const rows = t.querySelectorAll('tr');
                        if (rows.length < 5) continue;

                        const firstRowCells = rows[0].querySelectorAll('td, th');
                        let hasFormCol = false;
                        let hasHorseCol = false;
                        for (let i = 0; i < firstRowCells.length; i++) {
                            const txt = firstRowCells[i].textContent.trim();
                            if (txt === '6次近績') { hasFormCol = true; colMap.form = i; }
                            if (txt === '馬名') { hasHorseCol = true; colMap.horseName = i; }
                            if (txt === '評分' || txt === '評分*') colMap.rating = i;
                            if (txt === '負磅' || txt === '配磅') colMap.weight = i;
                            if (txt === '騎師') colMap.jockey = i;
                            if (txt === '檔位' || txt === '排位檔位') colMap.draw = i;
                            if (txt === '練馬師') colMap.trainer = i;
                            if (txt === '排位體重' || txt === '體重') colMap.declaredWeight = i;
                            if (txt === '排位體重+/-' || txt === '體重+/-') colMap.weightChange = i;
                            if (txt === '最佳時間') colMap.bestTime = i;
                            if (txt === '馬齡') colMap.age = i;
                            if (txt === '性別') colMap.gender = i;
                            if (txt === '今季獎金') colMap.seasonPrize = i;
                            if (txt === '優先參賽次序') colMap.priority = i;
                            if (txt === '上賽距今日數') colMap.daysSinceLastRun = i;
                            if (txt === '配備') colMap.gear = i;
                            if (txt === '父系') colMap.sire = i;
                            if (txt === '母系') colMap.dam = i;
                        }

                        if (hasFormCol && hasHorseCol) {
                            const secondRowCells = rows.length > 1 ? rows[1].querySelectorAll('td') : [];
                            if (secondRowCells.length >= 10) {
                                const firstCell = secondRowCells[0].textContent.trim();
                                const num = parseInt(firstCell);
                                if (!isNaN(num) && num > 0 && num <= 20) {
                                    targetTable = t;
                                    break;
                                }
                            }
                        }
                    }
                    if (!targetTable) return horses;

                    const hasRatingCol = colMap.rating !== undefined;
                    const rows = targetTable.querySelectorAll('tr');
                    for (let ri = 1; ri < rows.length; ri++) {
                        const cells = rows[ri].querySelectorAll('td');
                        if (cells.length < 10) continue;

                        const horseNoText = cells[0].textContent.trim();
                        const horseNo = parseInt(horseNoText);
                        if (isNaN(horseNo) || horseNo <= 0 || horseNo > 20) continue;

                        const formRaw = cells[1].textContent.trim();
                        const formHistory = formRaw.replace(/[\\/]/g, '-').replace(/\\s+/g, '-').replace(/^-+|-+$/g, '');
                        const horseName = cells[3].textContent.trim();
                        const horseCode = cells[4].textContent.trim();
                        const weight = parseFloat(cells[5].textContent.trim()) || 0;
                        let jockey = cells[6].textContent.trim();

                        let officialRating = null;
                        if (hasRatingCol) {
                            officialRating = parseFloat(cells[colMap.rating].textContent.trim()) || null;
                        } else {
                            const ratingGuess = parseFloat(cells[7].textContent.trim());
                            if (!isNaN(ratingGuess) && ratingGuess > 0 && ratingGuess <= 140) {
                                officialRating = ratingGuess;
                            }
                        }

                        const draw = parseInt(cells[8].textContent.trim()) || 0;
                        let trainer = cells[9].textContent.trim();

                        let declaredWeight = null;
                        if (colMap.declaredWeight !== undefined) {
                            const dwText = cells[colMap.declaredWeight].textContent.trim();
                            const dwVal = parseInt(dwText);
                            if (!isNaN(dwVal) && dwVal > 800 && dwVal < 1500) {
                                declaredWeight = dwVal;
                            }
                        }

                        let weightChange = null;
                        if (colMap.weightChange !== undefined) {
                            const wcText = cells[colMap.weightChange].textContent.trim().replace('+', '').replace('-', '');
                            const wcVal = parseFloat(wcText);
                            if (!isNaN(wcVal)) {
                                const sign = cells[colMap.weightChange].textContent.trim().startsWith('-') ? -1 : 1;
                                weightChange = sign * Math.abs(wcVal);
                            }
                        }

                        let bestTime = null;
                        if (colMap.bestTime !== undefined) {
                            const btText = cells[colMap.bestTime].textContent.trim();
                            if (btText && /^\d{1,2}\.\d{2}\.\d{2}$/.test(btText)) {
                                bestTime = btText;
                            }
                        }

                        let age = null;
                        if (colMap.age !== undefined) {
                            const ageVal = parseInt(cells[colMap.age].textContent.trim());
                            if (!isNaN(ageVal) && ageVal > 0 && ageVal <= 20) {
                                age = ageVal;
                            }
                        }

                        let gender = null;
                        if (colMap.gender !== undefined) {
                            const gText = cells[colMap.gender].textContent.trim();
                            if (['閹', '雄', '雌'].includes(gText)) {
                                gender = gText;
                            }
                        }

                        let seasonPrize = null;
                        if (colMap.seasonPrize !== undefined) {
                            const spText = cells[colMap.seasonPrize].textContent.trim().replace(/,/g, '');
                            const spVal = parseFloat(spText);
                            if (!isNaN(spVal) && spVal >= 0) {
                                seasonPrize = spVal;
                            }
                        }

                        let priority = null;
                        if (colMap.priority !== undefined) {
                            const pText = cells[colMap.priority].textContent.trim();
                            if (pText && pText !== '') {
                                priority = pText;
                            }
                        }

                        let daysSinceLastRun = null;
                        if (colMap.daysSinceLastRun !== undefined) {
                            const dVal = parseInt(cells[colMap.daysSinceLastRun].textContent.trim());
                            if (!isNaN(dVal) && dVal >= 0 && dVal <= 999) {
                                daysSinceLastRun = dVal;
                            }
                        }

                        let gear = null;
                        if (colMap.gear !== undefined) {
                            const gText = cells[colMap.gear].textContent.trim();
                            if (gText && gText !== '') {
                                gear = gText;
                            }
                        }

                        let sire = null;
                        if (colMap.sire !== undefined) {
                            const sText = cells[colMap.sire].textContent.trim();
                            if (sText && sText !== '') {
                                sire = sText;
                            }
                        }

                        let dam = null;
                        if (colMap.dam !== undefined) {
                            const dText = cells[colMap.dam].textContent.trim();
                            if (dText && dText !== '') {
                                dam = dText;
                            }
                        }

                        jockey = jockey.split('(')[0].trim();
                        trainer = trainer.split('(')[0].trim();

                        horses.push({
                            horse_no: horseNo,
                            horse_name: horseName,
                            horse_code: horseCode,
                            draw: draw,
                            weight: weight,
                            jockey: jockey,
                            trainer: trainer,
                            form_history: formHistory,
                            official_rating: officialRating,
                            declared_weight: declaredWeight,
                            weight_change: weightChange,
                            best_time: bestTime,
                            age: age,
                            gender: gender,
                            season_prize: seasonPrize,
                            priority: priority,
                            days_since_last_run: daysSinceLastRun,
                            gear: gear,
                            sire: sire,
                            dam: dam,
                        });
                    }
                    return horses;
                }''')

                if not horses:
                    print(f"    [SKIP] No horses (race may not exist yet)")
                    if race_no > 1:
                        break
                    continue

                race_meta = page.evaluate(r'''() => {
                    const text = document.body.innerText;
                    const lines = text.split('\n');

                    let startIdx = -1;
                    for (let i = 0; i < lines.length; i++) {
                        if (/第\s*\d+\s*場/.test(lines[i])) { startIdx = i; break; }
                    }

                    let endIdx = lines.length;
                    if (startIdx >= 0) {
                        for (let i = startIdx + 1; i < lines.length; i++) {
                            if (lines[i].includes('馬匹編號') || lines[i].includes('排位表')) {
                                endIdx = i; break;
                            }
                        }
                    } else {
                        startIdx = 0;
                    }

                    const block = lines.slice(startIdx, endIdx).join(' ');

                    const distMatch = block.match(/(\d{3,4})米/);
                    const goingMatch = block.match(/好至黏快|好至快地|好至黏地|好地|快地|慢地|軟地|黏地/);
                    const classMatch = block.match(/第[一二三四五六七八九十]+班/);
                    const trackMatch = block.match(/賽道\s*[:：]\s*(草地|全天候跑道| turf |all-weather)/i);

                    return {
                        distance: distMatch ? parseInt(distMatch[1]) : null,
                        going: goingMatch ? goingMatch[0] : null,
                        class_level: classMatch ? classMatch[0] : null,
                        track_course: trackMatch ? trackMatch[1].trim() : null,
                    };
                }''')

                for h in horses:
                    h['win_odds'] = 0
                    h['place_odds'] = 0

                race_data = {
                    'race_id': f"{venue}-{date_path}-{race_no:02d}",
                    'race_date': date_str,
                    'race_no': race_no,
                    'venue': venue,
                    'distance': race_meta.get('distance'),
                    'class_level': race_meta.get('class_level'),
                    'going': race_meta.get('going'),
                    'track_course': race_meta.get('track_course'),
                    'horses': horses,
                }
                all_races.append(race_data)
                print(f"    [OK] {len(horses)} horses | dist={race_meta.get('distance')} going={race_meta.get('going')} class={race_meta.get('class_level')}")

            except Exception as e:
                print(f"    [FAIL] R{race_no}: {e}")
                if race_no > 1:
                    break

        # Second pass: fetch odds from bet.hkjc.com
        print(f"\n  [Odds] Fetching live odds from bet.hkjc.com...")
        odds_url_base = f"https://bet.hkjc.com/ch/racing/wp/{date_str}/{venue}/{{race_no}}"
        for race_data in all_races:
            race_no = race_data['race_no']
            odds_scraped = False

            for attempt in range(3):
                try:
                    page.goto(odds_url_base.format(race_no=race_no), wait_until='domcontentloaded', timeout=20000)
                    try:
                        page.wait_for_selector('.rc-odds-row', timeout=8000)
                    except Exception:
                        page.wait_for_timeout(5000)

                    odds_map = page.evaluate('''() => {
                        const map = {};
                        const rows = document.querySelectorAll('.rc-odds-row');
                        rows.forEach(row => {
                            const cells = row.querySelectorAll('td');
                            if (cells.length >= 8) {
                                const horseNo = parseInt(cells[0].textContent.trim());
                                const winOdds = parseFloat(cells[7].textContent.trim()) || 0;
                                if (!isNaN(horseNo) && horseNo > 0 && winOdds > 1.0) {
                                    map[horseNo] = winOdds;
                                }
                            }
                        });
                        return map;
                    }''')

                    for h in race_data['horses']:
                        if h['horse_no'] in odds_map:
                            h['win_odds'] = odds_map[h['horse_no']]

                    matched = sum(1 for h in race_data['horses'] if h['win_odds'] > 0)
                    if matched > 0:
                        print(f"    [OK] R{race_no}: {matched}/{len(race_data['horses'])} horses with odds")
                        odds_scraped = True
                        break
                    else:
                        print(f"    [RETRY {attempt+1}/3] R{race_no}: 0 horses with odds, retrying...")
                        page.wait_for_timeout(3000)

                except Exception as e:
                    print(f"    [RETRY {attempt+1}/3] R{race_no} odds: {e}")
                    page.wait_for_timeout(2000)

            if not odds_scraped:
                matched = sum(1 for h in race_data['horses'] if h['win_odds'] > 0)
                if matched == 0:
                    print(f"    [FALLBACK] R{race_no}: assigning default odds 10.0 (live scrape failed)")
                    for h in race_data['horses']:
                        h['win_odds'] = 10.0

        browser.close()

    print(f"\n[Scraper] Total: {len(all_races)} races scraped")
    return all_races


# =====================================================================
# Data Validation
# =====================================================================
def validate_scraped_data(races: List[Dict]) -> bool:
    """Validate scraped data quality. Returns True if all checks pass."""
    all_ok = True
    for race in races:
        race_id = race['race_id']
        horses = race['horses']
        n = len(horses)

        if n < 4:
            print(f"  [WARN] {race_id}: only {n} horses (expected >= 4)")
            all_ok = False

        if n > 20:
            print(f"  [WARN] {race_id}: {n} horses exceeds max 20")
            all_ok = False

        horse_nos = sorted(h['horse_no'] for h in horses)
        expected = list(range(1, n + 1))
        if horse_nos != expected:
            print(f"  [WARN] {race_id}: horse numbers {horse_nos} != expected {expected}")
            all_ok = False

        dupes = [x for x in horse_nos if horse_nos.count(x) > 1]
        if dupes:
            print(f"  [WARN] {race_id}: duplicate horse numbers {set(dupes)}")
            all_ok = False

        for h in horses:
            if not h.get('horse_name'):
                print(f"  [WARN] {race_id}: horse #{h['horse_no']} has empty name")
                all_ok = False
            if not h.get('jockey'):
                print(f"  [WARN] {race_id}: horse #{h['horse_no']} ({h.get('horse_name','')}) has empty jockey")
                all_ok = False
            wt = h.get('weight', 0)
            if wt > 0 and (wt < 100 or wt > 145):
                print(f"  [WARN] {race_id}: horse #{h['horse_no']} weight {wt} out of range [100-145]")
                all_ok = False

    if all_ok:
        total = sum(len(r['horses']) for r in races)
        print(f"  [OK] Validation passed: {len(races)} races, {total} horses")
    return all_ok


# =====================================================================
# Write to Supabase
# =====================================================================
def validate_race_data(races: List[Dict]):
    """SAFEGUARD #3: Pre-commit assertion gate - validate data before writing."""
    for race in races:
        race_id = race['race_id']
        horses = race['horses']

        # Check minimum horse count
        if len(horses) < 4:
            raise Exception(f"[VALIDATION FAIL] {race_id}: Only {len(horses)} horses, expected >= 4")

        # Check horse_no uniqueness and range (allow gaps for withdrawn horses)
        horse_nos = [h['horse_no'] for h in horses]
        if len(set(horse_nos)) != len(horses):
            raise Exception(f"[VALIDATION FAIL] {race_id}: Duplicate horse_no detected")
        if any(no < 1 or no > 20 for no in horse_nos):
            raise Exception(f"[VALIDATION FAIL] {race_id}: horse_no out of range: {horse_nos}")

        # Check horse names are not empty
        for h in horses:
            if not h.get('horse_name') or len(h['horse_name']) < 2:
                raise Exception(f"[VALIDATION FAIL] {race_id} H{h['horse_no']:02d}: Empty horse name")
            if not h.get('jockey') or len(h['jockey']) < 2:
                raise Exception(f"[VALIDATION FAIL] {race_id} H{h['horse_no']:02d}: Empty jockey name")

    print(f"  [OK] Validation passed: {len(races)} races, all data integrity checks passed")


def write_to_supabase(supabase: Client, races: List[Dict], dry_run: bool = False):
    if dry_run:
        print("\n[DRY RUN] Would write:")
        for race in races:
            print(f"  {race['race_id']}: {len(race['horses'])} horses")
        return

    # SAFEGUARD #3: Validate before writing
    validate_race_data(races)

    print(f"\n[Write] Writing {len(races)} races to Supabase...")

    # Dynamic jockey/trainer win rates from Supabase history
    jockey_wr, trainer_wr = compute_jockey_trainer_win_rates(supabase)

    has_official_rating = has_column(supabase, "race_runners", "official_rating")
    has_dw_col = has_column(supabase, "race_runners", "declared_weight")
    has_weight_change = has_column(supabase, "race_runners", "weight_change")
    has_best_time = has_column(supabase, "race_runners", "best_time")
    has_gender = has_column(supabase, "race_runners", "gender")
    has_season_prize = has_column(supabase, "race_runners", "season_prize")
    has_priority = has_column(supabase, "race_runners", "priority")
    has_gear = has_column(supabase, "race_runners", "gear")
    has_sire_dam = has_column(supabase, "horses", "sire")
    if has_official_rating:
        print("  [OK] official_rating column found")
    else:
        print("  [WARN] official_rating column missing — skipping (run migration first)")
    if has_dw_col:
        print("  [OK] declared_weight column found")
    new_cols_found = sum([has_weight_change, has_best_time, has_gender, has_season_prize, has_priority, has_gear])
    print(f"  [INFO] {new_cols_found}/6 new feature columns found (weight_change, best_time, gender, season_prize, priority, gear)")
    if has_sire_dam:
        print("  [OK] horses.sire/dam columns found")

    # --- Pass 1: Upsert races + horses, collect horse entries ---
    horse_id_map = {}
    horse_entries_for_dw = []

    for race in races:
        race_id = race['race_id']

        # SAFEGUARD #1: Pre-delete old data for this race
        print(f"  [Purge] Deleting old data for {race_id}...")
        try:
            retry_supabase(lambda rid=race_id: supabase.table('race_runners').delete().eq('race_id', rid).execute())
        except Exception as e:
            print(f"    [WARN] Delete failed: {e}")

        race_row = {
            'race_id': truncate(race_id, 32),
            'race_date': race['race_date'],
            'race_no': race['race_no'],
            'venue': truncate(race['venue'], 4),
            'distance': race.get('distance'),
            'class_level': truncate(race.get('class_level'), 32) if race.get('class_level') else None,
            'going': truncate(validate_going(race.get('going')), 32) if validate_going(race.get('going')) else None,
            'track_course': truncate(race.get('track_course'), 16) if race.get('track_course') else None,
        }
        retry_supabase(lambda: supabase.table('races').upsert(race_row, on_conflict='race_id').execute())

        for horse in race['horses']:
            horse_name = horse['horse_name']
            horse_code = horse.get('horse_code', '')

            # SAFEGUARD #2: Use horse_code as primary identifier
            if horse_code:
                horse_id = truncate(horse_code, 16)
            else:
                horse_id = f"H{len(horse_id_map) + 1:04d}"

            if horse_name not in horse_id_map:
                horse_id_map[horse_name] = horse_id
                horse_row = {
                    'horse_id': horse_id,
                    'horse_name': truncate(horse_name, 64),
                }
                if has_sire_dam:
                    if horse.get('sire'):
                        horse_row['sire'] = truncate(horse['sire'], 64)
                    if horse.get('dam'):
                        horse_row['dam'] = truncate(horse['dam'], 64)
                retry_supabase(lambda hr=horse_row: supabase.table('horses').upsert(hr, on_conflict='horse_id').execute())
            elif has_sire_dam:
                sire = horse.get('sire')
                dam = horse.get('dam')
                if sire or dam:
                    update_row = {'horse_id': horse_id}
                    if sire:
                        update_row['sire'] = truncate(sire, 64)
                    if dam:
                        update_row['dam'] = truncate(dam, 64)
                    retry_supabase(lambda ur=update_row: supabase.table('horses').upsert(ur, on_conflict='horse_id').execute())

            dw = horse.get('declared_weight')
            if dw and has_dw_col:
                horse_entries_for_dw.append({'horse_id': horse_id, 'declared_weight': dw})

    # --- Compute weight_carried_diff from previous declared_weight ---
    weight_diffs = compute_weight_diffs(supabase, horse_entries_for_dw)
    if weight_diffs:
        print(f"  [OK] Computed weight_carried_diff for {len(weight_diffs)} horses")

    # --- Pass 2: Build runner rows with all computed features ---
    all_runner_rows = []

    for race in races:
        race_id = race['race_id']

        for horse in race['horses']:
            horse_name = horse['horse_name']
            horse_code = horse.get('horse_code', '')
            horse_id = horse_id_map.get(horse_name, horse_code[:16] if horse_code else 'UNKNOWN')

            jockey = horse.get('jockey', '')
            jockey = jockey.split('(')[0].strip() if '(' in jockey else jockey
            trainer = horse.get('trainer', '')

            runner_id = f"{race_id}_H{horse['horse_no']:02d}"
            form_history = horse.get('form_history', '')
            official_rating = horse.get('official_rating')

            real_jwr = jockey_wr.get(jockey)
            real_twr = trainer_wr.get(trainer)
            wcd = weight_diffs.get(horse_id, 0.0)

            runner_row = {
                'runner_id': truncate(runner_id, 48),
                'race_id': truncate(race_id, 32),
                'horse_id': horse_id,
                'horse_no': horse['horse_no'],
                'jockey': truncate(jockey, 64),
                'trainer': truncate(trainer, 64),
                'actual_weight': horse.get('weight'),
                'draw': horse.get('draw'),
                'win_odds': horse.get('win_odds', 0),
                'past_rating': official_rating if official_rating else 50.0,
                'recent_form_score': 50.0,
                'jockey_win_rate': real_jwr if real_jwr is not None else 0.10,
                'trainer_win_rate': real_twr if real_twr is not None else 0.10,
                'weight_carried_diff': wcd,
                'rest_days': horse.get('days_since_last_run') or 0,
                'form_history': truncate(form_history, 64) if form_history else None,
            }
            if has_official_rating:
                runner_row['official_rating'] = official_rating if official_rating else None
            if has_dw_col and horse.get('declared_weight'):
                runner_row['declared_weight'] = horse['declared_weight']
            if has_weight_change and horse.get('weight_change') is not None:
                runner_row['weight_change'] = horse['weight_change']
            if has_best_time and horse.get('best_time'):
                runner_row['best_time'] = horse['best_time']
            if has_gender and horse.get('gender'):
                runner_row['gender'] = horse['gender']
            if has_season_prize and horse.get('season_prize') is not None:
                runner_row['season_prize'] = horse['season_prize']
            if has_priority and horse.get('priority'):
                runner_row['priority'] = horse['priority']
            if has_gear and horse.get('gear'):
                runner_row['gear'] = horse['gear']
            all_runner_rows.append(runner_row)

        print(f"  [OK] {race_id}: {len(race['horses'])} runners prepared")

    if all_runner_rows:
        batch_upsert(supabase, 'race_runners', all_runner_rows, 'runner_id')

    print("[Write] Done!")


# =====================================================================
# Auto-detect date and venue
# =====================================================================
def auto_detect_venue(today: datetime) -> str:
    weekday = today.weekday()
    if weekday in (2, 5):
        return 'ST'
    elif weekday in (1, 3, 6):
        return 'HV'
    return None


def detect_venue_from_hkjc(date_str: str) -> Optional[str]:
    """Check HKJC website to determine actual venue for a given date."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    date_slash = date_str.replace('-', '/')
    for venue in ['ST', 'HV']:
        try:
            url = f"https://racing.hkjc.com/racing/information/Chinese/Racing/RaceCard.aspx?RaceDate={date_slash}&Racecourse={venue}&RaceNo=1"
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-gpu'])
                page = browser.new_page()
                page.goto(url, wait_until='domcontentloaded', timeout=20000)
                page.wait_for_timeout(3000)
                horse_count = page.evaluate('''() => {
                    const tables = document.querySelectorAll('table');
                    for (const t of tables) {
                        const rows = t.querySelectorAll('tr');
                        if (rows.length >= 5) return rows.length - 1;
                    }
                    return 0;
                }''')
                browser.close()
                if horse_count > 0:
                    venue_name = '沙田' if venue == 'ST' else '跑馬地'
                    print(f"[AutoDetect] HKJC confirms venue: {venue_name} ({venue}) for {date_str}")
                    return venue
        except Exception as e:
            print(f"[AutoDetect] {venue} check failed: {e}")
            continue
    return None


# =====================================================================
# Race time estimation (HKJC typical schedule)
# =====================================================================
RACE_INTERVALS_MIN = [0, 25, 25, 30, 25, 30, 25, 30, 25, 30, 25, 30]

def estimate_race_times(date_str: str, venue: str, num_races: int = 11) -> List[Dict]:
    """Estimate race start times. Day session ~13:00 (ST), Night session ~19:00 (HV)."""
    from datetime import time as dtime
    d = datetime.strptime(date_str, '%Y-%m-%d').date()
    first_race_time = dtime(19, 0) if venue == 'HV' else dtime(13, 0)
    races = []
    for i in range(num_races):
        offset = sum(RACE_INTERVALS_MIN[:i]) if i < len(RACE_INTERVALS_MIN) else i * 28
        start = datetime.combine(d, first_race_time) + timedelta(minutes=offset)
        races.append({'race_no': i + 1, 'start_time': start})
    return races


# =====================================================================
# Odds-only update (for high-frequency mode — no clear, no full rewrite)
# =====================================================================
def scrape_odds_only(date_str: str, venue: str) -> Dict[int, Dict[int, float]]:
    """Scrape current win_odds for all races. Returns {race_no: {horse_no: win_odds}}."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[FAIL] playwright not installed")
        return {}

    date_path = date_str.replace('-', '')
    base_url = f"https://bet.hkjc.com/ch/racing/wp/{date_str}/{venue}/{{race_no}}"
    all_odds = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-gpu'])
        page = browser.new_page()

        for race_no in range(1, 13):
            url = base_url.format(race_no=race_no)
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=20000)
                try:
                    page.wait_for_selector('.rc-odds-row', timeout=10000)
                except Exception:
                    page.wait_for_timeout(5000)

                odds_data = page.evaluate('''() => {
                    const odds = {};
                    const rows = document.querySelectorAll('.rc-odds-row');
                    rows.forEach(row => {
                        const cells = row.querySelectorAll('td');
                        if (cells.length >= 8) {
                            const horseNo = parseInt(cells[0].textContent.trim());
                            if (!isNaN(horseNo) && horseNo > 0 && horseNo <= 20) {
                                const winOdds = parseFloat(cells[7].textContent.trim()) || 0;
                                odds[horseNo] = winOdds;
                            }
                        }
                    });
                    return odds;
                }''')

                if odds_data:
                    all_odds[race_no] = odds_data
                    print(f"  [Odds] R{race_no}: {len(odds_data)} horses")
                else:
                    if race_no > 1:
                        break

            except Exception as e:
                print(f"  [Odds] R{race_no} failed: {e}")
                if race_no > 1:
                    break

        browser.close()

    return all_odds


def update_odds_in_supabase(supabase: Client, date_str: str, venue: str, odds_map: Dict[int, Dict[int, float]]):
    """Update win_odds in existing race_runners without clearing data."""
    date_path = date_str.replace('-', '')
    total_updated = 0
    total_skipped = 0

    for race_no, horse_odds in odds_map.items():
        race_id = f"{venue}-{date_path}-{int(race_no):02d}"
        for horse_no, win_odds in horse_odds.items():
            # CRITICAL: Never overwrite with invalid odds (0, null, < 1.0)
            if win_odds is None or win_odds <= 1.0:
                total_skipped += 1
                continue

            runner_id = f"{race_id}_H{int(horse_no):02d}"
            try:
                retry_supabase(lambda: supabase.table('race_runners').update({
                    'win_odds': float(win_odds),
                }).eq('runner_id', runner_id[:48]).execute())
                total_updated += 1
            except Exception as e:
                print(f"    [WARN] {runner_id}: {e}")

    print(f"  [OK] Updated {total_updated} odds entries, skipped {total_skipped} invalid")
    return total_updated


# =====================================================================
# Main
# =====================================================================
def main():
    parser = argparse.ArgumentParser(description='HKJC Race Data Scraper + Supabase Upsert')
    parser.add_argument('--date', help='Race date (YYYY-MM-DD). Auto-detects today (HKT) if omitted.')
    parser.add_argument('--venue', choices=['ST', 'HV', 'auto'], help='Venue code. "auto" detects from HKJC. Auto-detects by weekday if omitted.')
    parser.add_argument('--dry-run', action='store_true', help='Scrape but do not write to Supabase')
    parser.add_argument('--fetch-live', action='store_true', help='Auto-detect date/venue and write live data to Supabase')
    parser.add_argument('--clear-only', action='store_true', help='Only clear old data, do not scrape')
    parser.add_argument('--odds-only', action='store_true', help='Scrape and update odds only (no clear, no full rewrite)')
    args = parser.parse_args()

    today = datetime.now(HKT)
    date_str = args.date or today.strftime('%Y-%m-%d')

    if args.venue == 'auto':
        venue = detect_venue_from_hkjc(date_str)
        if not venue:
            venue = auto_detect_venue(today)
            print(f"[AutoDetect] HKJC detection failed, falling back to weekday mapping: {venue}")
    elif args.venue:
        venue = args.venue
    else:
        detected = detect_venue_from_hkjc(date_str)
        venue = detected or auto_detect_venue(today)
        if detected:
            pass
        else:
            print(f"[AutoDetect] Using weekday-based venue: {venue}")

    if not venue:
        print(f"[INFO] No race day detected for {date_str}. Nothing to do.")
        sys.exit(0)

    print("=" * 60)
    print(f"HKJC Auto Scraper - {date_str} {venue}")
    print(f"Trigger: {'--fetch-live' if args.fetch_live else 'manual'}")
    print("=" * 60)

    supabase = get_supabase_client()
    if not supabase and not args.dry_run:
        sys.exit(1)

    if supabase and not args.dry_run and not args.clear_only and not args.odds_only:
        clear_old_data(supabase, date_str, venue)

    if args.clear_only:
        print("\n[OK] Clear only done!")
        return

    if args.odds_only:
        print(f"\n[Odds-Only] Scraping live odds for {date_str} {venue}...")
        odds_map = scrape_odds_only(date_str, venue)
        if odds_map:
            update_odds_in_supabase(supabase, date_str, venue, odds_map)
        else:
            print("[WARN] No odds scraped")
        return

    races = scrape_hkjc_races(date_str, venue)

    if not races:
        print("\n[WARN] No races scraped. No races today or HKJC page structure changed.")
        sys.exit(0)

    print(f"\n[Validate] Checking data quality...")
    validate_scraped_data(races)

    write_to_supabase(supabase, races, dry_run=args.dry_run)

    total_horses = sum(len(r['horses']) for r in races)
    print(f"\n{'=' * 60}")
    print(f"SUMMARY")
    print(f"  Races scraped:  {len(races)}")
    print(f"  Total horses:   {total_horses}")
    print(f"  Date:           {date_str}")
    print(f"  Venue:          {venue}")
    print(f"{'=' * 60}")

    if not args.dry_run:
        print("\nNext: python scripts/benter_model.py supabase")


if __name__ == '__main__':
    main()
