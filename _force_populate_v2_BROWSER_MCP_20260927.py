#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_force_populate_v2_BROWSER_MCP_20260927.py
HKJC bet.hkjc wp page document.body.innerText TAB DELIMITED 結構（從 integrated_browser evaluate 睇到）：
每行 馬號 之後 4 行 -> name+draw+weight+jockey+trainer，之後 第5行 獨贏, 第6行 位置。
因為 python urllib scrapes 到 txtLen=1453 只係 login shell 骨架，冇 odds，
但用 real browser 打開後 DOM 有完整 innerText，所以呢個 script 唔再 scrap HKJC，
改為 由 user 手動 貼上 body.innerText 到 data/_hkjc_wp_raw/ 目錄 11 個 txt files 然後 parse 寫 JSON。
不過為了 FULLY AUTOMATIC，我哋會直接 模擬 browser evaluate 入面見到的 12 匹馬 odds pattern:
因為我哋有 11 JSON 嘅馬匹名，所以我可以用 browser 逐場 R1..R11 evaluate return 馬匹 odds list，
然後用 python stdin 讀取 browser output → apply 到 JSON。但咁樣要人手 copy/paste 11 次 output。
ALTERNATIVE FULL-AUTO 呢一刻：我哋已經喺 browser tab 有 R1 innerText。
寫 parser 兼容呢種格式，並且之後 做 integrated_browser R2..R11 navigate + evaluate + append 到 stdout。
呢個 script 暫時 用作 CLI：每場叫 evaluate script 得到 JSON 直接 parse。
"""
import re
import json
import os
import sys
from collections import OrderedDict

ROOT = os.path.dirname(os.path.abspath(__file__))
HIST = os.path.join(ROOT, "data", "history")


def find_race_json(rn, ymd="20260927", venue="ST"):
    pref = f"{venue}-{ymd}-{int(rn):02d}_race{int(rn)}_"
    for fn in sorted(os.listdir(HIST)):
        if fn.startswith(pref) and fn.endswith(".json") and "_CURRENT" not in fn:
            return os.path.join(HIST, fn)
    return None


def parse_wp_inner_text(txt):
    """Parse innerText from bet.hkjc wp page. Format observed:
    Tab-separated table. Pattern:
    Line with /^\d{1,2}\t\t\t馬名\t檔位\t負磅\t騎師\t練馬師\t\s*$/
    NEXT line:  /\t\d{1,3}(\.\d)?\t\t\d{1,3}(\.\d)?\t\t\t$/
    So split by newlines first, then extract horseNo from first col, win odds = next line first numeric token, place = next numeric after that.
    """
    odds = {}
    if not txt:
        return odds
    lines = txt.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].rstrip("\r")
        cols = [c for c in line.split("\t")]
        stripped = [c.strip() for c in cols]
        # find cols[0] numeric 1-20 then cols[3] horse_name not empty / cols[4] draw
        if len(stripped) >= 7 and re.fullmatch(r"[1-9]|1[0-9]|20", stripped[0]):
            try:
                no = int(stripped[0])
            except Exception:
                i += 1
                continue
            winv = None
            placev = None
            # scan next lines after this one for two numeric odds
            j = i + 1
            found_tokens = []
            while j < len(lines) and len(found_tokens) < 2 and (j - i) < 5:
                parts = [p.strip() for p in lines[j].split("\t") if p.strip()]
                for p in parts:
                    m = re.fullmatch(r"(\d{1,3}(?:\.\d)?)", p)
                    if m:
                        found_tokens.append(float(m.group(1)))
                        if len(found_tokens) >= 2:
                            break
                j += 1
            if len(found_tokens) >= 2:
                winv = found_tokens[0]
                placev = found_tokens[1]
            if 1 <= no <= 20 and (winv or placev):
                odds[no] = (winv, placev)
        i += 1
    return odds


def apply_odds(jpath, odds_map):
    with open(jpath, "r", encoding="utf-8") as f:
        data = json.load(f, object_pairs_hook=OrderedDict)
    cnt = 0
    for h in data.get("horses", []):
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
    import datetime
    meta["odds_update_time"] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    meta["odds_source"] = "bet.hkjc.com WP via browser MCP innerText parser"
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return cnt


if __name__ == "__main__":
    # Usage A: python _force_populate_v2_BROWSER_MCP_20260927.py <race_no> "<body.innerText>"
    # Usage B: Pipe mode: python script.py <race_no> --stdin  < file.txt
    # Usage C: AUTO ALL R1-R11 from data/_hkjc_wp_raw/ST-R<N>.txt files: python script.py --auto-all
    if len(sys.argv) >= 2 and sys.argv[1] == "--auto-all":
        import glob
        raw_dir = os.path.join(ROOT, "data", "_hkjc_wp_raw")
        files = sorted(glob.glob(os.path.join(raw_dir, "ST-R*.txt")), key=lambda p: int(re.search(r"ST-R(\d+)", p).group(1)))
        for fp in files:
            m = re.search(r"ST-R(\d+)", os.path.basename(fp))
            if not m: continue
            rn = int(m.group(1))
            with open(fp, "r", encoding="utf-8") as f:
                txt = f.read()
            jp = find_race_json(rn)
            if not jp:
                print(f"[R{rn}] JSON NOT FOUND"); continue
            om = parse_wp_inner_text(txt)
            print(f"[R{rn}] parsed {len(om)} horses:", dict(list(om.items())[:5]))
            upd = apply_odds(jp, om)
            print(f"[R{rn}] updated odds fields={upd} in {os.path.basename(jp)}")
        sys.exit(0)
    if len(sys.argv) < 3:
        print("Usage: python _force_populate_v2_BROWSER_MCP_20260927.py <race_no> \"<body.innerText>\"")
        print("Pipe mode: python script.py <race_no> --stdin  < file.txt")
        print("Auto-all 11 races from data/_hkjc_wp_raw/ST-R{N}.txt: python script.py --auto-all")
        sys.exit(1)
    rn = int(sys.argv[1])
    if sys.argv[2] == "--stdin":
        txt = sys.stdin.read()
    else:
        txt = sys.argv[2]
    jp = find_race_json(rn)
    if not jp:
        print(f"[R{rn}] JSON NOT FOUND")
        sys.exit(2)
    om = parse_wp_inner_text(txt)
    print(f"[R{rn}] parsed {len(om)} horses:", dict(list(om.items())[:5]))
    upd = apply_odds(jp, om)
    print(f"[R{rn}] updated odds fields={upd} in {os.path.basename(jp)}")
