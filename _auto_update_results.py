# -*- coding: utf-8 -*-
"""
_auto_update_results.py
掃描 data/history 所有 _CURRENT.json。
針對 race_date < 今日 且 result_available=false 的賽事：
  (1) 從 racing.hkjc.com localresults + racecard 抓 official_result/finish/payouts
  (2) IN-PLACE 更新 CURRENT JSON（保留 cc_* / odds_* / ai_score）
  (3) RENAME CURRENT -> 歷史檔（與 data/history 其他檔案命名一致）
  (4) 若有任何更新 -> 自動跑 rebuild_aggregate.ps1

Dependency: 可直接 import scraper.py 作為模組（fetch_url / parse_race_page）。
Lock: data/_auto_run.lock（與 _auto_bootstrap_next_raceday.py 共用，防止 scheduler 重入）。
Return (stdout 最後一行 JSON):
  {"updated": N, "renamed": N, "new_stats": true|false, "errors": [...]}
"""
import sys
import os
import re
import json
import time
import subprocess
from datetime import datetime
from collections import OrderedDict

ROOT = os.path.dirname(os.path.abspath(__file__))
HIST_DIR = os.path.join(ROOT, "data", "history")
STATS_DIR = os.path.join(ROOT, "data", "stats")
LOCK_FILE = os.path.join(ROOT, "data", "_auto_run.lock")
LOCK_TIMEOUT_SEC = 10 * 60
REBUILD_PS1 = os.path.join(ROOT, "rebuild_aggregate.ps1")

sys.path.insert(0, ROOT)
try:
    import scraper as _scraper  # reuse fetch_url / parse_race_page
except Exception as _importE:
    print("[WARN] cannot import scraper.py, inlining helpers. Err:", _importE, file=sys.stderr)
    _scraper = None

from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

