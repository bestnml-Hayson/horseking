# -*- coding: utf-8 -*-
"""
_hkjc_fetch_all_racedata.py （Pipeline Step I 專用 + 手動 CLI 雙模式）
=====================================================================
  用途：
    從 HKJC 官方 zh-hk 6 大資訊頁面收集每隻馬嘅所有補充資訊，merge 入去 JSON：
      ① /racecard               → 基本排位 + last_6/gear/draw (Step H 已做，此處 skip)
      ② /localtrackwork        → 晨操評分 (trackwork_score) + 操兵備註
      ③ /racereportext         → 綜合賽事報告 + 對上一仗名次/走勢
      ④ /formline              → 近績形勢線 + 形態評分 (form_score)
      ⑤ /exceptionalfactors    → 異常因素：負磅異常/換騎/換裝/退馬 (except_flags, except_score)
      ⑥ /veterinaryrecord      → 獸醫/檢疫/傷患紀錄 (vet_flags, vet_score)
    + 自動生成 cc_* 兼容欄 (cc_expert_count 等從 on.cc 補充)

  Merge 原則（嚴格遵守）：
    ✗ 絕對唔覆蓋靜態 12 欄（name/jockey/trainer/draw/rating/weight/gear/last_6/last_3/post_time…）
    ✗ 絕對唔覆蓋 odds_* / cc_* 舊值（如果新 fetch 冇值）
    ✗ 絕對唔覆蓋 official_result / payouts / split_times
    ✓ 新增動態欄：trackwork_score / form_score / except_score / vet_score / ... (共 8 個)
    ✓ 若舊 JSON 已經有上述欄，新值優先覆蓋（因呢啲補充欄每日都會更新）

  Pipeline 集成：sync_data.ps1 Step I (Step H populate 之後, Step C odds/cc merge 之前 或之後皆可)
  手動模式 CLI：
    python _hkjc_fetch_all_racedata.py --date 2026-09-27 --venue ST
    python _hkjc_fetch_all_racedata.py --url "https://racing.hkjc.com/zh-hk/local/information/racecard?racedate=2026/09/27&Racecourse=ST"
"""
import sys, os, re, json, argparse, subprocess
from datetime import datetime
from collections import OrderedDict

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import _auto_bootstrap_next_raceday as _boot

ZH_HK_BASE = "https://racing.hkjc.com/zh-hk/local/information"
OLD_CN_BASE = "https://racing.hkjc.com/racing/information/chinese/Racing"

# ============================================================
#  1. URL Builders + Generic Fetch (reuse _boot._scraper_mod)
# ============================================================

def _build_info_urls(date_slash, vc, rn, info_type):
    """
    info_type ∈ {racecard, localtrackwork, racereportext, formline, exceptionalfactors, veterinaryrecord}
    同時試 zh-hk 新版 + 舊版 URL，最大 bytes 優先。
    """
    if info_type == "racereportext":
        zh = f"{ZH_HK_BASE}/racereportext?racedate={date_slash}&Racecourse={vc}&RaceNo={rn}"
        old = f"{OLD_CN_BASE}/RaceReportExt.aspx?racedate={date_slash}&Racecourse={vc}&RaceNo={rn}"
    elif info_type == "formline":
        zh = f"{ZH_HK_BASE}/formline?racedate={date_slash}&Racecourse={vc}&RaceNo={rn}"
        old = f"{OLD_CN_BASE}/Formline.aspx?racedate={date_slash}&Racecourse={vc}&RaceNo={rn}"
    elif info_type == "exceptionalfactors":
        zh = f"{ZH_HK_BASE}/exceptionalfactors?racedate={date_slash}&Racecourse={vc}&RaceNo={rn}"
        old = f"{OLD_CN_BASE}/ExceptionalFactors.aspx?racedate={date_slash}&Racecourse={vc}&RaceNo={rn}"
    elif info_type == "veterinaryrecord":
        zh = f"{ZH_HK_BASE}/veterinaryrecord?racedate={date_slash}&Racecourse={vc}&RaceNo={rn}"
        old = f"{OLD_CN_BASE}/VeterinaryRecord.aspx?racedate={date_slash}&Racecourse={vc}&RaceNo={rn}"
    elif info_type == "localtrackwork":
        zh = f"{ZH_HK_BASE}/localtrackwork?racedate={date_slash}&Racecourse={vc}&RaceNo={rn}"
        old = f"{OLD_CN_BASE}/LocalTrackwork.aspx?racedate={date_slash}&Racecourse={vc}&RaceNo={rn}"
    else:  # racecard
        zh = f"{ZH_HK_BASE}/racecard?racedate={date_slash}&Racecourse={vc}&RaceNo={rn}"
        old = f"{OLD_CN_BASE}/Racecard.aspx?racedate={date_slash}&Racecourse={vc}&RaceNo={rn}"
    return [zh, old]


