#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DIRECT: parse browser_evaluate JSON string 11 races and write all 11 JSON at once.
Format per race: from browser_evaluate return, string that starts with " and contains \n and \t,
we just embed R1-R11 here.
"""
import re
import json
import os
import sys
from collections import OrderedDict
import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
HIST = os.path.join(ROOT, "data", "history")

# ============================================================
# EMBEDDED odds map extracted from browser MCP.
# FORMAT: {RACE_NO: {HORSE_NO: (odds_win, odds_place)}}
# ============================================================
RACES = {
    1: {
        1: (5.5, 2.0),
        2: (7.0, 2.7),
        3: (8.4, 2.8),
        4: (20.0, 5.1),
        5: (13.0, 3.4),
        6: (3.1, 1.6),
        7: (30.0, 7.3),
        8: (27.0, 7.5),
        9: (6.8, 1.6),
        10: (18.0, 5.0),
        11: (42.0, 8.5),
        12: (31.0, 7.2),
    },
    2: {
        1: (17.0, 4.2),
        2: (34.0, 8.5),
        3: (69.0, 12.0),
        4: (6.6, 2.3),
        5: (19.0, 5.2),
        6: (16.0, 7.8),
        7: (10.0, 2.9),
        8: (4.5, 1.8),
        9: (12.0, 3.1),
        10: (7.1, 2.5),
        11: (7.4, 2.8),
        12: (5.6, 2.0),
    },
    3: {
        1: (5.1, 2.2),
        2: (8.1, 2.5),
        3: (12.0, 4.1),
        4: (10.0, 3.7),
        5: (16.0, 4.6),
        6: (49.0, 10.0),
        7: (13.0, 4.7),
        8: (8.6, 2.8),
        9: (14.0, 4.5),
        10: (12.0, 3.9),
        11: (5.0, 2.3),
        12: (26.0, 5.1),
        13: (30.0, 6.8),
        14: (33.0, 6.5),
    },
    4: {
        1: (5.0, 2.1),
        2: (10.0, 3.4),
        3: (5.0, 2.2),
        4: (14.0, 5.0),
        5: (40.0, 9.7),
        6: (8.4, 2.6),
        7: (31.0, 7.4),
        8: (27.0, 5.4),
        9: (12.0, 3.4),
        10: (32.0, 7.2),
        11: (13.0, 4.7),
        12: (9.2, 2.9),
        13: (14.0, 3.9),
        14: (14.0, 5.6),
    },
    5: {
        1: (11.0, 3.0),
        2: (9.4, 2.3),
        3: (70.0, 12.0),
        4: (19.0, 4.8),
        5: (6.9, 2.9),
        6: (2.1, 1.4),
        7: (16.0, 3.8),
        8: (9.4, 2.0),
        9: (31.0, 6.4),
        10: (15.0, 2.9),
        11: (16.0, 4.8),
        12: (56.0, 9.8),
    },
    6: {
        1: (7.7, 2.1),
        2: (16.0, 4.8),
        3: (15.0, 5.0),
        4: (7.9, 2.3),
        5: (7.7, 4.0),
        6: (16.0, 4.9),
        7: (52.0, 12.0),
        8: (7.7, 2.6),
        9: (6.6, 3.4),
        10: (28.0, 7.3),
        11: (41.0, 9.8),
        12: (10.0, 3.0),
        13: (6.4, 2.3),
        14: (37.0, 7.9),
    },
    7: {
        1: (8.5, 2.2),
        2: (25.0, 5.3),
        3: (24.0, 5.6),
        4: (32.0, 6.1),
        5: (8.0, 2.5),
        6: (12.0, 2.9),
        7: (41.0, 7.6),
        8: (1.8, 1.7),
        9: (10.0, 1.6),
        10: (42.0, 6.1),
        11: (39.0, 7.9),
        12: (19.0, 3.1),
    },
    8: {
        1: (8.6, 2.5),
        2: (6.4, 1.9),
        3: (4.8, 1.8),
        4: (23.0, 4.4),
        5: (17.0, 3.5),
        6: (2.0, 1.0),
        7: (21.0, 5.0),
        8: (16.0, 2.6),
        9: (28.0, 7.4),
    },
    9: {
        1: (5.1, 1.4),
        2: (24.0, 5.4),
        3: (15.0, 5.5),
        4: (17.0, 5.2),
        5: (17.0, 5.6),
        6: (29.0, 8.3),
        7: (19.0, 4.7),
        8: (2.5, 1.2),
        9: (14.0, 4.0),
        10: (14.0, 4.0),
        11: (21.0, 6.4),
        12: (40.0, 12.0),
        13: (15.0, 5.3),
        14: (22.0, 7.0),
    },
    10: {
        1: (32.0, 6.8),
        2: (15.0, 5.8),
        3: (3.4, 1.5),
        4: (16.0, 4.4),
        5: (13.0, 5.0),
        6: (11.0, 4.0),
        7: (17.0, 5.2),
        8: (5.7, 2.7),
        9: (8.6, 3.0),
        10: (7.2, 1.5),
        11: (15.0, 4.4),
        12: (19.0, 5.1),
    },
    11: {
        1: (16.0, 4.9),
        2: (9.6, 3.4),
        3: (5.6, 2.0),
        4: (12.0, 4.3),
        5: (24.0, 5.7),
        6: (3.3, 1.9),
        7: (12.0, 4.1),
        8: (12.0, 2.9),
        9: (31.0, 10.0),
        10: (9.8, 2.0),
        11: (32.0, 8.9),
        12: (25.0, 8.9),
        13: (31.0, 7.6),
        14: (16.0, 5.4),
    },
}


def expand(remaining_races):
    """
    Fill remaining_races dict inline here via real data from browser after parsing.
    """
    return remaining_races


def find_race_json(rn, ymd="20260927", venue="ST"):
    pref = f"{venue}-{ymd}-{int(rn):02d}_race{int(rn)}_"
    for fn in sorted(os.listdir(HIST)):
        if fn.startswith(pref) and fn.endswith(".json") and "_CURRENT" not in fn:
            return os.path.join(HIST, fn)
    return None


def apply_odds_map(rn, odds_map):
    jp = find_race_json(rn)
    if not jp:
        return (False, f"[R{rn}] JSON NOT FOUND")
    with open(jp, "r", encoding="utf-8") as f:
        data = json.load(f, object_pairs_hook=OrderedDict)
    cnt = 0
    horses = data.get("horses", [])
    for h in horses:
        n = int(h.get("number") or h.get("horse_no") or 0)
        if n in odds_map:
            ow, op = odds_map[n]
            if isinstance(ow, (int, float)) and ow > 1:
                h["odds_win"] = round(float(ow), 1)
                cnt += 1
            if isinstance(op, (int, float)) and op > 1:
                h["odds_place"] = round(float(op), 1)
                cnt += 1
    meta = data.setdefault("meta", OrderedDict())
    meta["odds_update_time"] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    meta["odds_source"] = "bet.hkjc.com/ch/racing/wp/2026-09-27/ST/<R> direct MCP browser parse"
    with open(jp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return (True, f"[R{rn}] OK, fields={cnt}, file={os.path.basename(jp)}")


if __name__ == "__main__":
    from_arg = sys.argv[1:] if len(sys.argv) > 1 else []
    all_races = dict(RACES)
    if from_arg and from_arg[0] == "--merge-remaining":
        # expects: argv[2:] = list of "rn:no=win/place"
        bucket = {}
        for spec in from_arg[1:]:
            m = re.match(r"R(\d+):(\d+)=([\d.]+)/([\d.]+)$", spec)
            if m:
                r = int(m.group(1)); h = int(m.group(2)); w = float(m.group(3)); p = float(m.group(4))
                bucket.setdefault(r, {})[h] = (w, p)
        for r, mp in bucket.items():
            cur = dict(all_races.get(r, {})); cur.update(mp); all_races[r] = cur
    any_missing = False
    for r in range(1, 12):
        if r not in all_races:
            any_missing = True
            print(f"[WARN] R{r} not embedded yet. Use --merge-remaining with the remaining races' specs.")
    updated = 0
    for rn in sorted(all_races.keys()):
        ok, info = apply_odds_map(rn, all_races[rn])
        print(info)
        if ok: updated += 1
    print(f"\n[DONE] Races populated: {updated}/11. Missing embed data for races? {any_missing}")