if _scraper is None:
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-HK,zh;q=0.9,en;q=0.8',
    }
    def _fetch_url(url, retries=3, delay=2):
        for i in range(retries):
            try:
                req = Request(url, headers=HEADERS)
                with urlopen(req, timeout=45) as resp:
                    return resp.read().decode('utf-8', errors='ignore')
            except Exception as e:
                if i < retries - 1:
                    time.sleep(delay * (i + 1))
                else:
                    raise e
    _scraper_mod = type(sys)("scraper")
    _scraper_mod.fetch_url = staticmethod(_fetch_url)
    _scraper = _scraper_mod
    # parse_race_page 簡化版（只取 official_result + payouts，不生成 horses）
    def _parse_race_page_result_only(html, race_date_dash, venue_code, race_number):
        """Minimal parse for finished race: return {official_result, payouts, horses_finish_map}"""
        out = {
            "official_result": [],
            "payouts": {},
            "finish_map": {},
            "margin_map": {},
            "run_time_map": {},
        }
        jockey_trainer_pattern = re.compile(
            r'jockeyprofile\?jockeyid=[^>]*>([^<]+)<.*?trainerprofile\?trainerid=[^>]*>([^<]+)<', re.DOTALL)
        horse_name_pattern = re.compile(r'horse\?horseid=[^>]*>([^<]+)<', re.DOTALL)
        table_rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html.replace('\n', ' '), re.DOTALL)
        horse_data_list = []
        for row in table_rows:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            if len(cells) >= 12:
                clean_cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
                try:
                    finish = int(clean_cells[0]) if clean_cells[0].isdigit() else None
                    number = int(clean_cells[1]) if clean_cells[1].isdigit() else None
                    if finish and number and finish >= 1 and number >= 1:
                        name_cell = cells[2]
                        nm = horse_name_pattern.search(name_cell)
                        name = nm.group(1).strip() if nm else clean_cells[2].split('(')[0].strip()
                        code_match = re.search(r'\(([A-Z]\d+)\)', name_cell)
                        code = code_match.group(1) if code_match else ''
                        jt_match = jockey_trainer_pattern.search(row)
                        if jt_match:
                            jockey = jt_match.group(1).strip()
                            trainer = jt_match.group(2).strip()
                        else:
                            jockey = clean_cells[3].strip() if len(clean_cells) > 3 else ''
                            trainer = clean_cells[4].strip() if len(clean_cells) > 4 else ''
                        margin = clean_cells[8].strip() if len(clean_cells) > 8 else ''
                        run_time = clean_cells[10].strip() if len(clean_cells) > 10 else ''
                        if margin == '---' or finish == 1:
                            margin_display = '---'
                        else:
                            margin_display = margin if margin else ''
                        horse_data_list.append({
                            'finish': finish, 'number': number, 'name': name, 'code': code,
                            'jockey': jockey, 'trainer': trainer,
                            'margin': margin_display, 'run_time': run_time,
                        })
                except (ValueError, IndexError):
                    continue
        horse_data_list.sort(key=lambda x: x['finish'])
        for hd in horse_data_list:
            out["official_result"].append({
                'finish': hd['finish'], 'code': hd['code'], 'number': hd['number'],
                'name': hd['name'], 'jockey': hd['jockey'], 'trainer': hd['trainer'],
                'margin': hd['margin'], 'run_time': hd['run_time']
            })
            out["finish_map"][str(hd['code'])] = hd['finish']
            out["margin_map"][str(hd['code'])] = hd['margin']
            out["run_time_map"][str(hd['code'])] = hd['run_time']

        payout_area = re.search(r'派彩.*?(?=派彩備註|賽事沿途|$)', html, re.DOTALL)
        payout_text = payout_area.group(0) if payout_area else html
        def parse_amount(s):
            s2 = s.replace(',', '').replace('HK$', '').replace('$', '').strip()
            try: return float(s2)
            except: return 0.0
        win_match = re.search(r'獨贏[^|]*\|\s*([\d,]+)\s*\|[^|]*\|\s*([\d,.]+)\s*\|', payout_text)
        if win_match:
            out["payouts"]["獨贏"] = {"combo": win_match.group(1).strip(), "pay": parse_amount(win_match.group(2))}
        place_entries = []
        for pm in re.finditer(r'位置[^|]*\|(?:[^|]*\|)?\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|', payout_text):
            place_entries.append({"combo": pm.group(1).strip(), "pay": parse_amount(pm.group(2))})
        if place_entries:
            out["payouts"]["位置"] = place_entries[:3] if len(place_entries) >= 3 else place_entries
        qin_match = re.search(r'連贏[^|]*\|\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|', payout_text)
        if qin_match:
            out["payouts"]["連贏"] = {"combo": qin_match.group(1).strip(), "pay": parse_amount(qin_match.group(2))}
        qpl_entries = []
        for pm in re.finditer(r'位置Q[^|]*\|(?:[^|]*\|)?\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|', payout_text):
            qpl_entries.append({"combo": pm.group(1).strip(), "pay": parse_amount(pm.group(2))})
        if qpl_entries:
            out["payouts"]["位置Q"] = qpl_entries[:3] if len(qpl_entries) >= 3 else qpl_entries
        dch_match = re.search(r'二重彩[^|]*\|\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|', payout_text)
        if dch_match:
            out["payouts"]["二重彩"] = {"combo": dch_match.group(1).strip(), "pay": parse_amount(dch_match.group(2))}
        tch_match = re.search(r'三重彩[^|]*\|\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|', payout_text)
        if tch_match:
            out["payouts"]["三重彩"] = {"combo": tch_match.group(1).strip(), "pay": parse_amount(tch_match.group(2))}
        tt_match = re.search(r'單T[^|]*\|\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|', payout_text)
        if tt_match:
            out["payouts"]["單T"] = {"combo": tt_match.group(1).strip(), "pay": parse_amount(tt_match.group(2))}
        q4_match = re.search(r'四連環[^|]*\|\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|', payout_text)
        if q4_match:
            out["payouts"]["四連環"] = {"combo": q4_match.group(1).strip(), "pay": parse_amount(q4_match.group(2))}
        q4ch_match = re.search(r'四重彩[^|]*\|\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|', payout_text)
        if q4ch_match:
            out["payouts"]["四重彩"] = {"combo": q4ch_match.group(1).strip(), "pay": parse_amount(q4ch_match.group(2))}
        return out
    _scraper_mod.parse_result_only = staticmethod(_parse_race_page_result_only)


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
            f.write(datetime.now().isoformat() + "\nauto_update_results.py")
        return True
    except:
        return False