def _fetch_html(urls, retries=2, min_bytes=4000, delay_s=1.5):
    """Retry + delay + 最大 bytes 個 html 返回 (utf-8 text, import_url)。"""
    best = (b"", None)
    for u in urls:
        try:
            import time as _t; _t.sleep(delay_s)
            h = _boot._scraper_mod.fetch_url(u, retries=retries, delay=delay_s)
            hb = h.encode("utf-8", "replace") if isinstance(h, str) else bytes(h or b"")
            if len(hb) > len(best[0]):
                best = (hb, u)
            if len(hb) >= min_bytes:
                break
        except Exception as e:
            print(f"    [skip] {u} -> {e}")
    return best[0].decode("utf-8", "replace"), best[1]


# ============================================================
#  2. Generic td-cell row parser (復用 Step H robust 思路)
# ============================================================

_NUM_RE = re.compile(r"^\s*\d{1,2}\s*$")
_CLAIM_RE = re.compile(r"[\(（][\-−]?\s*\d+[lbLB磅]?\s*[\)）]")


def _split_tr_tds(html_snippet):
    """將 page 拆 rows -> cells (strip tags clean text)."""
    trs = re.split(r"</\s*tr\s*>", html_snippet, flags=re.IGNORECASE)
    rows = []
    for tr in trs:
        td_split = re.split(r"</\s*td\s*>", tr, flags=re.IGNORECASE)
        cells = []
        for td in td_split:
            c = re.sub(r"<[^>]+>", " ", td)
            c = re.sub(r"\s+", " ", c).strip()
            cells.append(c)
        if any(c for c in cells):
            rows.append(cells)
    return rows


def _find_col_index(rows, *keywords, fuzzy=5):
    """掃描 header / 首 3 行，返回包含 keyword 個 col index (first match)。"""
    for r in rows[:fuzzy]:
        for i, c in enumerate(r):
            for kw in keywords:
                if kw and kw in c:
                    return i
    return None


def _pick_number_cell(cells, idx_fallback=None, scan_range=None):
    """從 cells 搵 1-14 整數做馬號，優先 idx_fallback。"""
    candidates = []
    if idx_fallback is not None and 0 <= idx_fallback < len(cells):
        try:
            v = int(cells[idx_fallback])
            if 1 <= v <= 30:
                return v
        except Exception:
            pass
    rng = scan_range if scan_range else range(len(cells))
    for i in rng:
        try:
            v = int(cells[i])
            if 1 <= v <= 30:
                candidates.append((i, v))
        except Exception:
            pass
    if len(candidates) == 1:
        return candidates[0][1]
    # 多個候選：取 1~14 範圍最細（最似馬號）
    valid = [x[1] for x in candidates if 1 <= x[1] <= 14]
    if valid:
        return valid[0]
    if candidates:
        return candidates[0][1]
    return None


# ============================================================
#  3. Sub-Parsers（每個返回 dict[int] = {馬號: {欄位}}）
# ============================================================

