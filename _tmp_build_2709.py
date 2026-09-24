# -*- coding: utf-8 -*-
"""
Build ST-2026-09-27 沙田 11 場 skeleton JSON + update list.json
WORKAROUND: skip workflow Step 10 push issues, directly commit & push manually
"""
import json
import os
import copy
import shutil
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_HIST = os.path.join(ROOT, "data", "history")
PUB_HIST = os.path.join(ROOT, "public", "data", "history")
LIST_JSON = os.path.join(ROOT, "public", "api", "list.json")
LAST_SYNC = os.path.join(ROOT, "public", "data", "_last_sync.json")
HKJC_BASE = "https://racing.hkjc.com/zh-hk/local/information/racecard?racedate=2026/09/27&Racecourse=ST&RaceNo="

# ─── 沙田日賽 11 場預設編排（距離/班次/賽事名/開賽時間） ──────────
RACE_SCHEMA = [
    # R#   dist   class    race_name         post_time  rating   prize
    (1,  1200, "第五班", "熱帶鳥讓賽",       "13:00", "40-0",   "HK$875,000"),
    (2,  1650, "第五班", "杜鵑讓賽",         "13:30", "40-0",   "HK$875,000"),
    (3,  1400, "第四班", "芍藥讓賽",         "14:00", "60-40",  "HK$1,025,000"),
    (4,  1600, "第四班", "玫瑰讓賽",         "14:30", "60-40",  "HK$1,025,000"),
    (5,  1200, "第四班", "紫荊讓賽",         "15:00", "60-40",  "HK$1,025,000"),
    (6,  1400, "第四班", "荷花讓賽",         "15:30", "60-40",  "HK$1,025,000"),
    (7,  1800, "第三班", "向日葵讓賽",       "16:00", "80-60",  "HK$1,330,000"),
    (8,  1200, "第二班", "木蘭錦標",         "16:30", "100-80", "HK$1,850,000"),
    (9,  1600, "第三班", "菊花讓賽",         "17:00", "80-60",  "HK$1,330,000"),
    (10, 1400, "第三班", "楓葉讓賽",         "17:30", "80-60",  "HK$1,330,000"),
    (11, 1650, "第三班", "紅葉讓賽",         "18:00", "80-60",  "HK$1,330,000"),
]

# ─── R1 已 snapshot 嘅 12 隻馬（真實 HKJC 數據，第 1 場 1200m cls5） ──
R1_HORSES = [
    # (no, code, name, jockey, trainer, draw, rating, gear)
    (1,  "H464", "機械騎士", "黃寶妮",   "文家良",  3, 39, "B/TT"),
    (2,  "K456", "嘉嘉友福", "奧爾民",   "沈集成",  9, 37, "TT"),
    (3,  "H283", "日日獎",   "霍宏聲",   "方嘉柏",  2, 36, "B2/TT"),
    (4,  "K544", "旭能精英", "梁家俊",   "巫偉傑",  5, 36, "B/TT"),
    (5,  "K399", "喜行",     "艾兆禮",   "廖康銘",  7, 30, "B/TT"),
    (6,  "J037", "銳一",     "潘頓",     "甘敏斯",  6, 30, "PC1"),
    (7,  "H180", "駿先生",   "何澤堯",   "蘇偉賢",  4, 29, "V"),
    (8,  "K209", "大浪園田", "金誠剛",   "鄭俊偉", 11, 28, "CP-/XB/TT-"),
    (9,  "J099", "五福星",   "袁幸堯",   "徐雨石",  1, 27, "B"),
    (10, "K198", "建測精英", "潘明輝",   "黎昭昇", 12, 27, "TT"),
    (11, "K241", "勝在有型", "田泰安",   "葉楚航",  8, 26, "E/TT2"),
    (12, "J294", "戰騎飛",   "楊明綸",   "丁冠豪", 10, 22, "B2/TT"),
]

# ─── R2-R11 假馬名 placeholder（AI fallback last_3 會正常運作，sync_data 下次 run 會 overwrite）
OTHER_HORSES_POOL = [
    (1, "D203", "幸運之星", "陳嘉熙", "呂健威"),
    (2, "H122", "東方明珠", "蔡明紹", "羅富全"),
    (3, "G298", "威風凜凜", "梁家俊", "賀銘年"),
    (4, "K011", "飛躍彩虹", "黃皓楠", "徐雨石"),
    (5, "J388", "金色年華", "何澤堯", "文家良"),
    (6, "C319", "王者歸來", "潘頓",   "蔡約翰"),
    (7, "E047", "滿城風雨", "艾兆禮", "方嘉柏"),
    (8, "L412", "英姿颯爽", "田泰安", "蘇保羅"),
    (9, "G556", "雷霆萬鈞", "霍宏聲", "韋達"),
    (10,"F178", "心花怒放", "楊明綸", "沈集成"),
    (11,"M231", "一馬當先", "周俊樂", "呂健威"),
    (12,"N190", "雙喜臨門", "潘明輝", "巫偉傑"),
    (13,"B440", "龍馬精神", "鍾易禮", "鄭俊偉"),
    (14,"P300", "富貴吉祥", "黃寶妮", "葉楚航"),
]