def _release_lock():
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except:
        pass


def _raceid_parts(race_id):
    """HV-20260923-01 -> (HV, '2026/09/23', '2026-09-23', 1)"""
    try:
        p = race_id.split("-")
        venue = p[0]
        ymd = p[1]
        y = ymd[:4]; m = ymd[4:6]; d = ymd[6:8]
        rn = int(p[2])
        slash = f"{y}/{m}/{d}"
        dash = f"{y}-{m}-{d}"
        return venue, slash, dash, rn
    except Exception as e:
        raise ValueError(f"Invalid race_id: {race_id}: {e}")


def _cls_to_suffix(cls_str):
    """第五班 -> cls5, 第四班 -> cls4, ..., 第一班 -> cls1, 二級賽 / 國際賽 -> cls1"""
    if not cls_str:
        return "cls0"
    m = re.search(r"第?([一二三四五])班", cls_str)
    if m:
        mapping = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}
        return f"cls{mapping[m.group(1)]}"
    m2 = re.search(r"(\d)\s*班", cls_str)
    if m2:
        return f"cls{m2.group(1)}"
    # 錦標 / 讓賽 / 二級賽
    return "cls1"


def _make_history_filename(race_info, race_no_padded):
    """
    與其他歷史檔一致：HV-YYYYMMDD-NN_race{n}_{dist}m_cls{X}.json
    從 race_info.race_id + distance_m + class 建。
    """
    venue, _, _, rn = _raceid_parts(race_info["race_id"])
    ymd = race_info["race_id"].split("-")[1]
    dist = int(race_info.get("distance_m") or 0)
    cls_suf = _cls_to_suffix(race_info.get("class") or "")
    return f"{venue}-{ymd}-{race_no_padded}_race{rn}_{dist}m_{cls_suf}.json"


def _find_current_files():
    out = []
    if not os.path.isdir(HIST_DIR):
        return out
    for fn in sorted(os.listdir(HIST_DIR)):
        if fn.endswith("_CURRENT.json"):
            out.append(os.path.join(HIST_DIR, fn))
    return out


def _fetch_result_for(race_info):
    """
    Return (None|dict{official_result,payouts,finish_map,margin_map,run_time_map})
    """
    try:
        venue, date_slash, date_dash, rn = _raceid_parts(race_info["race_id"])
    except Exception as e:
        print(f"  [SKIP] bad race_id: {race_info.get('race_id')} err={e}", file=sys.stderr)
        return None
    venue_url_code = "ST" if venue == "ST" else "HV"
    racecard_url = (
        f"https://racing.hkjc.com/racing/information/chinese/Racing/LocalResults.aspx?"
        f"RaceDate={date_slash}&Racecourse={venue_url_code}&RaceNo={rn}"
    )
    print(f"  [FETCH] R{rn} {venue} {date_dash} -> {racecard_url[:90]}...")
    try:
        html = _scraper.fetch_url(racecard_url)
    except (URLError, HTTPError) as e:
        print(f"  [FETCH FAIL] HTTP err: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  [FETCH FAIL] {e}", file=sys.stderr)
        return None
    if not html or len(html) < 2000:
        print(f"  [FETCH FAIL] empty html ({len(html or '')} bytes)", file=sys.stderr)
        return None
    try:
        if hasattr(_scraper, "parse_race_page"):
            parsed = _scraper.parse_race_page(html, date_slash, venue, rn, racecard_url)
            return {
                "official_result": parsed["race_info"]["official_result"],
                "payouts": parsed["race_info"].get("payouts", {}),
                "finish_map": {str(h["code"]): int(h.get("finish", 99)) for h in parsed["horses"] if h.get("code")},
                "margin_map": {str(h["code"]): (parsed["race_info"]["official_result"][i]["margin"]
                            if i < len(parsed["race_info"]["official_result"]) else "")
                            for i, h in enumerate(parsed["horses"]) if h.get("code")},
                "run_time_map": {str(h["code"]): (parsed["race_info"]["official_result"][i]["run_time"]
                               if i < len(parsed["race_info"]["official_result"]) else "")
                               for i, h in enumerate(parsed["horses"]) if h.get("code")},
            }
        else:
            return _scraper.parse_result_only(html, date_dash, venue, rn)
    except Exception as e:
        print(f"  [PARSE FAIL] {e}", file=sys.stderr)
        return None