def parse_localtrackwork(html_text, _import_url):
    """
    返回：{馬號: OrderedDict([
        (trackwork_score, 0..100 int),
        (trackwork_note, str 備註),
    ])}
    規則：文字含「彈跳/活躍/走勢順/步佳」→ 高；「步穩/普通/一般」→ 中；「沉悶/乏力」→ 低。
    """
    rows = _split_tr_tds(html_text)
    out = {}
    no_col = _find_col_index(rows, "馬號", "馬匹編號", "編號") or 0
    note_col = _find_col_index(rows, "操兵", "操況", "備註", "晨操", "試閘") or -1
    score_col = _find_col_index(rows, "評分", "評級", "分")
    for r in rows:
        if not r:
            continue
        hno = _pick_number_cell(r, no_col)
        if hno is None:
            continue
        note = ""
        if 0 <= note_col < len(r):
            note = r[note_col]
        score_txt = ""
        if score_col is not None and 0 <= score_col < len(r):
            score_txt = r[score_col]
        # --- score heuristic ---
        base = 50
        text = (note + " " + score_txt)
        if any(w in text for w in ["彈跳", "活躍", "步佳", "走勢順", "優異", "特佳", "大勇"]):
            base += 30
        elif any(w in text for w in ["走勢靚", "順暢", "良好", "穩步", "靈活"]):
            base += 15
        elif any(w in text for w in ["沉悶", "乏力", "緊張", "發脾", "拒絕", "劣"]):
            base -= 25
        elif any(w in text for w in ["普通", "一般", "平穩", "無異樣"]):
            base += 0
        # bonus keywords
        if "試閘" in text:
            base += 5
        if "過關" in text:
            base += 5
        base = max(0, min(100, base))
        out[int(hno)] = OrderedDict([
            ("trackwork_score", int(base)),
            ("trackwork_note", note[:200]),
        ])
    return out


def parse_formline(html_text, _import_url):
    """
    返回：{馬號: {form_score 0..100, form_note, trend_direction [1=上升,0=平,-1=下降]}}
    依據 last_6 以外之文字：上升走勢「回升/回勇」高；下滑「回落/退腳」低
    """
    rows = _split_tr_tds(html_text)
    out = {}
    no_col = _find_col_index(rows, "馬號", "編號") or 0
    note_col = _find_col_index(rows, "形勢", "走勢", "近績", "備註", "狀態") or -1
    score_col = _find_col_index(rows, "評分", "形態分")
    for r in rows:
        if not r:
            continue
        hno = _pick_number_cell(r, no_col)
        if hno is None:
            continue
        note = ""
        if 0 <= note_col < len(r):
            note = r[note_col]
        s_txt = ""
        if score_col is not None and 0 <= score_col < len(r):
            s_txt = r[score_col]
        base = 50
        text = note + " " + s_txt
        trend = 0
        if any(w in text for w in ["回升", "回勇", "復甦", "勇", "狀態佳", "起飛", "脫胎換骨"]):
            base += 25; trend = 1
        elif any(w in text for w in ["進步", "趨好", "向好", "改善", "穩步上揚"]):
            base += 12; trend = 1
        elif any(w in text for w in ["回落", "退腳", "下滑", "走樣", "疲態", "沉"]):
            base -= 20; trend = -1
        elif any(w in text for w in ["一般", "平", "穩定", "無大變化"]):
            base += 0
        base = max(0, min(100, base))
        out[int(hno)] = OrderedDict([
            ("form_score", int(base)),
            ("form_note", note[:200]),
            ("form_trend", int(trend)),
        ])
    return out


def parse_exceptionalfactors(html_text, _import_url):
    """
    返回：{馬號: {except_score 0..100, except_flags [list of flags], except_note}}
    換騎/升分/加磅/負磅差距大 → 扣；無異常 → 85。
    """
    rows = _split_tr_tds(html_text)
    out = {}
    no_col = _find_col_index(rows, "馬號", "編號") or 0
    note_col = _find_col_index(rows, "異常", "備註", "因素", "說明") or -1
    for r in rows:
        if not r:
            continue
        hno = _pick_number_cell(r, no_col)
        if hno is None:
            continue
        text = ""
        if 0 <= note_col < len(r):
            text = r[note_col]
        flags = []
        base = 85  # 無異常最高分
        if any(w in text for w in ["換騎", "騎師變更", "替補", "改配"]):
            base -= 12; flags.append("換騎")
        if any(w in text for w in ["加磅", "升分", "評分上調"]):
            base -= 6; flags.append("加磅")
        if any(w in text for w in ["減磅", "降分"]):
            base += 8; flags.append("減磅")
        if any(w in text for w in ["退馬", "退出", "scr", "vet"]):
            base -= 40; flags.append("退馬")
        if any(w in text for w in ["換裝", "裝備變更", "加配", "除下"]):
            base -= 4; flags.append("換裝")
        if any(w in text for w in ["檔位劣", "外檔", "大外檔"]):
            base -= 8; flags.append("檔差")
        if any(w in text for w in["負磅差", "不公平", "差距大"]):
            base -= 10; flags.append("負磅異常")
        base = max(0, min(100, base))
        out[int(hno)] = OrderedDict([
            ("except_score", int(base)),
            ("except_flags", flags),
            ("except_note", text[:250]),
        ])
    return out


