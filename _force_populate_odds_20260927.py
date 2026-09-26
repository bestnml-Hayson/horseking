#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_force_populate_odds_20260927.py
URGENT FALLBACK: 唔靠 Chrome CDP / _CURRENT.json。
直接 urllib GET bet.hkjc.com/ch/racing/wp/2026-09-27/ST/{1..11} HTML，
parse 馬號/獨贏/位置 odds，寫入 data/history/ST-20260927-*.json 11 個 files。
HKJC wp page markup - 馬匹 entries 列表入面 win odds 通常有 class*='win' 或者 attribute data-win，
冇固定 class 就 parse 所有 table cells 找 pattern：horse no [1-20] followed by two decimal odds 1.1 - 999.9
"""
import re
import json
import os
import sys
import urllib.request
import urllib.error
from collections import OrderedDict
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.abspath(__file__))
HIST = os.path.join(ROOT, "data", "history")
BASE = "https://bet.hkjc.com/ch/racing/wp/2026-09-27/ST"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"


def get(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-HK,zh-TW,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="ignore")


def extract_numbers_from_text(text):
    """Generic 暴力 parse: (馬號, 獨贏, 位置) tuples"""
    results = {}
    lines = text.replace('</tr>', '\n').replace('</div>', '\n').replace('<br>', ' ')
    lines = re.sub(r'<[^>]+>', '\t', lines)
    tokens = [t.strip() for t in re.split(r'[\t\r\n]+', lines) if t.strip()]
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if re.fullmatch(r'[1-9]|1[0-9]|20', tok):
            horse_no = int(tok)
            win_odds = None
            place_odds = None
            j = i + 1
            scans = 0
            while j < len(tokens) and scans < 30:
                t = tokens[j]
                m = re.fullmatch(r'(\d{1,3}(?:\.\d)?)', t)
                if m:
                    v = float(m.group(1))
                    if 1.0 < v < 999.9:
                        if win_odds is None:
                            win_odds = v
                        elif place_odds is None and place_odds != win_odds:
                            place_odds = v
                            break
                scans += 1
                j += 1
            if horse_no not in results or win_odds:
                if horse_no <= 20 and (win_odds or place_odds):
                    results[horse_no] = (win_odds, place_odds)
        i += 1
    return results


def match_place_and_odds(text):
    """Regex extractor with look-around for horse-no followed by win then place.
    patterns like \"...1 <...> 8.5 <...> 3.2 ...\" """
    out = {}
    pattern = re.compile(
        r'(?:^|[\s>"])(?P<no>[1-9]|1[0-9]|20)(?:[\s<"]{1,80}?)(?P<win>\d{1,3}\.\d)(?:[\s<"]{1,200}?)(?P<place>\d{1,3}\.\d)',
        re.IGNORECASE | re.MULTILINE,
    )
    for m in pattern.finditer(text):
        try:
            no = int(m.group('no'))
            w = float(m.group('win'))
            p = float(m.group('place'))
            if 1.0 < w < 1000 and 1.0 < p < 1000 and p < w + 10:
                if no not in out:
                    out[no] = (w, p)
        except Exception:
            pass
    return out


def parse_race_html(raw_html, race_no):
    out1 = match_place_and_odds(raw_html)
    out2 = extract_numbers_from_text(raw_html)
    merged = dict(out2)
    for k, v in out1.items():
        merged[k] = v
    return merged


def find_race_json(race_no):
    ymd = "20260927"
    suffix = f"ST-{ymd}-{int(race_no):02d}_race{int(race_no)}_"
    for fn in sorted(os.listdir(HIST)):
        if fn.startswith(suffix) and fn.endswith(".json") and "_CURRENT" not in fn:
            return os.path.join(HIST, fn)
    return None


def apply_odds(json_path, odds_map):
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f, object_pairs_hook=OrderedDict)
    except Exception as e:
        return (False, f"read fail: {e}")
    updates = 0
    for h in data.get("horses", []):
        n = int(h.get("number") or h.get("horse_no") or 0)
        if n in odds_map:
            ow, op = odds_map[n]
            if ow and isinstance(ow, (int, float)) and ow > 1:
                prev = float(h.get("odds_win") or 0)
                if abs(prev - ow) > 0.05:
                    h["odds_win"] = round(float(ow), 1)
                    updates += 1
            if op and isinstance(op, (int, float)) and op > 1:
                prev = float(h.get("odds_place") or 0)
                if abs(prev - op) > 0.05:
                    h["odds_place"] = round(float(op), 1)
                    updates += 1
    meta = data.setdefault("meta", OrderedDict())
    import datetime
    meta["odds_update_time"] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    meta["odds_source"] = "bet.hkjc.com WP html fallback scraper"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return (True, updates)


def report(msg, file=None):
    print(msg, flush=True)
    if file:
        try:
            ts = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(file, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {msg}\n")
        except Exception:
            pass


def main():
    logfile = os.path.join(ROOT, "_force_populate_odds_log.txt")
    total_updated_files = 0
    for rn in range(1, 12):
        url = f"{BASE}/{rn}"
        jp = find_race_json(rn)
        report(f"\n[R{rn}] source: {url}", logfile)
        report(f"[R{rn}] target: {os.path.basename(jp) if jp else 'NOT FOUND'}", logfile)
        if not jp:
            report(f"[R{rn}] SKIP JSON NOT FOUND", logfile)
            continue
        try:
            raw = get(url)
        except urllib.error.HTTPError as e:
            report(f"[R{rn}] HTTP {e.code}", logfile)
            continue
        except Exception as e:
            report(f"[R{rn}] NET {e}", logfile)
            continue
        odds_map = parse_race_html(raw, rn)
        report(f"[R{rn}] parsed horses with odds: {sorted(odds_map.keys())} ({len(odds_map)}匹)", logfile)
        if odds_map:
            report(f"[R{rn}] sample odds: " +
                   ", ".join([f"#{k} W:{v[0]} P:{v[1]}" for k, v in list(odds_map.items())[:3]]), logfile)
        ok, info = apply_odds(jp, odds_map)
        if ok:
            report(f"[R{rn}] OK, updated fields={info}", logfile)
            if info and info > 0:
                total_updated_files += 1
        else:
            report(f"[R{rn}] FAIL apply, {info}", logfile)
    report(f"\n[DONE] files with odds updates: {total_updated_files}/11", logfile)
    return 0


if __name__ == "__main__":
    sys.exit(main())
