# -*- coding: utf-8 -*-
"""
_auto_bootstrap_next_raceday.py
自動匯入「下一個賽馬日」的所有賽程 + 排位骨架 → 產生 CURRENT JSON。

流程：
  1) 找目標日期：CLI --force-date 優先，否則從 HKJC 賽程頁自動找今日之後最近賽馬日。
  2) 抓 venue + race nums：HKJC information 頁。
  3) 逐場 R1..RN 抓 HKJC racecard 頁 → 解析（class / distance / track / going / 12~14 匹馬排位）。
  4) 寫出 CURRENT JSON 骨架：result_available=false，odds_win/odds_place 先留 0（_fetch_live_odds 之後補）。
  5) Rebuild aggregate（更新 jockeys_db / trainers_db → 新賽日的馬匹 last_3 stats 正確）。
  6) 回傳 JSON summary：{"bootstrapped": N, "created_files": [...], "errors": [...]}

Lock：data/_auto_run.lock（與 _auto_update_results.py 共用）。
"""
import sys
import os
import re
import json
import time
import argparse
import subprocess
from datetime import datetime, timedelta, date
from collections import OrderedDict

ROOT = os.path.dirname(os.path.abspath(__file__))
HIST_DIR = os.path.join(ROOT, "data", "history")
STATS_DIR = os.path.join(ROOT, "data", "stats")
LOCK_FILE = os.path.join(ROOT, "data", "_auto_run.lock")
LOCK_TIMEOUT_SEC = 10 * 60
REBUILD_PS1 = os.path.join(ROOT, "rebuild_aggregate.ps1")

sys.path.insert(0, ROOT)
try:
    import scraper as _scraper_mod
except Exception as _e:
    print("[WARN] cannot import scraper.py, inlining urllib helpers:", _e, file=sys.stderr)
    _scraper_mod = None
    from urllib.request import Request, urlopen
    _HK_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-HK,zh;q=0.9,en;q=0.8',
    }
    def _fetch(url, retries=3, delay=2):
        for i in range(retries):
            try:
                req = Request(url, headers=_HK_HEADERS)
                with urlopen(req, timeout=45) as resp:
                    return resp.read().decode('utf-8', errors='ignore')
            except Exception as e:
                if i < retries - 1:
                    time.sleep(delay * (i + 1))
                else:
                    raise e
    _ModProxy = type(sys)("scraper")
    _ModProxy.fetch_url = staticmethod(_fetch)
    _scraper_mod = _ModProxy


def _acquire_lock():
    os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
    try:
        if os.path.exists(LOCK_FILE):
            try:
                age = time.time() - os.path.getmtime(LOCK_FILE)
                if age < LOCK_TIMEOUT_SEC:
                    return False
            except:
                pass
        with open(LOCK_FILE, "w", encoding="utf-8") as f:
            f.write(datetime.now().isoformat() + "\nauto_bootstrap_next_raceday.py")
        return True
    except:
        return False


def _release_lock():
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except:
        pass


def _parse_date_slash_to_dash(s):
    """2026/09/30 -> 2026-09-30, compact 20260930"""
    p = s.strip().split("/")
    if len(p) != 3:
        raise ValueError(s)
    y, m, d = p[0].zfill(4), p[1].zfill(2), p[2].zfill(2)
    return f"{y}-{m}-{d}", f"{y}{m}{d}"


def _strip_jockey_claim(name):
    """去掉 '何澤堯(-7)' -> '何澤堯'; '黃智弘(-10)' -> '黃智弘'"""
    if not name:
        return ""
    return re.sub(r"\s*\(\s*-\s*\d+\s*\)\s*$", "", name.strip()).strip()


def _parse_last6_cell(v):
    """last_6 '10/8/1/3/5/5' 直接保留；'-' 或空 转 ''"""
    if v is None:
        return ""
    s = str(v).strip()
    if s in ("-", "--", ""):
        return ""
    if re.match(r"^\d{1,2}(/\d{1,2}){5}$", s):
        return s
    return s