def parse_veterinaryrecord(html_text, _import_url):
    """
    返回：{馬號: {vet_score 0..100, vet_flags [list], vet_note}}
    正常/健康 → 95；小毛病 → 70；傷患復出/手術 → 50；未出賽隔離 → 30。
    """
    rows = _split_tr_tds(html_text)
    out = {}
    no_col = _find_col_index(rows, "馬號", "編號") or 0
    note_col = _find_col_index(rows, "備註", "醫療", "檢疫", "獸醫", "狀態") or -1
    status_col = _find_col_index(rows, "狀態", "結果", "合格")
    for r in rows:
        if not r:
            continue
        hno = _pick_number_cell(r, no_col)
        if hno is None:
            continue
        text = ""
        if 0 <= note_col < len(r):
            text = r[note_col]
        st = ""
        if status_col is not None and 0 <= status_col < len(r):
            st = r[status_col]
        all_txt = text + " " + st
        flags = []
        base = 95
        if any(w in all_txt for w in ["合格", "健康", "良好", "正常", "適合出賽", "Pass"]):
            base = 95; flags.append("合格")
        if any(w in all_txt for w in ["微恙", "感冒", "小毛病", "肌肉緊", "輕微"]):
            base = 70; flags.append("小毛病")
        if any(w in all_txt for w in ["手術", "受傷", "骨折", "腱", "復出", "康復中"]):
            base = 45; flags.append("傷患/手術")
        if any(w in all_txt for w in ["檢疫", "隔離", "發熱", "未通過"]):
            base = 25; flags.append("檢疫/隔離")
        if any(w in all_txt for w in ["禁止出賽", "暫停", "不適合"]):
            base = 0; flags.append("禁止出賽")
        base = max(0, min(100, base))
        out[int(hno)] = OrderedDict([
            ("vet_score", int(base)),
            ("vet_flags", flags),
            ("vet_note", text[:250]),
        ])
    return out


def parse_racereportext(html_text, _import_url):
    """
    返回：{馬號: {last_run_note, last_run_rank, report_note}}
    （綜合賽事報告：對上一仗名次 + 走勢文字）
    """
    rows = _split_tr_tds(html_text)
    out = {}
    no_col = _find_col_index(rows, "馬號", "編號") or 0
    note_col = _find_col_index(rows, "走勢", "賽事報告", "備註", "上仗", "名次") or -1
    rank_col = _find_col_index(rows, "名次", "排名", "終點")
    for r in rows:
        if not r:
            continue
        hno = _pick_number_cell(r, no_col)
        if hno is None:
            continue
        note = ""
        if 0 <= note_col < len(r):
            note = r[note_col]
        rank = None
        if rank_col is not None and 0 <= rank_col < len(r):
            try:
                rk = int(r[rank_col])
                if 1 <= rk <= 30:
                    rank = rk
            except Exception:
                # extract first \d+
                m = re.search(r"(\d{1,2})", r[rank_col])
                if m:
                    rank = int(m.group(1))
        out[int(hno)] = OrderedDict([
            ("last_run_note", note[:250]),
            ("last_run_rank", rank),
            ("report_note", note[:250]),
        ])
    return out


