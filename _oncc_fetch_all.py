#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_oncc_fetch_all.py — 自動收集 racing.on.cc 所有有用賽馬資料
  使用情景（sync_data.ps1 Step J）：
    ① 首頁 / discover 自動 extract 下一賽馬日 URL list (最後來料 / 晨操摘要 / 排位差異 / 馬匹評論 / 退馬表)
    ② fallback URL pattern generate (rjfavg / rjifoa / rjmorc 三套固定 pattern)
    ③ parse 每頁內容 → extract cc_expert_count / cc_experts / cc_expert_tips / cc_trackwork_summary / cc_trackwork_daily / cc_draw_oncc / cc_jockey_oncc / cc_weight_change / cc_* 所有兼容欄
    ④ merge 入 race JSON entries → 絕對唔覆蓋靜態 12 欄 / odds_* / official_result / Step I supplement 8+ 欄 / 原有 cc_* 舊值（如果新值 count 唔夠舊多）
    ⑤ sync 入 public/data/history mirror

  CLI:
    python _oncc_fetch_all.py --date 2026-09-27 --venue ST --race-nums-csv 1,5,8,11
    python _oncc_fetch_all.py --url "https://racing.on.cc/racing/fav/current/rjfavg0001x0.html"
    python _oncc_fetch_all.py --min-days 0 (auto detect next raceday)
    python _oncc_fetch_all.py --date 2026-09-27 --venue ST --dry-run --push