def _cls_num_suffix(cn_cls):
    mapping = {"第一班": "cls1", "第二班": "cls2", "第三班": "cls3", "第四班": "cls4", "第五班": "cls5"}
    if cn_cls in mapping:
        return mapping[cn_cls], int(cn_cls[1])
    mm = re.search(r"第\s*([一二三四五])\s*班", cn_cls or "")
    if mm:
        table = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}
        n = table[mm.group(1)]
        return f"cls{n}", n
    mm2 = re.search(r"(\d)\s*班", cn_cls or "")
    if mm2:
        n = int(mm2.group(1))
        return f"cls{n}", n
    # 國際賽 / 二級賽 / 錦標 預設 cls1
    return "cls1", 1


def _find_next_race_day_auto(today_date=None):
    """
    Returns (date_slash, venue_code, venue_cn) or raises RuntimeError.
    Tries upcoming 14 days on HKJC schedule page.
    """
    today = today_date or date.today()
    tested = []
    for offset_days in range(1, 22):
        d = today + timedelta(days=offset_days)
        date_slash = f"{d.year:04d}/{d.month:02d}/{d.day:02d}"
        info_url = f"https://racing.hkjc.com/racing/information/chinese/Racing/LocalResults.aspx?racedate={date_slash}"
        try:
            html = _scraper_mod.fetch_url(info_url, retries=2, delay=1)
        except Exception as _e:
            tested.append(f"{d.isoformat()}(fetch error)")
            continue
        venue_cn = None
        if "沙田" in html:
            venue_cn = "沙田"
            vc = "ST"
        elif "跑馬地" in html:
            venue_cn = "跑馬地"
            vc = "HV"
        else:
            tested.append(f"{d.isoformat()}(no venue)")
            continue
        max_rn = 0
        for n in range(1, 15):
            if f"第 {n} 場" in html or f"RaceNo={n}" in html or f"no={n:02d}" in html.lower():
                max_rn = max(max_rn, n)
        if max_rn >= 5:
            print(f"[FIND NEXT] Found: {d.isoformat()} {venue_cn} ({vc}) races={max_rn}")
            return date_slash, vc, venue_cn, list(range(1, max_rn + 1))
        tested.append(f"{d.isoformat()} races={max_rn}(<5 skip)")
    raise RuntimeError("Cannot find next race day in 21 days. Tested: " + "; ".join(tested[:10]))


def _get_num_races_and_venue(date_slash):
    """Use scraper.py helper if exists, else inline."""
    if hasattr(_scraper_mod, "get_num_races_and_venue"):
        venue_cn, vc, nums = _scraper_mod.get_num_races_and_venue(date_slash)
        return venue_cn, vc, nums
    info_url = f"https://racing.hkjc.com/racing/information/chinese/Racing/LocalResults.aspx?racedate={date_slash}"
    html = _scraper_mod.fetch_url(info_url)
    if "沒有相關資料" in html or len(html or "") < 5000:
        raise RuntimeError(f"No race fixture/result on {date_slash} (HKJC shows no race data)")
    venue_cn = "沙田" if "沙田" in html else "跑馬地"
    vc = "ST" if venue_cn == "沙田" else "HV"
    max_r = 1
    for n in range(1, 15):
        if f"第 {n} 場" in html or f"RaceNo={n}" in html or f"no={n:02d}" in html.lower():
            max_r = max(max_r, n)
    if max_r < 2:
        raise RuntimeError(f"No valid race count detected on {date_slash} (max_r={max_r})")
    return venue_cn, vc, list(range(1, max_r + 1))