PARSE_MAP = OrderedDict([
    ("localtrackwork",       (parse_localtrackwork,       ["trackwork_score", "trackwork_note"])),
    ("formline",             (parse_formline,             ["form_score", "form_note", "form_trend"])),
    ("exceptionalfactors",   (parse_exceptionalfactors,   ["except_score", "except_flags", "except_note"])),
    ("veterinaryrecord",     (parse_veterinaryrecord,     ["vet_score", "vet_flags", "vet_note"])),
    ("racereportext",        (parse_racereportext,        ["last_run_note", "last_run_rank", "report_note"])),
])


# ============================================================
#  4. 查找 JSON 文件 + merge helper (保留動態欄、覆蓋新補充欄)
# ============================================================

def _find_race_json(date_dash, vc, race_number):
    """在 data/history 搵對應 JSON 路徑（兼容 CURRENT / 原版兩種 filename）"""
    hist_dir = os.path.join(ROOT, "data", "history")
    date_cmpct = date_dash.replace("-", "")  # 20260927
    prefix = f"{vc}-{date_cmpct}-{int(race_number):02d}"
    if not os.path.isdir(hist_dir):
        return None
    for fn in os.listdir(hist_dir):
        if fn.startswith(prefix) and fn.endswith(".json") and "_CURRENT" in fn:
            return os.path.join(hist_dir, fn)
    for fn in os.listdir(hist_dir):
        if fn.startswith(prefix) and fn.endswith(".json"):
            return os.path.join(hist_dir, fn)
    return None


DYNAMIC_CORE_KEEP_PREFIXES = ("cc_", "odds_", "payouts", "split_times", "official_result", "result_info", "betfair", "pool_")
STATIC_CORE_KEEP = {"number", "code", "name", "jockey", "trainer", "draw", "rating", "weight",
                    "gear", "last_6", "last_3", "best_time_sec", "best_time_src", "starts", "wins", "places"}


def _merge_horse(old_horse, new_supplement):
    """
    合併策略：
    - 所有新補充欄（PARSE_MAP.values 列出嘅 8+）直接覆蓋舊值（每日更新）
    - 以 cc_/odds_/payouts/official_result 開頭嘅舊值 100% 保留
    - 其他舊值保留（Step H populate 嘅靜態欄唔會被碰）
    """
    merged = OrderedDict(old_horse) if isinstance(old_horse, OrderedDict) else OrderedDict(old_horse.items())
    for k, v in new_supplement.items():
        if v is None:
            continue
        if isinstance(v, (list, dict)) and not v:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        merged[k] = v
    return merged


def _merge_cc_compat(horse, info_bundle):
    """cc_* 兼容：計算 cc_expert_count / cc_jockey_stat / cc_trainer_stat 攬展；唔覆蓋舊 cc_*。"""
    h = horse
    # cc_expert_count：根據新補充欄 4 項分數綜合 (≥85 每項 +1；≥70 每項 +0.5) → floor
    if not isinstance(h.get("cc_expert_count"), int) or h.get("cc_expert_count", 0) <= 0:
        expert = 0
        for k in ["trackwork_score", "form_score", "except_score", "vet_score"]:
            s = info_bundle.get(k)
            if isinstance(s, int):
                if s >= 85:
                    expert += 1
                elif s >= 70:
                    expert += 0.5
        if expert >= 2:
            h["cc_expert_count"] = int(expert)
    # cc_jockey_claim → skip (Step H populate 已做)
    return h


# ============================================================
#  5. Main CLI + pipeline driver
# ============================================================

def _date_to_slash(s):
    # YYYY-MM-DD or YYYY/MM/DD → YYYY/MM/DD (0-padded)
    s = (s or "").strip()
    m = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", s)
    if not m:
        raise ValueError(f"日期格式錯誤：{s}")
    return f"{int(m.group(1)):04d}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"


def _parse_url_targets(url):
    m = re.search(r"racedate[=:]\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})", url, re.I)
    mv = re.search(r"Racecourse[=:]\s*(ST|HV)", url, re.I)
    mr = re.search(r"RaceNo[=:]\s*(\d{1,2})", url, re.I)
    if not m:
        raise ValueError(f"URL 缺 racedate：{url}")
    date_slash = f"{int(m.group(1)):04d}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"
    date_dash = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    vc = mv.group(1).upper() if mv else None
    race_nums = [int(mr.group(1))] if mr else None
    return date_slash, date_dash, vc, race_nums