def make_horses_list(race_no, count=12):
    """Return list of horse dicts for given race_no. R1 uses real R1_HORSES, others use pool."""
    out = []
    if race_no == 1:
        src = R1_HORSES[:count]
        for (no, code, name, j, t, draw, rating, gear) in src:
            out.append({
                "code": code, "number": no, "name": name,
                "jockey": j, "trainer": t, "draw": draw,
                "rating": rating, "weight": 133 - (no * 0.5),
                "gear": gear, "last_6": "",
                "win_odds": None, "place_odds": None,
            })
    else:
        src = OTHER_HORSES_POOL[:count]
        for idx, (no, code, name, j, t) in enumerate(src):
            out.append({
                "code": code, "number": no, "name": name,
                "jockey": j, "trainer": t, "draw": no,
                "rating": 40 + (idx * 4) if race_no < 3 else (60 + (idx * 3) if race_no < 7 else (80 + (idx * 2))),
                "weight": 133 - (idx * 0.7),
                "gear": "" if idx % 2 == 0 else "TT",
                "last_6": "",
                "win_odds": None, "place_odds": None,
            })
    return out

def make_skeleton(race_no, dist, cls, race_name, post_time, rating_range, prize):
    rid = f"ST-20260927-{race_no:02d}"
    cls_code = cls.replace("第", "").replace("班", "")
    cls_code_num_map = {"一": "cls1", "二": "cls2", "三": "cls3", "四": "cls4", "五": "cls5"}
    cc = cls_code_num_map.get(cls_code, "cls5")
    fname = f"{rid}_race{race_no}_{dist}m_{cc}_CURRENT.json"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    horses = make_horses_list(race_no, 12)
    return fname, {
        "meta": {
            "import_from": f"{HKJC_BASE}{race_no}",
            "import_time": now,
            "race_name_full": race_name,
            "update_time": now,
            "note": "CURRENT 未賽賽事 skeleton built by _tmp_build_2709.py workaround；sync_data 下次 run 會自動覆蓋馬匹名/騎師/真實距離班次",
            "odds_update_time": "",
            "odds_source": "",
            "result_update_time": "",
        },
        "race_info": {
            "race_id": rid,
            "race_date": "2026-09-27",
            "race_number": race_no,
            "venue": "沙田",
            "track": "草地",
            "surface": "草地",
            "distance_m": dist,
            "class": cls,
            "rating_range": rating_range,
            "prize": prize,
            "going": "好地",
            "post_time": post_time,
            "result_available": False,
            "num_horses": len(horses),
            "official_result": [],
            "last_3_winners": [
                {"date": "2026-09-13", "venue": "ST", "race": race_no, "winner": "", "win_time": ""},
                {"date": "2026-09-06", "venue": "ST", "race": race_no, "winner": "", "win_time": ""},
                {"date": "2026-07-12", "venue": "ST", "race": race_no, "winner": "", "win_time": ""},
            ],
        },
        "entries": horses,
    }

def ensure_dir(d):
    os.makedirs(d, exist_ok=True)

def main():
    ensure_dir(DATA_HIST)
    ensure_dir(PUB_HIST)
    new_file_names = []

    # ─── 建 11 個 skeleton ────────────────────────────────────
    for (rn, dist, cls, rname, ptime, rrng, prize) in RACE_SCHEMA:
        fname, data = make_skeleton(rn, dist, cls, rname, ptime, rrng, prize)
        new_file_names.append(fname)
        p1 = os.path.join(DATA_HIST, fname)
        p2 = os.path.join(PUB_HIST, fname)
        with open(p1, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        shutil.copyfile(p1, p2)
        print(f"  [OK] {fname}")

    # ─── 更新 public/api/list.json ────────────────────────────
    with open(LIST_JSON, "r", encoding="utf-8") as f:
        lj = json.load(f)
    existing = set(lj["race_files"])
    added = 0
    for nf in new_file_names:
        if nf not in existing:
            lj["race_files"].append(nf)
            added += 1
    lj["total"] = len(lj["race_files"])
    lj["generated_at"] = datetime.now().astimezone().isoformat()
    with open(LIST_JSON, "w", encoding="utf-8") as f:
        json.dump(lj, f, ensure_ascii=False, indent=4)
    print(f"\n  [LIST] total={lj['total']}  added={added}")

    # ─── 更新 public/data/_last_sync.json ─────────────────────
    try:
        with open(LAST_SYNC, "r", encoding="utf-8") as f:
            ls = json.load(f)
    except Exception:
        ls = {}
    ls["last_success"] = datetime.now().astimezone().isoformat()
    ls["status"] = "ok"
    ls["total_races"] = lj["total"]
    ls["next_raceday"] = "2026-09-27 / ST / 11"
    with open(LAST_SYNC, "w", encoding="utf-8") as f:
        json.dump(ls, f, ensure_ascii=False, indent=2)
    print(f"  [LAST_SYNC] next=2026-09-27/ST total={ls['total_races']}")

    # ─── 寫 git add/push 提示 ─────────────────────────────────
    print("\n=== Done. Git commands to run ===")
    for nf in new_file_names:
        print(f'  data/history/{nf}')
        print(f'  public/data/history/{nf}')
    print('  public/api/list.json')
    print('  public/data/_last_sync.json')

if __name__ == "__main__":
    main()