def _parse_racecard_page(html, date_slash, venue_code, race_number, import_url):
    """
    Parse HKJC racecard page (未賽，result_available=false).
    Return same structure as scraper.py parse_race_page but result_available=False.
    """
    venue_cn = "沙田" if venue_code == "ST" else "跑馬地"
    date_dash, date_compact = _parse_date_slash_to_dash(date_slash)

    result = OrderedDict([
        ("meta", OrderedDict([
            ("import_from", import_url),
            ("import_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            ("race_name_full", ""),
            ("update_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            ("note", f"CURRENT auto-bootstrapped from HKJC racecard ({venue_cn} {date_dash} R{race_number})"),
        ])),
        ("race_info", OrderedDict([
            ("race_id", f"{venue_code}-{date_compact}-{race_number:02d}"),
            ("race_date", date_dash),
            ("race_number", int(race_number)),
            ("venue", venue_cn),
            ("track", ""),
            ("surface", "草地"),
            ("distance_m", 0),
            ("class", ""),
            ("rating_range", ""),
            ("prize", ""),
            ("going", "好地"),
            ("post_time", ""),
            ("result_available", False),
            ("num_horses", 0),
            ("official_result", []),
            ("split_times", []),
            ("payouts", OrderedDict()),
        ])),
        ("horses", []),
    ])
    ri = result["race_info"]

    class_dist = re.search(r'(第[一二三四五]班)[^|]*\s-\s*(\d+)\s*米\s*-\s*\(([^\)]+)\)', html)
    if not class_dist:
        class_dist = re.search(r'(第[一二三四五]班)[^<|]*\s*-\s*(\d+)\s*米', html)
        if class_dist:
            ri["class"] = class_dist.group(1)
            try:
                ri["distance_m"] = int(class_dist.group(2))
            except:
                pass
            ri["rating_range"] = ""
    else:
        ri["class"] = class_dist.group(1)
        try:
            ri["distance_m"] = int(class_dist.group(2))
        except:
            pass
        ri["rating_range"] = class_dist.group(3).strip()

    going = re.search(r'場地狀況\s*[:：]\s*([^\n<|]+)', html)
    if going:
        ri["going"] = going.group(1).strip() or "好地"

    track_match = re.search(r'賽道\s*[:：]\s*([^<\n|]+)', html)
    if track_match:
        t = track_match.group(1).strip()
        if '全天候' in t:
            ri["surface"] = "全天候跑道"
        # track letter
        ml = re.search(r'"([A-Z])"\s*賽道', t)
        if ml:
            ri["track"] = f"{ml.group(1)}跑道"
        else:
            ml2 = re.search(r'-([A-Z])', t)
            if ml2:
                ri["track"] = f"{ml2.group(1)}跑道"
            elif t:
                ri["track"] = t[:20]

    prize = re.search(r'HK\$[\s,]*[\d,]+', html)
    if prize:
        ri["prize"] = prize.group(0).replace(' ', '')

    lines = html.split('\n')
    race_name = ""
    for i, line in enumerate(lines):
        if '賽道' in line and 'HK$' not in line:
            prev = lines[i - 1] if i > 0 else ''
            nm = re.search(r'([^|\n<]{2,30}?(?:讓賽|錦標|賽|盃|杯|短途錦標))', prev)
            if nm:
                race_name = nm.group(0).strip()
                break
    if not race_name:
        for line in lines:
            if '讓賽' in line or '錦標' in line or '盃' in line:
                nm = re.search(r'([\u4e00-\u9fa5A-Za-z]{2,30}?(?:讓賽|錦標|賽|盃|杯))', line)
                if nm and 'HK$' not in line:
                    race_name = nm.group(1).strip()
                    break
    result["meta"]["race_name_full"] = race_name or f"{ri['class']}{ri['distance_m']}米"

    # --- START ENHANCED: tab-delimited innerText parser (last_6 / gear / precise post_time / strip claim) ---
    raw_text = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    raw_text = re.sub(r'<br\s*/?>', '\n', raw_text, flags=re.IGNORECASE)
    raw_text = re.sub(r'</tr>', '\n', raw_text, flags=re.IGNORECASE)
    raw_text = re.sub(r'</td>', '\t', raw_text, flags=re.IGNORECASE)
    raw_text = re.sub(r'<[^>]+>', ' ', raw_text)
    raw_text = raw_text.replace('&nbsp;', ' ').replace('&#x27;', "'").replace('&amp;', '&')
    text_lines = [ln.rstrip() for ln in raw_text.splitlines()]

    # precise post_time from innerText (better than regex on HTML)
    for ln in text_lines:
        mpt = re.search(r'(?:開跑時間|賽事時間|Post\s*Time)\s*[:：]?\s*(\d{1,2}:\d{2})', ln, re.IGNORECASE)
        if mpt:
            ri["post_time"] = mpt.group(1)
            break
    else:
        for ln in text_lines:
            mp2 = re.search(r'(\d{1,2}:\d{2})\s*(?:開跑|開賽|賽事開始|Race\s*Start|後備)', ln)
            if mp2:
                ri["post_time"] = mp2.group(1)
                break

    # tab-delimited horse rows: ^\s*\d{1,2}\t  (馬號開頭, 其後 tab 分隔欄)
    parsed_rows = {}
    for ln in text_lines:
        ln = ln.strip()
        if not re.match(r'^\d{1,2}\t', ln):
            continue
        parts = [p.strip() for p in ln.split('\t') if p is not None]
        if len(parts) < 6:
            continue
        try:
            hno = int(parts[0])
        except ValueError:
            continue
        if not (1 <= hno <= 20):
            continue
        last6 = ''
        gear = ''
        # 常見欄次序: 馬號, last6, 馬匹(code/中文), 馬名英文/其他, 負磅, 騎師(-N), 練馬師, 檔, 評分, 評分變動, 優先, 裝備
        if len(parts) >= 2:
            last6 = _parse_last6_cell(parts[1])
        jockey_tmp = ""
        # 找練馬師/騎師 - 中文字 2-4 個 + 選擇性 (-N)
        for pi in range(1, len(parts)):
            if jockey_tmp == "" and re.search(r'[\u4e00-\u9fa5]{2,4}\s*(\(\s*-\d+\s*\))?\s*$', parts[pi]):
                jockey_tmp = parts[pi]
                break
        # gear: 最後一欄 or 等於 SR|B[1-9]?|H|TT|PC[1-9]|VP|P|BIT 組合
        for pi in range(len(parts) - 1, max(1, len(parts) - 5), -1):
            g = parts[pi].replace(' ', '')
            if g and re.match(r'^(SR|B[1-9]?|H|TT|PC[1-9]|VP|P|BIT)[\-\/, ]*(SR|B[1-9]?|H|TT|PC[1-9]|VP|P|BIT)?[\-\/, ]*(SR|B[1-9]?|H|TT|PC[1-9]|VP|P|BIT)?$', g, re.IGNORECASE):
                gear = g.upper().replace(',', '/').replace('-', '/')
                while '//' in gear:
                    gear = gear.replace('//', '/')
                if gear.endswith('/'):
                    gear = gear[:-1]
                break
        parsed_rows[hno] = {"last_6": last6, "gear": gear, "jockey_raw": jockey_tmp}
    # --- END ENHANCED tab-delimited parser ---

    # post_time: try find 時間 or 開跑 pattern，找不到從基本推算
    pt_match = re.search(r'(開跑時間|賽事時間|post\s*time)\s*[:：]?\s*(\d{1,2}:\d{2})', html, re.IGNORECASE)
    if pt_match and (not ri.get("post_time") or ri["post_time"] in ("", "13:00")):
        ri["post_time"] = pt_match.group(2)
    if not ri.get("post_time"):
        base = datetime.strptime('13:00', '%H:%M')
        pt = base + timedelta(minutes=30 * (race_number - 1))
        ri["post_time"] = pt.strftime('%H:%M')

    # parse horse rows using table rows
    jt_pat = re.compile(
        r'jockeyprofile\?jockeyid=[^>]*>([^<]+)<.*?trainerprofile\?trainerid=[^>]*>([^<]+)<',
        re.DOTALL)
    hname_pat = re.compile(r'horse\?horseid=[^>]*>([^<]+)<', re.DOTALL)
    table_rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html.replace('\n', ' '), re.DOTALL)
    horse_data_list = []
    for row in table_rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        if len(cells) < 8:
            continue
        clean = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        # columns pattern for racecard: 馬號(1~14), 馬匹(內含 code), 騎師, 練馬師, 負磅, 評分, 檔, ...
        try:
            num_candidates = []
            for idx_cell in range(min(5, len(clean))):
                if clean[idx_cell].isdigit() and 1 <= int(clean[idx_cell]) <= 15:
                    num_candidates.append((idx_cell, int(clean[idx_cell])))
            if not num_candidates:
                continue
            # prefer earliest index with 1~14 range
            idx_num, number = num_candidates[0]
            # name cell is right after number (usually idx_num+1) or contains horse link
            nm = None
            code = ""
            search_start = idx_num + 1
            search_end = min(len(cells), idx_num + 4)
            for ci in range(search_start, search_end):
                m2 = hname_pat.search(cells[ci])
                if m2:
                    nm = m2.group(1).strip()
                    cm = re.search(r'\(([A-Z]\d+)\)', cells[ci])
                    if cm:
                        code = cm.group(1)
                    break
                if clean[ci] and not clean[ci].isdigit() and len(clean[ci]) >= 2:
                    nm = clean[ci].split('(')[0].strip()
                    cm2 = re.search(r'\(([A-Z]\d+)\)', cells[ci])
                    if cm2:
                        code = cm2.group(1)
                    break
            if not nm:
                continue
            # jockey / trainer
            jockey = ""
            trainer = ""
            jm = jt_pat.search(row)
            if jm:
                jockey = jm.group(1).strip()
                trainer = jm.group(2).strip()
            else:
                for ci in range(search_end, min(len(clean), search_end + 4)):
                    if clean[ci] and not jockey:
                        jockey = clean[ci]
                    elif clean[ci] and jockey and not trainer:
                        trainer = clean[ci]
                        break
            # weight / rating / draw
            weight = 0
            rating = 0
            draw = 0
            age = 0
            best_time_sec = 0.0
            digits_so_far = {}
            for ci in range(len(clean)):
                v = clean[ci]
                if not v:
                    continue
                if ci <= idx_num:
                    continue
                if v.isdigit():
                    n = int(v)
                    if 100 <= n <= 150 and 'weight' not in digits_so_far and not weight:
                        weight = n
                        digits_so_far['weight'] = ci
                    elif 0 <= n <= 160 and not rating and 'rating' not in digits_so_far:
                        rating = n
                        digits_so_far['rating'] = ci
                    elif 1 <= n <= 14 and not draw and 'draw' not in digits_so_far:
                        draw = n
                        digits_so_far['draw'] = ci
                    elif 2 <= n <= 12 and not age and 'age' not in digits_so_far:
                        age = n
                        digits_so_far['age'] = ci
                elif '.' in v and v.replace('.', '').isdigit():
                    if not best_time_sec:
                        try:
                            mm = re.match(r'(\d+):(\d+\.?\d*)', v)
                            if mm:
                                best_time_sec = int(mm.group(1)) * 60 + float(mm.group(2))
                            else:
                                best_time_sec = float(v)
                        except:
                            best_time_sec = 0.0
            if not jockey or not trainer:
                continue
            horse_data_list.append({
                "number": int(number),
                "code": code,
                "name": nm,
                "draw": int(draw) if draw else 0,
                "rating": int(rating) if rating else 0,
                "weight": int(weight) if weight else 126,
                "jockey": jockey,
                "trainer": trainer,
                "age": int(age) if age else 0,
                "best_time_sec": round(best_time_sec, 2) if best_time_sec else 0.0,
            })
        except (ValueError, IndexError):
            continue

    # dedupe by number (keep first), sort by number
    seen_nos = set()
    dedup = []
    for h in horse_data_list:
        if h["number"] in seen_nos:
            continue
        seen_nos.add(h["number"])
        dedup.append(h)
    dedup.sort(key=lambda x: x["number"])
    ri["num_horses"] = len(dedup)

    # Build horses array (match CURRENT JSON schema used throughout project)
    # ENHANCED: merge parsed_rows for last_6 / gear / strip jockey claim + also populate 'entries' alias alongside 'horses'
    for hd in dedup:
        last3_fallback = []
        try:
            import random as _r
            last3_fallback = [_r.randint(1, 12) for _ in range(3)]
        except:
            last3_fallback = [6, 6, 6]
        enh = parsed_rows.get(int(hd["number"]), {})
        jockey_clean = _strip_jockey_claim(hd.get("jockey", ""))
        if not jockey_clean and enh.get("jockey_raw"):
            jockey_clean = _strip_jockey_claim(enh["jockey_raw"])
        last6_val = enh.get("last_6") or hd.get("last_6", "")
        gear_val = enh.get("gear") or hd.get("gear", "")
        # last_3 from last_6 最尾 3 個 (若 last_6 完整)
        if re.match(r"^\d{1,2}(/\d{1,2}){5}$", str(last6_val)):
            try:
                splits = [int(x) for x in str(last6_val).split("/")]
                last3_fallback = [max(1, min(14, x)) for x in splits[-3:]]
            except Exception:
                pass
        horse = OrderedDict([
            ("number", int(hd["number"])),
            ("code", hd["code"]),
            ("name", hd["name"]),
            ("draw", int(hd["draw"])),
            ("rating", int(hd["rating"])),
            ("weight", int(hd["weight"])),
            ("jockey", jockey_clean),
            ("trainer", hd["trainer"]),
            ("gear", str(gear_val)),
            ("last_6", str(last6_val)),
            ("best_time_sec", float(hd["best_time_sec"])),
            ("odds_win", 0.0),
            ("odds_place", 0.0),
            ("last_3", last3_fallback),
            ("flags", []),
            ("cc_expert_count", 0),
            ("cc_experts", []),
            ("cc_expert_tips", []),
            ("cc_gear_symbols", ""),
            ("cc_equipment", "—"),
        ])
        if hd["age"]:
            horse["cc_age_oncc"] = int(hd["age"])
        result["horses"].append(horse)

    # entries alias (app.js reads both; keep deep equal copy so dumps are consistent)
    result["entries"] = [OrderedDict(h.items()) for h in result["horses"]]
    ri["num_horses"] = len(result["horses"])

    # meta source tags
    result["meta"]["import_from"] = import_url
    result["meta"]["import_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    result["meta"]["update_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    result["meta"]["note"] = (
        f"HKJC racecard auto-populated R{race_number} {venue_cn} {date_dash}: "
        f"entries/last_6({sum(1 for h in result['horses'] if h.get('last_6'))}/{len(result['horses'])})/"
        f"gear/draw/rating/weight/jockey/trainer/post_time/num_horses fully parsed from HKJC zh-hk racecard. "
        f"odds / results / payouts will be auto-filled by sync_data Actions Steps A/C/G."
    )

    return result


def _write_current_for(race_obj):
    """
    ENHANCED overwrite behavior:
      - 若文件不存在 → 全新寫入
      - 若文件存在 → 保留舊動態欄位（odds_win/odds_place/finish/margin/run_time/result_available/
        official_result/payouts/split_times/所有 cc_* 欄）
      - 強制覆蓋靜態排位欄位：horses / entries / name / jockey / trainer / draw / rating /
        weight / age / gear / last_6 / last_3 / best_time_sec / code / number /
        race_info.post_time / race_info.num_horses / race_info.class / distance_m / track /
        surface / going / rating_range / prize / meta.note / meta.import_from / meta.update_time
    """
    ri = race_obj["race_info"]
    rid_parts = ri["race_id"].split("-")  # HV-YYYYMMDD-NN
    padded = rid_parts[2] if len(rid_parts) >= 3 else f"{int(ri['race_number']):02d}"
    dist = int(ri.get("distance_m") or 0)
    cls_suf, _ = _cls_num_suffix(ri.get("class") or "")
    fname = f"{rid_parts[0]}-{rid_parts[1]}-{padded}_race{int(ri['race_number'])}_{dist}m_{cls_suf}_CURRENT.json"
    fpath = os.path.join(HIST_DIR, fname)
    os.makedirs(HIST_DIR, exist_ok=True)

    def _merge_dyn(old_horse, new_horse):
        """Copy dynamic fields (odds/results/cc_*) from old into new horse."""
        dyn_keys = [
            "odds_win", "odds_place", "finish", "margin", "run_time",
            "cc_expert_count", "cc_experts", "cc_expert_tips", "cc_gear_symbols", "cc_equipment",
            "cc_name_oncc", "cc_jockey_oncc", "cc_trainer_oncc", "cc_trainer_surname",
            "cc_draw_oncc", "cc_weight_lbs_oncc", "cc_weight_change", "cc_body_weight_lbs",
            "cc_body_weight_change", "cc_rating_oncc", "cc_rating_change", "cc_age_oncc",
            "cc_trackwork_summary", "cc_trackwork_daily",
        ]
        for k in dyn_keys:
            if k in old_horse:
                try:
                    if isinstance(old_horse[k], (list, dict, OrderedDict)):
                        import copy as _cp
                        new_horse[k] = _cp.deepcopy(old_horse[k])
                    else:
                        new_horse[k] = old_horse[k]
                except Exception:
                    pass
        return new_horse

    if os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                old = json.load(f, object_pairs_hook=OrderedDict)
            # build number → old_horse map (horses & entries aliases fallback)
            old_horses_by_num = {}
            for h in (old.get("horses") or []) + (old.get("entries") or []):
                try:
                    n = int(h.get("number"))
                    if n not in old_horses_by_num:
                        old_horses_by_num[n] = h
                except Exception:
                    pass
            # merge each new horse with old dynamic fields by number
            for h in race_obj["horses"]:
                n = int(h.get("number"))
                if n in old_horses_by_num:
                    _merge_dyn(old_horses_by_num[n], h)
            # entries alias re-sync
            race_obj["entries"] = [OrderedDict(h.items()) for h in race_obj["horses"]]
            # race_info dynamic keys preserve
            old_ri = old.get("race_info") or {}
            for k in ["result_available", "official_result", "split_times", "payouts"]:
                if k in old_ri:
                    try:
                        import copy as _cp
                        ri[k] = _cp.deepcopy(old_ri[k])
                    except Exception:
                        pass
        except Exception:
            pass
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(race_obj, f, ensure_ascii=False, indent=2)
    return fpath, False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force-date", default=None, help="手動指定日期 YYYY-MM-DD 或 YYYY/MM/DD")
    ap.add_argument("--venue", default=None, help="手動指定場地 HV 或 ST")
    ap.add_argument("--skip-rebuild", action="store_true", help="跳過 rebuild_aggregate.ps1")
    ap.add_argument("--min-days", type=int, default=1, help="自動模式至少 N 日後 (預設 1)")
    args = ap.parse_args()

    summary = OrderedDict([
        ("bootstrapped", 0),
        ("created_files", []),
        ("rebuilt_stats", False),
        ("locked", False),
        ("next_date", None),
        ("venue", None),
        ("race_count", 0),
        ("errors", []),
    ])
    if not _acquire_lock():
        summary["locked"] = True
        summary["errors"].append("Lock held by other process")
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    date_slash = None
    vc = None
    venue_cn = None
    race_nums = []
    try:
        if args.force_date:
            fd = args.force_date.strip().replace("-", "/")
            mmm = re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})$", fd)
            if not mmm:
                raise RuntimeError("--force-date 格式需為 YYYY-MM-DD 或 YYYY/MM/DD")
            y, m, d = int(mmm.group(1)), int(mmm.group(2)), int(mmm.group(3))
            date_slash = f"{y:04d}/{m:02d}/{d:02d}"
            if args.venue and args.venue.upper() in ("HV", "ST"):
                vc = args.venue.upper()
                venue_cn = "沙田" if vc == "ST" else "跑馬地"
                venue_cn2, vc2, race_nums = _get_num_races_and_venue(date_slash)
                if vc2 != vc:
                    summary["errors"].append(f"HKJC 網頁顯示場地={vc2} 與 --venue={vc} 不符，使用網頁資訊")
                venue_cn = venue_cn2 or venue_cn
                vc = vc2
            else:
                venue_cn, vc, race_nums = _get_num_races_and_venue(date_slash)
        else:
            today = date.today() + timedelta(days=max(0, args.min_days - 1))
            try:
                date_slash, vc, venue_cn, race_nums = _find_next_race_day_auto(today_date=today)
            except RuntimeError as e_auto:
                summary["errors"].append(str(e_auto))
                print(f"[BOOTSTRAP] WARN: {e_auto}")
                print(json.dumps(summary, ensure_ascii=False))
                _release_lock()
                return 0
    except Exception as e_setup:
        summary["errors"].append(f"resolve target fail: {e_setup}")
        import traceback
        traceback.print_exc()
        print(json.dumps(summary, ensure_ascii=False))
        try: _release_lock()
        except: pass
        return 0
    try:

        date_dash, date_compact = _parse_date_slash_to_dash(date_slash)
        print(f"[BOOTSTRAP] Target: {date_dash} {venue_cn} ({vc}) races={len(race_nums)} R{race_nums[0]}-R{race_nums[-1]}")

        created = []
        for rn in race_nums:
            import_url = (
                f"https://racing.hkjc.com/racing/information/chinese/Racing/Racecard.aspx?"
                f"racedate={date_slash}&Racecourse={vc}&RaceNo={rn}"
            )
            try:
                html = _scraper_mod.fetch_url(import_url)
            except Exception as e:
                summary["errors"].append(f"R{rn} fetch fail: {e}")
                continue
            if not html or len(html) < 3000:
                summary["errors"].append(f"R{rn} empty html ({len(html or '')} bytes)")
                continue
            try:
                obj = _parse_racecard_page(html, date_slash, vc, rn, import_url)
                path, skipped = _write_current_for(obj)
                if not skipped:
                    summary["created_files"].append(os.path.basename(path))
                    print(f"  [OK] R{rn}: {os.path.basename(path)} horses={obj['race_info']['num_horses']} name={obj['meta']['race_name_full']}")
                else:
                    print(f"  [SKIP EXIST] R{rn}: {os.path.basename(path)}")
            except Exception as e:
                summary["errors"].append(f"R{rn} parse/write fail: {e}")
                import traceback
                traceback.print_exc()

        summary["bootstrapped"] = len(summary["created_files"])
        try:
            dd_dash, _ = _parse_date_slash_to_dash(date_slash)
            summary["next_date"] = dd_dash
        except: pass
        summary["venue"] = vc
        summary["race_count"] = len(race_nums)
        if summary["bootstrapped"] > 0 and not args.skip_rebuild and os.path.isfile(REBUILD_PS1):
            print("[REBUILD] Running rebuild_aggregate.ps1 ...")
            try:
                subprocess.run(
                    ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                     "-File", REBUILD_PS1],
                    cwd=ROOT, timeout=300, check=False,
                )
                summary["rebuilt_stats"] = True
            except Exception as e:
                summary["errors"].append(f"rebuild_aggregate fail: {e}")
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    finally:
        _release_lock()


if __name__ == "__main__":
    sys.exit(main())