def run_for_raceday(date_slash, date_dash, vc, race_nums, dry_run=False):
    """Step I pipeline entry: return summary OrderedDict, mutate JSON files on disk."""
    if vc not in ("ST", "HV"):
        raise ValueError(f"venue 必須 ST/HV (收到：{vc})")
    if not race_nums:
        raise ValueError("race_nums 為空")

    summary = OrderedDict([
        ("started_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ("date_dash", date_dash), ("date_slash", date_slash), ("venue", vc),
        ("races", race_nums),
        ("per_info_fetch_bytes", OrderedDict()),
        ("per_race_horses_updated", OrderedDict()),
        ("errors", []),
    ])

    info_types = list(PARSE_MAP.keys())

    for rn in race_nums:
        print(f"\n▶ Step I R{rn:02d}/{vc} ({date_dash})")
        jpath = _find_race_json(date_dash, vc, rn)
        if not jpath:
            msg = f"R{rn:02d} 搵唔到 JSON，skip（可能 skeleton 未 bootstrap）"
            print(f"  ⚠ {msg}")
            summary["errors"].append(msg)
            continue
        with open(jpath, "r", encoding="utf-8") as f:
            race = json.load(f, object_pairs_hook=OrderedDict)
        horses = race.get("horses") or race.get("entries") or []
        if not horses:
            summary["errors"].append(f"R{rn:02d} horses/entries 空")
            continue

        # 每隻馬 build info_bundle (key=馬號)
        bundle = {}  # hno(int) → dict
        for info_type in info_types:
            fn, fields = PARSE_MAP[info_type]
            urls = _build_info_urls(date_slash, vc, rn, info_type)
            try:
                html, iurl = _fetch_html(urls, retries=2, delay_s=1.0)
                summary["per_info_fetch_bytes"].setdefault(info_type, 0)
                summary["per_info_fetch_bytes"][info_type] += len(html)
                if not html or len(html) < 2000:
                    print(f"    · {info_type:18s} skip ({len(html)} bytes <2000)")
                    continue
                parsed_rows = fn(html, iurl)
                print(f"    ✓ {info_type:18s} matched {len(parsed_rows)} 匹馬 ({len(html)} bytes)")
                for hno, kv in parsed_rows.items():
                    bundle.setdefault(int(hno), OrderedDict())
                    for k, v in kv.items():
                        bundle[int(hno)][k] = v
            except Exception as e:
                msg = f"R{rn} {info_type} parse fail: {type(e).__name__} {e}"
                print(f"    ✗ {msg}")
                summary["errors"].append(msg)
                continue

        # Apply merge
        updated = 0
        for horse in horses:
            hno = int(horse.get("number") or 0)
            if hno < 1 or hno > 30:
                continue
            info_bundle = bundle.get(hno, {})
            if info_bundle:
                # 1) 合併 8+ 補充欄 (覆蓋舊值)
                merged = _merge_horse(horse, info_bundle)
                # 2) cc_* 兼容 (唔覆蓋舊 cc_expert_count)
                merged = _merge_cc_compat(merged, info_bundle)
                # 3) 同步 horse reference → in-place update
                for k, v in list(merged.items()):
                    horse[k] = v
                updated += 1
        # 同步 entries alias (若存在)
        if "entries" in race and isinstance(race["entries"], list) and len(race["entries"]) == len(horses):
            race["entries"] = [OrderedDict(h.items()) for h in horses]
        race["horses"] = horses

        # meta 欄補充 import_from 多來源 (append)
        race.setdefault("meta", OrderedDict())
        meta = race["meta"]
        srcs = set()
        for info_type in info_types:
            for u in _build_info_urls(date_slash, vc, rn, info_type)[:1]:
                srcs.add(u)
        old_import = meta.get("import_from") or ""
        for s in srcs:
            if s and s not in old_import:
                old_import = (old_import + "; " + s).strip("; ")
        meta["import_from"] = old_import
        meta["fetch_all_update_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        meta["fetch_all_updated_horses_R%s" % rn] = updated

        summary["per_race_horses_updated"][f"R{rn:02d}"] = updated
        print(f"    ⇩ merge 完成：{updated}/{len(horses)} 匹有補充欄 → 寫入 {os.path.basename(jpath)}")

        if dry_run:
            continue
        try:
            tmp = jpath + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(race, f, indent=2, ensure_ascii=False)
            os.replace(tmp, jpath)
            # Mirror 到 public/data/history (若存在同名 file)
            pub_dir = os.path.join(ROOT, "public", "data", "history")
            if os.path.isdir(pub_dir):
                mirror_fn = os.path.basename(jpath)
                mirror_path = os.path.join(pub_dir, mirror_fn)
                if os.path.exists(mirror_path):
                    with open(mirror_path, "w", encoding="utf-8") as f:
                        json.dump(race, f, indent=2, ensure_ascii=False)
        except Exception as e:
            msg = f"R{rn} write JSON 失敗：{type(e).__name__} {e}"
            summary["errors"].append(msg)
            print(f"    ✗ {msg}")

    summary["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    summary["total_horses_with_supplement"] = sum(summary["per_race_horses_updated"].values())
    return summary


def _main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None)
    ap.add_argument("--date", default=None)
    ap.add_argument("--venue", default=None)
    ap.add_argument("--race-no", type=int, default=None)
    ap.add_argument("--skip-rebuild", action="store_true", help="保留給 sync_data.ps1 pipeline 用")
    ap.add_argument("--dry-run", action="store_true", help="只 print 唔寫檔")
    ap.add_argument("--push", action="store_true", help="完成後自動 git commit push")
    ap.add_argument("--race-nums-csv", default=None, help="1,2,5,7.. (指定多場)")
    args = ap.parse_args()

    if args.url:
        date_slash, date_dash, vc, race_nums = _parse_url_targets(args.url)
    else:
        if not args.date:
            print("ERROR: 缺少 --date 或 --url")
            sys.exit(2)
        date_slash = _date_to_slash(args.date)
        date_dash = date_slash.replace("/", "-")
        vc = None
        if args.venue:
            vc = args.venue.upper()
        if not vc:
            try:
                _cn, vc2, nums = _boot._get_num_races_and_venue(date_slash)
                vc = vc2
            except Exception:
                raise RuntimeError("自動 detect venue 失敗，請 --venue ST 或 HV")
        # race_nums
        if args.race_no:
            race_nums = [int(args.race_no)]
        elif args.race_nums_csv:
            race_nums = [int(x.strip()) for x in args.race_nums_csv.split(",") if x.strip()]
        else:
            try:
                _cn, _vc, nums = _boot._get_num_races_and_venue(date_slash)
                race_nums = nums
            except Exception:
                race_nums = list(range(1, 12))
                print(f"[WARN] detect nums 失敗 → fallback R1..R{race_nums[-1]}")

    if vc not in ("ST", "HV"):
        print(f"ERROR: venue={vc} 非法，請 ST/HV")
        sys.exit(2)

    summary = run_for_raceday(date_slash, date_dash, vc, race_nums, dry_run=args.dry_run)

    out_json = os.path.join(ROOT, "data", "_fetch_all_summary.json")
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"\n✓ summary 寫入：{out_json}")
    # stdout summary line (方便 sync_data.ps1 ExtractJson)
    print("\n==== STEP I SUMMARY ====")
    try:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    except Exception:
        pass
    print("========================")

    if args.push:
        try:
            subprocess.check_call(["git", "-C", ROOT, "add", "-A"])
            subprocess.check_call(["git", "-C", ROOT, "commit", "-m",
                                   "stepI: fetch HKJC all 6 infos (trackwork/form/except/vet/report)"])
            subprocess.check_call(["git", "-C", ROOT, "push"])
            print("[push] ✓ OK")
        except subprocess.CalledProcessError as e:
            print(f"[push] skip: {e}")


if __name__ == "__main__":
    _main()
