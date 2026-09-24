import json, os, shutil, sys, argparse
from collections import OrderedDict
import _cc_raw_data

ROOT = r"d:\Trae\horse"
DATA = os.path.join(ROOT, "data")
STATS = os.path.join(DATA, "stats")
HISTORY = os.path.join(DATA, "history")
PUB_DATA = os.path.join(ROOT, "public", "data")

_parser = argparse.ArgumentParser()
_parser.add_argument("--date", default="20260923", help="賽事日期 YYYYMMDD")
_parser.add_argument("--venue", default="HV", help="場地 HV 或 ST")
_parser.add_argument("--next-date", action="store_true", help="只處理指定 date/venue，忽略 hardcoded ED tips")
_args, _unknown = _parser.parse_known_args()
RACE_DATE = _args.date
VENUE = _args.venue
NEXT_DATE_MODE = bool(_args.next_date)
RACE_DATE_DASH = f"{RACE_DATE[:4]}-{RACE_DATE[4:6]}-{RACE_DATE[6:8]}"

def read_json(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f, object_pairs_hook=OrderedDict)

def write_json(p, data):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

trainer_map = {
    "柏":"方嘉柏","丁":"丁冠豪","廖":"廖康銘","游":"游達榮","黎":"黎昭昇",
    "桂":"桂福特","賢":"蘇偉賢","徐":"徐雨石","韋":"韋達","巫":"巫偉傑",
    "希":"大衛希斯","蔡":"蔡約翰","葉":"葉楚航","伍":"伍鵬志","呂":"呂健威",
    "沈":"沈集成","賀":"賀賢","羅":"羅富全","告":"告東尼","鄭":"鄭俊偉",
    "文":"文家良","霍":"霍利時","鮑":"鮑敘維","蘇":"蘇保羅","姚":"姚本輝"
}

jkc_path = os.path.join(STATS, f"jkcstat_{RACE_DATE}.json")
if os.path.isfile(jkc_path):
    jkc = read_json(jkc_path)