"""
import sys, os, re, json, argparse, subprocess
from collections import OrderedDict
from urllib import request as urlreq, parse as urlparse, error as urlerr

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

ZH_ONCC_BASE = "https://racing.on.cc/racing"
ONCC_INDEX = "https://racing.on.cc/"
FALLBACK_CURRENT = {
    "expert_fav": ZH_ONCC_BASE + "/fav/current/rjfavg{:04d}x0.html",
    "barrier":    ZH_ONCC_BASE + "/ifo/current/rjifoa{:04d}x0.html",
    "trackwork":  ZH_ONCC_BASE + "/mor/current/rjmorc{:04d}x0.html",
    "results":    ZH_ONCC_BASE + "/ifo/current/rjifom{:04d}x0.html",
}

MAX_RACES_PER_DAY = 14
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 HorseKingBot/1.0"

STATIC_CORE_KEEP = {  # =============== 絕對唔覆蓋（靜態 core 12 欄 + 衍生 last3/best_time） ===============
    "name","jockey","trainer","draw","rating","weight","gear","last_6","last_3","number","code",
    "best_time_sec","best_time_src","places","starts","wins"
}
DYNAMIC_CORE_KEEP_PREFIXES = (  # =============== 絕對唔覆蓋（動態 odds/results/cc_* 舊值 / Step I supplement 8+ 新欄 除外） ===============
    "odds_","payouts","split_times","official_result","result_info","betfair","pool_"
)
SUPPLEMENT_OVERWRITE_PREFIXES = ("cc_",)  # =============== Step J 會覆蓋（on.cc 專屬欄） ===============

try:
    import _auto_bootstrap_next_raceday as _boot
except Exception:
    _boot = None


def write_json(p, d):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)


def read_json(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f, object_pairs_hook=OrderedDict)


def _date_to_slash(s):
    return s.replace("-", "/")


def _http_get(url, timeout=18):
    req = urlreq.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})
    try:
        with urlreq.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            charset = "utf-8"
            ct = r.headers.get("Content-Type", "")
            mc = re.search(r"charset\s*=\s*([\w\-]+)", ct, re.I)
            if mc: charset = mc.group(1).lower()
            try:
                text = raw.decode(charset, errors="replace")
            except Exception:
                text = raw.decode("big5hkscs", errors="replace")
            return text, len(raw)
    except (urlerr.URLError, urlerr.HTTPError, TimeoutError, OSError) as e:
        return None, f"ERR:{type(e).__name__}:{str(e)[:80]}"


def _discover_next_raceday_oncc():
    """
    從 racing.on.cc 首頁 /racing/index.html discover:
      - detect next racedate (YYYY/MM/DD) + venue (ST/HV) + num_races
      - discover expert_fav / barrier / trackwork URL map 每場
    失敗 → safe return None
    """
    info = {"date_slash": None, "date_dash": None, "venue": None, "race_count": None, "urls": {}}
    candidates = [ONCC_INDEX, ZH_ONCC_BASE + "/"]
    html = None
    for u in candidates:
        t, _ = _http_get(u)
        if t: html = t; break
    if not html:
        return None
    m_date = re.search(r"(\d{4})[\/\-年](\d{1,2})[\/\-月](\d{1,2})", html)
    if m_date:
        info["date_slash"] = f"{m_date.group(1)}/{int(m_date.group(2)):02d}/{int(m_date.group(3)):02d}"
        info["date_dash"] = info["date_slash"].replace("/", "-")
    m_venue = re.search(r"(沙田|跑馬地|SHATIN|HAPPY\s*VALLEY)", html, re.I)
    if m_venue:
        v = m_venue.group(1).upper()
        info["venue"] = "HV" if ("VALLEY" in v or "跑馬地" in m_venue.group(1)) else "ST"
    rn = re.findall(r"第\s*(\d{1,2})\s*場", html)
    if rn:
        info["race_count"] = max(int(x) for x in rn)
    # URL 提取：rjfavgXXXX / rjifoaXXXX / rjmorcXXXX pattern
    for key in ("expert_fav", "barrier", "trackwork"):
        pattern_map = {
            "expert_fav": r"rjfavg(\d{4})[a-z0-9]*\.html",
            "barrier":    r"rjifoa(\d{4})[a-z0-9]*\.html",
            "trackwork":  r"rjmorc(\d{4})[a-z0-9]*\.html",
        }
        matches = re.findall(pattern_map[key], html, re.I)
        if matches:
            info["urls"][key] = list(sorted(set(int(x) for x in matches)))
    if info["date_slash"] and info["venue"] and info["race_count"]:
        return info
    return None


def _resolve_date_venue_nums(args):
    """
    Returns: (date_slash, date_dash, vc, race_nums)
    Priority: args.url > args.date/venue > --min-days auto detect > on.cc homepage discover > fallback R1..11
    """
    if args.url:
        m = re.search(r"(rj\w+)(\d{4})[a-z0-9]*\.html", args.url, re.I)
        if m:
            num = int(m.group(2))
            # 呢個 pattern 通常係 current month race，日期需要靠 detect
            if _boot:
                try:
                    cn, vc, nums = _boot._get_num_races_and_venue(None)
                    d = _boot._find_next_race_day_auto(args.min_days)
                    if d:
                        date_slash = _date_to_slash(d)
                        return date_slash, date_slash.replace("/","-"), vc or "ST", [num]
                except Exception:
                    pass
            return "2099/01/01", "2099-01-01", "ST", [num]
    if args.date:
        date_slash = _date_to_slash(args.date)
        date_dash = date_slash.replace("/","-")
        vc = None
        if args.venue: vc = args.venue.upper()
        if not vc and _boot:
            try:
                _cn, vc2, _nums = _boot._get_num_races_and_venue(date_slash)
                vc = vc2
            except Exception:
                pass
        if not vc:
            vc = "ST"
            print("[WARN] 未 detect 到 venue → fallback ST")
        race_nums = None
        if args.race_no:
            race_nums = [int(args.race_no)]
        elif args.race_nums_csv:
            race_nums = [int(x) for x in args.race_nums_csv.split(",") if x.strip()]
        else:
            if _boot:
                try:
                    _cn, _vc, nums = _boot._get_num_races_and_venue(date_slash)
                    race_nums = nums
                except Exception:
                    race_nums = None
            if not race_nums:
                race_nums = list(range(1, 12))
                print(f"[WARN] 未 detect nums → fallback R1..R{race_nums[-1]}")
        return date_slash, date_dash, vc, race_nums
    # auto detect
    d = None
    if _boot:
        try:
            d = _boot._find_next_race_day_auto(args.min_days)
        except Exception:
            d = None
    if d:
        date_slash = _date_to_slash(d)
        date_dash = d
        try:
            _cn, vc, nums = _boot._get_num_races_and_venue(date_slash)
            return date_slash, date_dash, vc, nums
        except Exception:
            pass
    disc = _discover_next_raceday_oncc()
    if disc and disc["date_slash"] and disc["venue"]:
        rn = disc["race_count"] or 11
        return disc["date_slash"], disc["date_dash"], disc["venue"], list(range(1, rn+1))
    print("[ERROR] 所有 detect 都失敗 → 請手動 --date YYYY-MM-DD --venue ST/HV")
    sys.exit(2)


def _extract_oncc_races_list_from_page(html_text):
    """ barrier / trackwork page 有馬號+馬名+各種 cc 欄 → extract list[dict] """
    result = OrderedDict()
    # 1. Extract tab / whitespace separated rows（on.cc racecard 頁面都有馬號開頭嘅 row）
    lines = [ln.strip() for ln in html_text.replace("\r","\n").split("\n") if ln.strip()]
    # 2. HTML <tr> 拆 rows（robuster 就 loop <tr>，但有時 table 用 tabs）
    trs = re.findall(r"<tr[^>]*>(.*?)</tr>", html_text, flags=re.I | re.S)
    if not trs:
        # fallback：tab-delimited innerText rows
        for ln in lines:
            if re.match(r"^\d{1,2}\s+[\u4e00-\u9fa5]", ln):
                cells = [c.strip() for c in ln.split("\t") if c.strip()]
                if 3 <= len(cells) <= 30:
                    hno = int(re.match(r"^(\d{1,2})", cells[0]).group(1))
                    result[hno] = {"cells": cells, "raw": ln}
        return result
    for tr in trs:
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.I | re.S)
        if not tds: continue
        tds_plain = [re.sub(r"<[^>]+>", "", t).replace("&nbsp;"," ").replace("\u3000"," ").strip() for t in tds]
        tds_plain = [t for t in tds_plain if t]
        if not tds_plain: continue
        # 頭 cell 馬號？
        first = tds_plain[0]
        m_num = re.match(r"^(\d{1,2})", first)
        if m_num:
            hno = int(m_num.group(1))
            if 1 <= hno <= MAX_RACES_PER_DAY:
                result[hno] = {"cells": tds_plain, "tds_html": tds}
    return result


def _parse_barrier_page_to_cc(html_text, race_no):
    """ barrier page → extract cc_draw_oncc / cc_jockey_oncc / cc_trainer_surname / cc_weight_change / cc_equipment """
    rows = _extract_oncc_races_list_from_page(html_text)
    out = OrderedDict()
    for hno, row in rows.items():
        cells = row["cells"]
        info = OrderedDict()
        # on.cc barrier 欄順序通常：馬號(+馬名) | 檔 | 騎師 | 負磅 | 評分 | 裝備 | 練馬師
        # 直接掃 cells 找 pattern
        for i, c in enumerate(cells):
            if not info.get("cc_name_oncc") and re.match(r"^\d{1,2}\s*[\u4e00-\u9fa5]", c):
                mn = re.sub(r"^\d{1,2}\s*", "", c).strip()
                if mn: info["cc_name_oncc"] = mn
            if re.match(r"^([1-9]|1[0-4])$", c) and 1 <= len(cells[i:]) > 0:
                try:
                    dr = int(c)
                    if 1 <= dr <= 14: info["cc_draw_oncc"] = dr
                except: pass
            if re.search(r"\([\-\s]?\d\)$", c) and len(c) <= 8:
                info["cc_jockey_oncc"] = re.sub(r"\s*\([\-\s]?\d\)\s*$", "", c).strip()
            if re.match(r"^[\u4e00-\u9fa5]$", c) and len(c) == 1 and len(info) >= 3:
                info["cc_trainer_oncc"] = c
            m_w = re.match(r"^([\+\-]?\d{1,3})$", c)
            if m_w and not info.get("cc_weight_change"):
                v = int(m_w.group(1))
                if -40 <= v <= 40: info["cc_weight_change"] = v
            if re.search(r"(SR|H|TT|PC|VP|BIT|BL|CP|EO|F\d*|G|HO|XB|O|PP|R\d*|SH|NB|L\d*|B\d*|—)", c) and len(c) <= 30:
                if not info.get("cc_equipment"): info["cc_equipment"] = c
        out[hno] = info
    return out


def _parse_trackwork_page_to_cc(html_text, race_no):
    """ trackwork page → cc_trackwork_summary + cc_trackwork_daily + cc_body_weight_change """
    rows = _extract_oncc_races_list_from_page(html_text)
    out = OrderedDict()
    for hno, row in rows.items():
        cells = row["cells"]
        info = OrderedDict()
        # Summary = cells 最尾個 long text cell（有「從化開操 / 踱步 / 快跳 / 游水 / 泥閘 / 草閘」呢啲 pattern）
        summary = None
        for c in cells:
            if len(c) >= 20 and re.search(r"開操|踱步|快跳|游水|泥閘|草閘|彈閘|從化", c):
                summary = c
                break
        if summary: info["cc_trackwork_summary"] = summary
        # daily (6 欄 7-9 / 10-13 / 14-16 / 17-20 / 21-21 / 22-22)
        daily = OrderedDict()
        keys_daily = ["7-9","10-13","14-16","17-20","21","22"]
        # cells 中 2-4 words 短 cell（< 20 chars）且唔係馬號/檔/評分 → 就 daily
        shorts = [c for c in cells if 1 <= len(c) <= 24 and not re.match(r"^[\d\-\+]{1,5}$", c) and not re.search(r"開操|踱步", c)]
        for i, k in enumerate(keys_daily):
            if i < len(shorts): daily[k] = shorts[i]
        if daily: info["cc_trackwork_daily"] = daily
        out[hno] = info
    return out


def _parse_expert_fav_page_to_cc(html_text, race_no):
    """ expert_fav page → cc_expert_count / cc_experts / cc_expert_tips (ranked) """
    out = OrderedDict()
    # extract table rows：每個專家有頭馬/位置/排名 pick
    rows = _extract_oncc_races_list_from_page(html_text)
    # 另一個 pattern：專家名 × 馬號 grid（page 上方會有一堆 中文字專家名）
    expert_names = list(OrderedDict.fromkeys(re.findall(r"[\u4e00-\u9fa5]{2,4}(?:先生|太)?", html_text)))
    expert_names = [e for e in expert_names if len(e) <= 5]
    # 掃每隻馬：有多少專家 pick，pick 第幾名
    per_horse = OrderedDict()
    # pattern： <td> 專家名 </td><td>N</td>  ... <td>N</td> (pick 名次)
    trs = re.findall(r"<tr[^>]*>(.*?)</tr>", html_text, flags=re.I | re.S)
    for tr in trs:
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.I | re.S)
        if len(tds) < 5: continue
        plain = [re.sub(r"<[^>]+>", "", t).replace("&nbsp;"," ").strip() for t in tds]
        plain = [x for x in plain if x]
        if len(plain) < 4: continue
        # 頭 cell 可能係專家名，然後尾 N 個 cell 每隻馬 pick rank (1/2/3/4/--)
        if len(plain[0]) <= 5 and re.match(r"^[\u4e00-\u9fa5]+$", plain[0]):
            expert = plain[0]
            picks = plain[1:]
            for idx, rank_s in enumerate(picks):
                hno = idx + 1
                if hno > MAX_RACES_PER_DAY: break
                m_rank = re.match(r"^(\d)", rank_s)
                if not m_rank: continue
                rank = int(m_rank.group(1))
                if rank < 1 or rank > 6: continue
                bucket = per_horse.setdefault(hno, {"count": 0, "experts": [], "tips": []})
                bucket["count"] += 1
                if expert not in bucket["experts"]: bucket["experts"].append(expert)
                bucket["tips"].append({"expert": expert, "rank": rank})
    for hno, b in per_horse.items():
        info = OrderedDict()
        info["cc_expert_count"] = int(b["count"])
        if b["experts"]: info["cc_experts"] = b["experts"]
        if b["tips"]: info["cc_expert_tips"] = b["tips"]
        out[hno] = info
    return out


def _find_race_json(date_dash, vc, race_no):
    """ 返回 race JSON 檔案 full path / public mirror path """
    history = os.path.join(ROOT, "data", "history")
    public_history = os.path.join(ROOT, "public", "data", "history")
    patterns = [
        f"{vc}-{date_dash.replace('-','')}-R{race_no:02d}.json",
        f"{vc}-{date_dash.replace('-','')}-{race_no:02d}_",
    ]
    src = pub = None
    if os.path.isdir(history):
        for fn in sorted(os.listdir(history)):
            if fn.startswith(f"{vc}-{date_dash.replace('-','')}-{race_no:02d}_") and fn.endswith(".json"):
                src = os.path.join(history, fn)
                break
    if src is None and os.path.isdir(history):
        for fn in sorted(os.listdir(history)):
            if fn.startswith(patterns[0]):
                src = os.path.join(history, fn)
                break
    if src and os.path.isdir(public_history):
        pub = os.path.join(public_history, os.path.basename(src))
        if not os.path.isfile(pub): pub = None
    return src, pub


def _merge_cc_into_horse(horse_old, cc_info_new):
    """ cc_info_new dict → merge 入 horse_old，嚴格規則：
        ① STATIC_CORE_KEEP 唔碰
        ② DYNAMIC_CORE_KEEP_PREFIXES (odds_* / official_result / ...) 唔碰
        ③ cc_*:
            - cc_expert_count 新 >= 舊 → overwrite
            - 其他 cc_* → 舊值空先寫
    """
    if not cc_info_new: return
    for k, v in cc_info_new.items():
        if k in STATIC_CORE_KEEP: continue
        if any(k.startswith(p) for p in DYNAMIC_CORE_KEEP_PREFIXES): continue
        if not any(k.startswith(p) for p in SUPPLEMENT_OVERWRITE_PREFIXES): continue  # 只 accept cc_ 開頭
        if k == "cc_expert_count":
            old_c = horse_old.get(k)
            if not isinstance(old_c, int) or v >= old_c:
                horse_old[k] = v
        else:
            old_v = horse_old.get(k)
            if old_v in (None, "", 0, [], {}, "—"):
                horse_old[k] = v


def run_for_raceday(date_slash, date_dash, vc, race_nums, dry_run=False):
    summary = OrderedDict([
        ("date", date_slash), ("venue", vc), ("races", race_nums),
        ("fetched", OrderedDict()), ("errors", []), ("horses_with_cc", 0),
        ("expert_horses_total", 0), ("tw_horses_total", 0), ("barrier_horses_total", 0),
    ])
    fetched_globals = {}
    urls_global_by_race = {rn: OrderedDict() for rn in race_nums}
    # Step A: generate URLs per race (fallback pattern + fallback discover homepage extracted nums)
    for rn in race_nums:
        for key, tpl in (("expert_fav", 0), ("barrier", 0), ("trackwork", 0)):
            urls_global_by_race[rn][key] = FALLBACK_CURRENT[key].format(rn)
    # Step B: fetch + parse per race
    horses_merged_any = set()
    for rn in race_nums:
        per_race_cc = OrderedDict()  # hno → merged cc dict
        for key, url in urls_global_by_race[rn].items():
            html, meta = _http_get(url, timeout=20)
            fetch_key = f"R{rn:02d}_{key}"
            if not html:
                summary["errors"].append(f"{fetch_key}: {meta}")
                summary["fetched"][fetch_key] = "FAIL"
                continue
            try:
                if key == "expert_fav":
                    parsed = _parse_expert_fav_page_to_cc(html, rn)
                    label = "expert"
                    for hno, info in parsed.items():
                        c = per_race_cc.setdefault(hno, OrderedDict())
                        c.update(info)
                elif key == "barrier":
                    parsed = _parse_barrier_page_to_cc(html, rn)
                    label = "barrier"
                    for hno, info in parsed.items():
                        c = per_race_cc.setdefault(hno, OrderedDict())
                        c.update(info)
                elif key == "trackwork":
                    parsed = _parse_trackwork_page_to_cc(html, rn)
                    label = "trackwork"
                    for hno, info in parsed.items():
                        c = per_race_cc.setdefault(hno, OrderedDict())
                        c.update(info)
                else:
                    parsed = {}
                    label = key
                summary["fetched"][fetch_key] = f"OK rows={len(parsed)} bytes={len(html)}"
            except Exception as e:
                summary["errors"].append(f"{fetch_key}: parser {type(e).__name__}:{str(e)[:120]}")
                summary["fetched"][fetch_key] = "PARSE_FAIL"
                continue
        if not per_race_cc:
            continue
        src, pub = _find_race_json(date_dash, vc, rn)
        if not src:
            summary["errors"].append(f"R{rn:02d}: 搵唔到 race JSON 檔 → skip merge")
            continue
        try:
            d = read_json(src)
        except Exception as e:
            summary["errors"].append(f"R{rn:02d}: JSON parse fail {e}")
            continue
        entries = d.get("entries") or d.get("horses") or []
        if not entries:
            summary["errors"].append(f"R{rn:02d}: entries 空 → skip")
            continue
        number_to_entry = OrderedDict()
        for e in entries:
            try:
                n = int(e.get("number") or 0)
            except Exception:
                n = 0
            if 1 <= n <= MAX_RACES_PER_DAY:
                number_to_entry[n] = e
        for hno, cc_info in per_race_cc.items():
            ent = number_to_entry.get(hno)
            if not ent: continue
            _merge_cc_into_horse(ent, cc_info)
            horses_merged_any.add((rn, hno))
        # 自動 cc_expert_count <4 項 ≥85 → 升級 cc_expert_count (Step I 補充 mirror)
        for hno, ent in number_to_entry.items():
            cnt = 0
            for kk in ("trackwork_score","form_score","except_score","vet_score"):
                v = ent.get(kk)
                if isinstance(v, (int, float)) and v >= 85: cnt += 1
            if cnt >= 4 and (ent.get("cc_expert_count") or 0) < 2:
                ent["cc_expert_count"] = 2
                if not ent.get("cc_experts"): ent["cc_experts"] = ["AI auto(晨/形/異/醫≥85)"]
        # mirror entries ↔ horses
        if "horses" in d and not d.get("entries"):
            d["entries"] = [OrderedDict(x) for x in d["horses"]]
        if "entries" in d and not d.get("horses"):
            d["horses"] = [OrderedDict(x) for x in d["entries"]]
        if not dry_run:
            write_json(src, d)
            if pub:
                try: write_json(pub, d)
                except Exception as e: summary["errors"].append(f"R{rn:02d}: public mirror {e}")
    summary["horses_with_cc"] = len(horses_merged_any)
    # summary counts
    for rn in race_nums:
        try:
            src, _pub = _find_race_json(date_dash, vc, rn)
            if not src: continue
            d = read_json(src)
            es = d.get("entries") or []
            for e in es:
                if (e.get("cc_expert_count") or 0) > 0: summary["expert_horses_total"] += 1
                if e.get("cc_trackwork_summary"): summary["tw_horses_total"] += 1
                if e.get("cc_draw_oncc"): summary["barrier_horses_total"] += 1
        except Exception:
            pass
    summary["errors"] = summary["errors"][:15]
    return summary


def _main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None)
    ap.add_argument("--date", default=None, help="YYYY-MM-DD")
    ap.add_argument("--venue", default=None, help="ST | HV")
    ap.add_argument("--race-no", default=None, type=int)
    ap.add_argument("--race-nums-csv", default=None)
    ap.add_argument("--min-days", default=0, type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--push", action="store_true")
    args = ap.parse_args()

    date_slash, date_dash, vc, race_nums = _resolve_date_venue_nums(args)
    if vc not in ("ST", "HV"):
        print(f"ERROR: venue={vc} invalid")
        sys.exit(2)
    print(f"[oncc] target: {date_slash} {vc} races={race_nums}")

    summary = run_for_raceday(date_slash, date_dash, vc, race_nums, dry_run=args.dry_run)
    out_json = os.path.join(ROOT, "data", "_oncc_fetch_summary.json")
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"\n✓ summary 寫入：{out_json}")
    print("\n==== STEP J (ON.CC) SUMMARY ====")
    try:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    except Exception:
        pass
    print("================================")
    if args.push:
        try:
            subprocess.check_call(["git", "-C", ROOT, "add", "-A"])
            subprocess.check_call(["git", "-C", ROOT, "commit", "-m",
                                   f"stepJ: on.cc fetch expert/barrier/tw {date_dash} {vc}"])
            subprocess.check_call(["git", "-C", ROOT, "push"])
            print("[push] ✓ OK")
        except subprocess.CalledProcessError as e:
            print(f"[push] skip: {e}")


if __name__ == "__main__":
    _main()