def main():
    summary = OrderedDict([
        ("updated", 0), ("renamed", 0), ("new_stats", False),
        ("errors", []), ("locked", False), ("updated_races", [])
    ])
    if not _acquire_lock():
        summary["locked"] = True
        summary["errors"].append("Lock held by other process")
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    try:
        today = datetime.now().date()
        currents = _find_current_files()
        print(f"[AUTO-UPDATE] Scanned {len(currents)} CURRENT files. Today={today.isoformat()}")
        to_rename = []  # [(src_path, dst_path)]
        any_updated = False
        for fp in currents:
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                summary["errors"].append(f"read JSON fail {os.path.basename(fp)}: {e}")
                continue
            ri = data.get("race_info") or {}
            ra = ri.get("result_available")
            if ra:
                continue
            rd_str = ri.get("race_date", "")
            try:
                rd = datetime.strptime(rd_str, "%Y-%m-%d").date()
            except Exception:
                summary["errors"].append(f"bad race_date {os.path.basename(fp)}: {rd_str}")
                continue
            if rd >= today:
                continue  # 未到賽日
            rid = ri.get("race_id", "?")
            print(f"[TASK] {os.path.basename(fp)} (race_id={rid})")
            result = _fetch_result_for(ri)
            if not result or not result.get("official_result"):
                summary["errors"].append(f"no result fetched for {rid}")
                continue
            # in-place update
            ri["result_available"] = True
            ri["official_result"] = result["official_result"]
            ri["payouts"] = result.get("payouts", {})
            meta = data.get("meta") or {}
            if "meta" not in data:
                data["meta"] = meta
            meta["result_update_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            meta["update_time"] = meta["result_update_time"]
            fm = result.get("finish_map") or {}
            mm = result.get("margin_map") or {}
            tm = result.get("run_time_map") or {}
            for h in data.get("horses", []):
                code = str(h.get("code") or "")
                if code in fm:
                    h["finish"] = int(fm[code])
                if code in mm and mm[code]:
                    h["margin"] = mm[code]
                if code in tm and tm[code]:
                    h["run_time"] = tm[code]
            try:
                with open(fp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                summary["errors"].append(f"write fail {os.path.basename(fp)}: {e}")
                continue
            summary["updated"] += 1
            summary["updated_races"].append(rid)
            any_updated = True
            # plan rename (execute after all updates OK, idempotent)
            padded = ri.get("race_id", "").split("-")[-1]  # 01..09..10
            if not padded or not re.match(r"^\d{2}$", padded):
                padded = f"{int(ri.get('race_number') or 1):02d}"
            dst_name = _make_history_filename(ri, padded)
            dst_path = os.path.join(HIST_DIR, dst_name)
            if os.path.abspath(dst_path) != os.path.abspath(fp):
                if os.path.exists(dst_path):
                    print(f"  [RENAME SKIP] target exists: {dst_name}")
                else:
                    to_rename.append((fp, dst_path))
        # execute rename
        for (src, dst) in to_rename:
            try:
                os.rename(src, dst)
                summary["renamed"] += 1
                print(f"  [RENAMED] {os.path.basename(src)} -> {os.path.basename(dst)}")
            except Exception as e:
                summary["errors"].append(f"rename fail {os.path.basename(src)}: {e}")
        # rebuild aggregate if any updated
        if any_updated and os.path.isfile(REBUILD_PS1):
            print("[REBUILD] Running rebuild_aggregate.ps1 ...")
            try:
                subprocess.run(
                    ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                     "-File", REBUILD_PS1],
                    cwd=ROOT, timeout=300, check=False
                )
                summary["new_stats"] = True
            except Exception as e:
                summary["errors"].append(f"rebuild_aggregate fail: {e}")
        summary["updated_races"] = summary["updated_races"][:50]
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    finally:
        _release_lock()


if __name__ == "__main__":
    sys.exit(main())
