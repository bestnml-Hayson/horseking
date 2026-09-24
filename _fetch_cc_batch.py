import json
import os
import re
from collections import OrderedDict
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

ROOT = r"d:\Trae\horse"
DATA = os.path.join(ROOT, "data")
STATS = os.path.join(DATA, "stats")
OUT = os.path.join(DATA, "references", "_cc_raw_extract.json")
RACE_DATE = "20260923"
VENUE = "HV"
TOTAL_RACES = 9

def write_json(p, d):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

def parse_barrier_text(raw: str, race_no: int):
    lines = [l.replace("\u00a0", " ").strip() for l in raw.splitlines()]
    lines = [l for l in lines if len(l) > 0]
    header_idx = None
    for i, l in enumerate(lines):
        if re.search(r"馬號\s*馬名.*檔\s*騎師", l):
            header_idx = i
            break
    if header_idx is None:
        return []
    result = []
    for i in range(header_idx + 1, len(lines)):
        l = lines[i]
        if re.search(r"^馬經所提供|^資料只供|B戴眼罩|^賽事日期|^第\d+場|馬名旁數目|註：", l):
            break
        if re.match(r"^(\d+|[Rr]\d*)\s+", l):
            parts = re.split(r"\t", l)
            if len(parts) >= 10:
                result.append(parts)
    return result

def parse_trackwork_text(raw: str, race_no: int):
    lines = [l.replace("\u00a0", " ").strip() for l in raw.splitlines()]
    lines = [l for l in lines if len(l) > 0]
    header_idx = None
    for i, l in enumerate(lines):
        if re.search(r"7-9\s+10-13\s+14-16", l):
            header_idx = i
            break
    if header_idx is None:
        return []
    ranges = ["7-9","10-13","14-16","17-20","21-21","22-22"]
    horses = OrderedDict()
    cur_hno = None
    cur_daily_idx = 0
    i = header_idx + 1
    while i < len(lines):
        l = lines[i]
        if re.search(r"^馬經所提供|^資料只供|^賽事日期|^第\d+場|評級$", l):
            break
        m_head = re.match(r"^(\d+)([\u4e00-\u9fa5][^\t]*)", l)
        if m_head:
            hno = int(m_head.group(1))
            name = m_head.group(2).strip()
            horses[hno] = {
                "horse_no": hno, "name": name, "weight_lbs": None,
                "trainer_surname": None, "daily": [""]*6, "summary": None
            }
            rest_parts = l[len(m_head.group(0)):].split("\t")
            rest_parts = [p for p in rest_parts if p]
            if len(rest_parts) >= 1:
                m_wt = re.search(r"(\d{3})", rest_parts[0])
                if m_wt:
                    horses[hno]["weight_lbs"] = int(m_wt.group(1))
            if len(rest_parts) >= 2:
                tn = rest_parts[1].strip()
                if re.match(r"^[\u4e00-\u9fa5]$", tn):
                    horses[hno]["trainer_surname"] = tn
                elif len(rest_parts) >= 3 and re.match(r"^[\u4e00-\u9fa5]$", rest_parts[2].strip()):
                    horses[hno]["trainer_surname"] = rest_parts[2].strip()
            cur_hno = hno
            cur_daily_idx = 0
            i += 1
            continue
        if cur_hno is None:
            i += 1
            continue
        if cur_daily_idx < 6:
            horses[cur_hno]["daily"][cur_daily_idx] = l.strip()
            cur_daily_idx += 1
            i += 1
            continue
        if re.search(r"(踱步|快跳|泥閘|草閘|彈閘|游水|開操)", l) and horses[cur_hno]["summary"] is None:
            horses[cur_hno]["summary"] = l.strip()
            cur_hno = None
            cur_daily_idx = 0
        i += 1
    out = []
    for hno in sorted(horses.keys()):
        h = horses[hno]
        out.append(OrderedDict([
            ("horse_no", hno), ("name", h["name"]),
            ("trainer_surname", h["trainer_surname"] or ""),
            ("weight_lbs", h["weight_lbs"]),
            ("trackwork_summary", h["summary"] or ""),
            ("trackwork_daily", OrderedDict([(ranges[k], h["daily"][k]) for k in range(6)]))
        ]))
    return out

def main():
    result = OrderedDict([
        ("meta", OrderedDict([
            ("race_date", RACE_DATE), ("venue", VENUE),
            ("total_races", TOTAL_RACES),
            ("url_barrier_tpl", "https://racing.on.cc/racing/ifo/current/rjifoa{:04d}x0.html"),
            ("url_trackwork_tpl", "https://racing.on.cc/racing/mor/current/rjmorc{:04d}x0.html")
        ])),
        ("cc_barrier_raw", OrderedDict()),
        ("cc_trackwork_raw", OrderedDict()),
    ])
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = ctx.new_page()
        for rn in range(1, TOTAL_RACES + 1):
            url = f"https://racing.on.cc/racing/ifo/current/rjifoa{rn:04d}x0.html"
            key = f"race_{rn}"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(1000)
                raw = page.inner_text("body")
                parsed = parse_barrier_text(raw, rn)
                result["cc_barrier_raw"][key] = parsed
                print(f"[BARRIER R{rn}] OK: {len(parsed)} rows -> {url}")
            except PWTimeout as e:
                result["cc_barrier_raw"][key] = f"TIMEOUT: {e}"
                print(f"[BARRIER R{rn}] TIMEOUT")
            except Exception as e:
                result["cc_barrier_raw"][key] = f"ERROR: {type(e).__name__}: {e}"
                print(f"[BARRIER R{rn}] ERROR {type(e).__name__}: {e}")
        for rn in range(1, TOTAL_RACES + 1):
            url = f"https://racing.on.cc/racing/mor/current/rjmorc{rn:04d}x0.html"
            key = f"race_{rn}"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(1200)
                raw = page.inner_text("body")
                parsed = parse_trackwork_text(raw, rn)
                result["cc_trackwork_raw"][key] = parsed
                print(f"[TRACKWORK R{rn}] OK: horses={len(parsed)} -> {url}")
            except PWTimeout as e:
                result["cc_trackwork_raw"][key] = f"TIMEOUT: {e}"
                print(f"[TRACKWORK R{rn}] TIMEOUT")
            except Exception as e:
                result["cc_trackwork_raw"][key] = f"ERROR: {type(e).__name__}: {e}"
                print(f"[TRACKWORK R{rn}] ERROR {type(e).__name__}: {e}")
        browser.close()
    write_json(OUT, result)
    print(f"\n[DONE] Raw extract written -> {OUT}")

if __name__ == "__main__":
    main()