else:
    import datetime as dt0
    jkc = OrderedDict([
        ("meta", OrderedDict([
            ("generated_at", dt0.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            ("race_date", RACE_DATE_DASH),
            ("venue", VENUE),
            ("note", f"auto-created empty jkcstat for {RACE_DATE_DASH} {VENUE}"),
        ])),
        ("jockeys", OrderedDict()),
        ("trainers", OrderedDict()),
        ("combo", OrderedDict()),
    ])

cc_barrier = None
cc_trackwork = None
ranges = list(_cc_raw_data.RANGES)
ED_HARDCODED_DATE = "20260923"
ED = []
# Only load hardcoded expert tips for original 2026-09-23 / non-next-date mode
if (RACE_DATE == ED_HARDCODED_DATE) and not NEXT_DATE_MODE:
    ED = [
        ("卡洛斯", [
            (7,1,"東來欣賞",1),(7,8,"首飾悟空",2),(7,12,"丞匡掠影",3),(7,4,"競駿皇者",4),
            (8,8,"繼往開來",1),(8,1,"人和家興",2),(8,4,"久久為昇",3),(8,11,"驕陽雄心",4)
        ]),
        ("匡公", [
            (7,12,"丞匡掠影",1),(7,1,"東來欣賞",2),(7,8,"首飾悟空",3),(7,11,"盈妍威楓",4),
            (8,8,"繼往開來",1),(8,11,"驕陽雄心",2),(8,6,"富國兄弟",3),(8,4,"久久為昇",4)
        ]),
        ("金駒", [
            (4,9,"將傲",1),(4,6,"快樂神駒",2),(4,11,"焦點",3),(4,4,"星辰千帥",4),
            (7,3,"天星",1),(7,11,"盈妍威楓",2),(7,10,"正極",3),(7,8,"首飾悟空",4)
        ]),
        ("西門獨", [
            (5,6,"越駿聯歡",1),(5,5,"創科群英",2),(5,3,"大學生",3),(5,1,"本領非凡",4),
            (8,9,"蓮冠皇",1),(8,4,"久久為昇",2),(8,8,"繼往開來",3),(8,2,"團結勇士",4)
        ]),
        ("諸葛數", [
            (2,4,"馬馳登",1),(2,1,"紅愛舍",2),(2,3,"路路勁",3),(2,5,"飛輪霸",4),
            (6,1,"福進",1),(6,4,"巴閉王",2),(6,3,"藍地球",3),(6,5,"佐治傳奇",4)
        ]),
        ("長風", [
            (4,6,"快樂神駒",1),(4,4,"星辰千帥",2),(4,9,"將傲",3),(4,3,"應龍飛影",4),
            (7,1,"東來欣賞",1),(7,8,"首飾悟空",2),(7,3,"天星",3),(7,11,"盈妍威楓",4)
        ]),
        ("陳志懷", [
            (4,3,"應龍飛影",1),(4,6,"快樂神駒",2),(4,9,"將傲",3),(4,2,"智勝一籌",4),
            (7,3,"天星",1),(7,2,"乘數表",2),(7,1,"東來欣賞",3),(7,8,"首飾悟空",4)
        ]),
        ("明治朗", [
            (1,11,"東方魅影",1),(1,8,"電訊驕陽",2),(1,3,"神駒馬靈",3),(1,6,"開心三多",4),
            (3,12,"得意佳作",1),(3,2,"贏玥",2),(3,5,"凝妙星",3),(3,7,"有情有義",4)
        ]),
        ("內幕料", [
            (1,3,"神駒馬靈",1),(1,6,"開心三多",2),(1,8,"電訊驕陽",3),(1,11,"東方魅影",4),
            (8,2,"團結勇士",1),(8,3,"富心星",2),(8,8,"繼往開來",3),(8,9,"蓮冠皇",4)
        ]),
        ("網中神", [
            (3,2,"贏玥",1),(3,5,"凝妙星",2),(3,6,"領航天子",3),(3,7,"有情有義",4),
            (7,1,"東來欣賞",1),(7,3,"天星",2),(7,8,"首飾悟空",3),(7,11,"盈妍威楓",4)
        ]),
        ("洛飛", [
            (4,1,"沙井之友",1),(4,3,"應龍飛影",2),(4,4,"星辰千帥",3),(4,6,"快樂神駒",4),
            (9,2,"紫荊傳令",1),(9,6,"將義",2),(9,8,"豐辰",3),(9,9,"中國心",4)
        ]),
    ]

# Try dynamic cache first (HTML cache fetched by scheduler.ps1 PowerShell Invoke-WebRequest)
try:
    cc_barrier = _cc_raw_data.fetch_barrier_for(RACE_DATE_DASH, VENUE)
    print("[POPULATE][DYNAMIC] barrier loaded from cache: %s races" % len(cc_barrier))
except (FileNotFoundError, ValueError) as _e:
    if RACE_DATE == ED_HARDCODED_DATE:
        cc_barrier = _cc_raw_data.BARRIER
        print("[POPULATE][FALLBACK] barrier: hardcoded 2026-09-23 (%s)" % _e)
    else:
        cc_barrier = OrderedDict()
        print("[POPULATE][SKIP] barrier: no dynamic cache, not original date (%s)" % _e)
try:
    cc_trackwork = _cc_raw_data.fetch_trackwork_for(RACE_DATE_DASH, VENUE)
    print("[POPULATE][DYNAMIC] trackwork loaded from cache: %s races" % len(cc_trackwork))
except (FileNotFoundError, ValueError) as _e:
    if RACE_DATE == ED_HARDCODED_DATE:
        cc_trackwork = _cc_raw_data.TRACKWORK
        print("[POPULATE][FALLBACK] trackwork: hardcoded 2026-09-23 (%s)" % _e)
    else:
        cc_trackwork = OrderedDict()
        print("[POPULATE][SKIP] trackwork: no dynamic cache, not original date (%s)" % _e)

tips_by_race = {}
detail_by_race = {}
total_tips = 0
expert_names_used = []
if cc_barrier:
    for rk in cc_barrier.keys():
        tips_by_race[rk] = {}
        detail_by_race[rk] = []
if cc_trackwork:
    for rk in cc_trackwork.keys():
        if rk not in tips_by_race:
            tips_by_race[rk] = {}
            detail_by_race[rk] = []
if not tips_by_race:
    tips_by_race = {f"race_{i}": {} for i in range(1, 15)}
    detail_by_race = {f"race_{i}": [] for i in range(1, 15)}

for expert, lst in ED:
    expert_names_used.append(expert)
    for (race_no, hno, name, rank) in lst:
        rk = f"race_{race_no}"
        if rk not in tips_by_race:
            tips_by_race[rk] = {}
            detail_by_race[rk] = []
        detail_by_race[rk].append(OrderedDict([
            ("expert", expert), ("horse_no", int(hno)), ("name", name), ("rank", int(rank))
        ]))
        bucket = tips_by_race[rk]
        if hno not in bucket:
            bucket[hno] = OrderedDict([("horse_no",int(hno)),("name",name),("count",0),("experts",[])])
        bucket[hno]["count"] += 1
        bucket[hno]["experts"].append(expert)
        total_tips += 1

cc_expert_tips = OrderedDict()
cc_hot_horses = OrderedDict()
all_hot = []

for rk in tips_by_race:
    items = []
    for hno in sorted(tips_by_race[rk].keys(), key=lambda x:int(x)):
        e = tips_by_race[rk][hno]
        items.append(OrderedDict([
            ("horse_no", int(e["horse_no"])), ("name", e["name"]),
            ("count", int(e["count"])), ("experts", list(e["experts"]))
        ]))
        rn = int(rk.replace("race_",""))
        all_hot.append(OrderedDict([("race_no",rn),("horse_no",int(e["horse_no"])),
            ("name",e["name"]),("count",int(e["count"])),("experts",list(e["experts"]))]))
    cc_expert_tips[rk] = items
    cc_hot_horses[rk] = sorted(items, key=lambda x:-x["count"])
cc_hot_horses["top_global"] = sorted(all_hot, key=lambda x:(-x["count"], -x["race_no"]))[:30]
cc_expert_tips_detail = {rk:detail_by_race[rk] for rk in detail_by_race}

jkc["cc_expert_tips"] = cc_expert_tips
jkc["cc_expert_tips_detail"] = cc_expert_tips_detail
jkc["cc_hot_horses"] = cc_hot_horses
jkc["cc_barrier"] = cc_barrier
jkc["cc_trackwork"] = cc_trackwork

cc_sources_items = [
    ("expert_fav_page", "https://racing.on.cc/racing/fav/current/rjfavg0001x0.html"),
    ("expert_count", len(expert_names_used)),
    ("expert_names", list(expert_names_used)),
    ("total_tips_analyzed", int(total_tips)),
    ("merge_key_rule", "Primary: (race_no + horse_no); Secondary: name cross-validate only"),
    ("date", RACE_DATE_DASH),
    ("venue", VENUE),
    ("dynamic_cache_used_barrier", bool(cc_barrier and RACE_DATE != ED_HARDCODED_DATE)),
    ("dynamic_cache_used_trackwork", bool(cc_trackwork and RACE_DATE != ED_HARDCODED_DATE)),
]
detected_rn = set()
for rk in list(cc_barrier.keys()) + list(cc_trackwork.keys()) + list(tips_by_race.keys()):
    if rk.startswith("race_"):
        try:
            detected_rn.add(int(rk.replace("race_","")))
        except:
            pass
for rn in sorted(detected_rn):
    cc_sources_items.append(("barrier_race_%d_page" % rn,
        "https://racing.on.cc/racing/ifo/current/rjifoa%04dx0.html" % rn))
    cc_sources_items.append(("trackwork_race_%d_page" % rn,
        "https://racing.on.cc/racing/mor/current/rjmorc%04dx0.html" % rn))
jkc["cc_sources"] = OrderedDict(cc_sources_items)
import datetime as dt
jkc["meta"]["note"] = (
    f"JKC stats ({VENUE} {RACE_DATE_DASH}) + racing.on.cc 3大核心："
    f"最後來料({len(expert_names_used)}名家{total_tips} tips) + "
    f"barrier({len(cc_barrier)}場) + trackwork({len(cc_trackwork)}場)；merge cc_* 欄位入 CURRENT race JSON"
)
jkc["meta"]["cc_fetch_time"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
if "meta" not in jkc:
    jkc["meta"] = OrderedDict()
elif not isinstance(jkc["meta"], OrderedDict):
    jkc["meta"] = OrderedDict(jkc["meta"])

write_json(jkc_path, jkc)
rn_list = sorted([int(k.replace("race_","")) for k in cc_barrier.keys() if k.startswith("race_")])
total_b = sum(len(cc_barrier['race_%d' % rn]) for rn in rn_list if ('race_%d' % rn) in cc_barrier)
rn_list2 = sorted([int(k.replace("race_","")) for k in cc_trackwork.keys() if k.startswith("race_")])
total_t = sum(len(cc_trackwork['race_%d' % rn]) for rn in rn_list2 if ('race_%d' % rn) in cc_trackwork)
print("[POPULATE OK] jkcstat=%s expert_tips=%d, barrier=%d races total %d匹, trackwork=%d races total %d匹" % (
    os.path.basename(jkc_path), total_tips, len(cc_barrier), total_b, len(cc_trackwork), total_t))

# ---- MERGE into CURRENT race JSONs ----
races_with_data = set()
for rk in list(tips_by_race.keys()) + list(cc_barrier.keys()) + list(cc_trackwork.keys()):
    if not rk.startswith("race_"): continue
    rn = int(rk.replace("race_",""))
    races_with_data.add(rn)

print(f"[MERGE] Races with cc_* data: {sorted(races_with_data)}")

import glob, re
merged_count = 0
total_horses = 0

for race_no in sorted(races_with_data):
    pat = os.path.join(HISTORY, f"{VENUE}-{RACE_DATE}-{race_no:02d}_race{race_no}_*_CURRENT.json")
    matches = glob.glob(pat)
    if not matches:
        print(f"[MERGE][WARN] R{race_no} CURRENT JSON not found: {pat}")
        continue
    rf = matches[0]
    race = read_json(rf)
    fld = f"race_{race_no}"
    for h in race["horses"]:
        total_horses += 1
        hno = int(h["number"])

        if fld in cc_expert_tips:
            arr = [e for e in cc_expert_tips[fld] if int(e["horse_no"]) == hno]
            if arr:
                et = arr[0]
                h["cc_expert_count"] = int(et["count"])
                h["cc_experts"] = list(et["experts"])
                det = [OrderedDict([("expert",d["expert"]),("rank",int(d["rank"]))])
                       for d in cc_expert_tips_detail.get(fld,[]) if int(d["horse_no"])==hno]
                h["cc_expert_tips"] = det
            else:
                h["cc_expert_count"] = 0
                h["cc_experts"] = []
                h["cc_expert_tips"] = []

        if fld in cc_barrier:
            barr = [b for b in cc_barrier[fld] if int(b["horse_no"]) == hno]
            if barr:
                b = barr[0]
                h["cc_gear_symbols"] = b["gear_symbols"]
                h["cc_equipment"] = b["equipment"]
                if b.get("draw"): h["cc_draw_oncc"] = int(b["draw"])
                if b.get("jockey"): h["cc_jockey_oncc"] = b["jockey"]
                h["cc_weight_lbs_oncc"] = int(b["weight_lbs"])
                if "weight_change" in b: h["cc_weight_change"] = int(b["weight_change"])
                if b.get("trainer_surname"):
                    h["cc_trainer_surname"] = b["trainer_surname"]
                    h["cc_trainer_oncc"] = trainer_map.get(b["trainer_surname"], b["trainer_surname"])
                if b.get("rating_cc"): h["cc_rating_oncc"] = int(b["rating_cc"])
                if "rating_change" in b: h["cc_rating_change"] = int(b["rating_change"])
                if b.get("age"): h["cc_age_oncc"] = int(b["age"])
                if b.get("body_weight_lbs"): h["cc_body_weight_lbs"] = int(b["body_weight_lbs"])
                if "body_weight_change" in b: h["cc_body_weight_change"] = int(b["body_weight_change"])
                if b.get("name_oncc") and b["name_oncc"] != b["name"]:
                    h["cc_name_oncc"] = b["name_oncc"]

        if fld in cc_trackwork:
            twa = [t for t in cc_trackwork[fld] if int(t["horse_no"]) == hno]
            if twa:
                t = twa[0]
                h["cc_trackwork_summary"] = t["trackwork_summary"]
                daily_od = OrderedDict()
                for k in t["trackwork_daily"]:
                    daily_od[k] = t["trackwork_daily"][k]
                h["cc_trackwork_daily"] = daily_od
                if t.get("trainer_surname") and "cc_trainer_surname" not in h:
                    h["cc_trainer_surname"] = t["trainer_surname"]
                    h["cc_trainer_oncc"] = trainer_map.get(t["trainer_surname"], t["trainer_surname"])

        merged_count += 1

    write_json(rf, race)
    pub_path = os.path.join(PUB_DATA, "history", os.path.basename(rf))
    if os.path.isdir(os.path.dirname(pub_path)):
        shutil.copy2(rf, pub_path)
    print(f"[MERGE] R{race_no}: {len(race['horses'])} horses updated -> {os.path.basename(rf)}")

# Sync jkcstat to public/data/stats
jkc_pub = os.path.join(PUB_DATA, "stats", os.path.basename(jkc_path))
if os.path.isdir(os.path.dirname(jkc_pub)):
    shutil.copy2(jkc_path, jkc_pub)
    print(f"[MERGE] jkcstat synced -> public/data/stats")

print(f"\n[DONE] Total merged: {merged_count}/{total_horses} horses with cc_* fields", flush=True)
