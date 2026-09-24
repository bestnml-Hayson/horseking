# -*- coding: utf-8 -*-
"""
_fetch_live_odds.py（通用化 WP 賠率抓取）
從 bet.hkjc.com/ch/racing/wp/{YYYY-MM-DD}/{VC}/{race_no} 抓獨贏 + 位置 odds，
用 Chrome CDP（WebSocket evaluate）抓 body.innerText，parse 後更新對應 CURRENT JSON 嘅 horses[i].odds_win / odds_place。
CLI:
  python _fetch_live_odds.py --date 2026-09-23 --venue HV --races 1,2,3,4,5,6,7,8,9
  python _fetch_live_odds.py --date 2026-09-30 --venue HV  # 自動掃描當日所有 CURRENT races
若 Chrome CDP 或 websocket 失敗 → 不會 raise 連線失敗 skip 但不 crash（scheduler.ps1 每 3 min loop 重抓）。
"""
import sys
import os
import re
import json
import time
import argparse
import subprocess
import urllib.request
import http.client
from collections import OrderedDict
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
HIST_DIR = os.path.join(ROOT, "data", "history")
LOG_FILE = os.path.join(ROOT, "_fetch_odds_log.txt")

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]
USER_DATA_DIR = os.path.join(ROOT, ".cdp_profile3")
DEBUG_PORT = 9226  # 與 odds R4-R9 用 9225，避撞
CDP_TIMEOUT = 20
PAGE_SLEEP = 5

try:
    _logf = open(LOG_FILE, "a", encoding="utf-8")
except Exception:
    _logf = sys.stderr


def log(msg):
    try:
        print(msg, flush=True)
    except Exception:
        pass
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _logf.write(f"[{ts}] {msg}\n")
        _logf.flush()
    except Exception:
        pass


def find_chrome():
    for p in CHROME_PATHS:
        if os.path.isfile(p):
            return p
    return None


def http_get(url, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def cdp_list_targets(port):
    """list /json 列表，取 page target。"""
    import json as _json
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=8)
    try:
        conn.request("GET", "/json")
        resp = conn.getresponse().read().decode("utf-8", errors="ignore")
        conn.close()
        arr = _json.loads(resp)
        for t in arr:
            if t.get("type") == "page":
                return t
        return arr[0] if arr else None
    except Exception as e:
        log(f"[WARN] cdp_list_targets fail: {e}")
        return None
    finally:
        try: conn.close()
        except: pass


def cdp_evaluate(port, target_ws_url, js):
    """WebSocket CDP Runtime.evaluate，回傳 result.value。"""
    try:
        import websocket
    except Exception:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client", "-q"])
            import websocket
        except Exception as ex:
            raise RuntimeError(f"websocket-client install fail: {ex}")
    payload = json.dumps({
        "id": 1, "method": "Runtime.evaluate",
        "params": {"expression": js, "returnByValue": True}
    }).encode("utf-8")
    ws = websocket.create_connection(target_ws_url, timeout=CDP_TIMEOUT)
    try:
        ws.send(payload)
        raw = ws.recv()
    finally:
        ws.close()
    data = json.loads(raw)
    try:
        return data["result"]["result"]["value"]
    except KeyError:
        log(f"[WARN] CDP evaluate 冇 result: {str(data)[:400]}")
        return None


EVALUATE_SCRIPT = r"""
(function(){
  const txt = document.body.innerText || '';
  const headerIdx = txt.indexOf('馬號\t綵衣\t馬名\t檔位\t負磅\t騎師\t練馬師\t獨贏\t位置');
  const src = headerIdx >= 0 ? txt.substring(headerIdx) : txt;
  const lines = src.split(/\n/);
  const horses = [];
  let i = 1;
  while (i < lines.length) {
    const cols = lines[i].split('\t');
    const c0 = (cols[0]||'').trim();
    if (/^\d{1,2}$/.test(c0)) {
      const horseNo = parseInt(c0,10);
      i++;
      while (i < lines.length && !lines[i].trim()) i++;
      let name='', draw='', weight='', jockey='', trainer='';
      if (i < lines.length) {
        const infoCols = lines[i].split('\t').map(s=>s.trim());
        let ci = 0;
        while (ci < infoCols.length && infoCols[ci]==='') ci++;
        if (ci < infoCols.length) name = infoCols[ci++];
        if (ci < infoCols.length) draw = infoCols[ci++];
        if (ci < infoCols.length) weight = infoCols[ci++];
        if (ci < infoCols.length) jockey = infoCols[ci++];
        if (ci < infoCols.length) trainer = infoCols[ci++];
        i++;
      }
      while (i < lines.length && !lines[i].trim()) i++;
      let oddsWin = NaN, oddsPlace = NaN;
      if (i < lines.length) {
        const wCols = lines[i].split('\t').map(s=>s.trim()).filter(s=>s.length>0);
        if (wCols.length && /^\d{1,3}(\.\d)?$/.test(wCols[0])) oddsWin = parseFloat(wCols[0]);
        i++;
      }
      while (i < lines.length && !lines[i].trim()) i++;
      if (i < lines.length) {
        const pCols = lines[i].split('\t').map(s=>s.trim()).filter(s=>s.length>0);
        if (pCols.length && /^\d{1,3}(\.\d)?$/.test(pCols[0])) oddsPlace = parseFloat(pCols[0]);
        i++;
      }
      if (name && horseNo>=1 && horseNo<=20) {
        horses.push({number:horseNo,name,draw,weight,jockey,trainer,odds_win:oddsWin,odds_place:oddsPlace});
      }
    } else if (c0.includes('全餐') || (lines[i]||'').includes('總投注額')) {
      break;
    } else {
      i++;
    }
  }
  const rnm = src.match(/第\s*(\d+)\s*場/);
  const ut = src.match(/更新時間:\s*([\d\s\/:]+?)(?:\n|$)/);
  return {url: location.href, raceNumber: rnm? parseInt(rnm[1],10):null, updateTime: ut? ut[1].trim():null, horseCount: horses.length, horses};
})();
"""


def find_current_for(venue_ymd, venue_code, race_no):
    """Return path or None."""
    ymd_c = venue_ymd.replace("-", "")
    pat = re.compile(
        rf"^{venue_code}-{ymd_c}-{int(race_no):02d}_race{int(race_no)}_.*_CURRENT\.json$"
    )
    if not os.path.isdir(HIST_DIR):
        return None
    for fn in sorted(os.listdir(HIST_DIR)):
        if pat.match(fn):
            return os.path.join(HIST_DIR, fn)
    return None


def scan_all_currents(venue_ymd, venue_code):
    out = []
    ymd_c = venue_ymd.replace("-", "")
    pat = re.compile(rf"^{venue_code}-{ymd_c}-(\d{{2}})_race(\d+)_.*_CURRENT\.json$")
    if os.path.isdir(HIST_DIR):
        for fn in sorted(os.listdir(HIST_DIR)):
            m = pat.match(fn)
            if m:
                out.append(int(m.group(2)))
    return sorted(set(out))


def ensure_chrome_running():
    """如果冇 CDP 冇回應就 launch Chrome。"""
    t = cdp_list_targets(DEBUG_PORT)
    if t:
        return True
    chrome = find_chrome()
    if not chrome:
        log("[SKIP] 冇 Chrome/Edge 安裝路徑")
        return False
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    cmd = [
        chrome,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--no-first-run", "--no-default-browser-check",
        "--disable-popup-blocking", "--disable-gpu",
        "--bwsi", "--headless=new",
        "about:blank",
    ]
    log(f"[LAUNCH] Chrome 啟動中: {' '.join(cmd[:4])}...")
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        log(f"[FAIL] Chrome 啟動 fail: {e}")
        return False
    deadline = time.time() + 20
    while time.time() < deadline:
        time.sleep(1.5)
        if cdp_list_targets(DEBUG_PORT):
            return True
    log("[FAIL] Chrome CDP timeout")
    return False


def cdp_navigate(ws_url, url, sleep_sec=PAGE_SLEEP):
    try:
        import websocket
    except Exception as e:
        raise RuntimeError(str(e))
    nav = json.dumps({
        "id": 2, "method": "Page.navigate",
        "params": {"url": url}
    }).encode("utf-8")
    ws = websocket.create_connection(ws_url, timeout=CDP_TIMEOUT)
    try:
        ws.send(nav)
        for _ in range(120):
            try:
                ws.recv()
            except Exception:
                break
    finally:
        ws.close()
    time.sleep(max(1, sleep_sec))


def apply_odds_to_current(current_path, odds_payload):
    """odds_payload: {horseNo: {odds_win, odds_place}}"""
    try:
        with open(current_path, "r", encoding="utf-8") as f:
            data = json.load(f, object_pairs_hook=OrderedDict)
    except Exception as e:
        log(f"  [FAIL] 讀 CURRENT fail: {e}")
        return False
    updated = 0
    code = None
    for h in data.get("horses", []):
        n = int(h.get("number") or 0)
        if n and n in odds_payload:
            o = odds_payload[n]
            try: ow = float(o.get("odds_win"))
            except: ow = None
            try: op = float(o.get("odds_place"))
            except: op = None
            if ow and ow > 0 and not (h.get("odds_win")):
                h["odds_win"] = ow
                updated += 1
            elif ow and ow > 0:
                if abs(float(h.get("odds_win") or 0) - ow) > 0.05:
                    h["odds_win"] = ow
                    updated += 1
            if op and op > 0 and not (h.get("odds_place")):
                h["odds_place"] = op
                updated += 1
            elif op and op > 0:
                if abs(float(h.get("odds_place") or 0) - op) > 0.05:
                    h["odds_place"] = op
                    updated += 1
    meta = data.setdefault("meta", OrderedDict())
    meta["odds_update_time"] = datetime.now().strftime("%d/%m/%Y %H:%M")
    meta["odds_source"] = f"bet.hkjc.com WP live"
    try:
        with open(current_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"  [FAIL] 寫 CURRENT fail: {e}")
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--venue", required=True, help="HV 或 ST")
    ap.add_argument("--races", default=None, help="1,2,3,... 冇指定自動掃")
    ap.add_argument("--sleep", type=int, default=PAGE_SLEEP)
    args = ap.parse_args()
    venue_code = args.venue.strip().upper()
    venue_ymd = args.date.strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", venue_ymd):
        raise SystemExit("--date 需 YYYY-MM-DD")
    if args.races:
        race_nums = [int(x) for x in re.split(r"[,;\s]+", args.races) if x.isdigit()]
    else:
        race_nums = scan_all_currents(venue_ymd, venue_code)
        if not race_nums:
            log(f"[SCAN] {venue_ymd} {venue_code} 冇 CURRENT JSON，quit")
            print(json.dumps({"ok": True, "updated_files": 0, "errors": ["no CURRENT files"]}, ensure_ascii=False))
            return 0
    log(f"[START] date={venue_ymd} venue={venue_code} races={race_nums}")
    ok = ensure_chrome_running()
    summary = OrderedDict([
        ("ok", ok), ("date", venue_ymd), ("venue", venue_code),
        ("races", []), ("updated_files", 0), ("errors", []),
    ])
    if not ok:
        summary["errors"].append("Chrome CDP 無法啟動")
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    target = cdp_list_targets(DEBUG_PORT)
    if not target or "webSocketDebuggerUrl" not in target:
        summary["errors"].append("CDP 冇 page target/ws url")
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    ws_url = target["webSocketDebuggerUrl"]
    base = f"https://bet.hkjc.com/ch/racing/wp/{venue_ymd}/{venue_code}"
    total_updated = 0
    for rn in race_nums:
        cp = find_current_for(venue_ymd, venue_code, rn)
        if not cp:
            log(f"  [SKIP R{rn}] 冇 CURRENT JSON")
            summary["errors"].append(f"R{rn}: no CURRENT JSON")
            continue
        url = f"{base}/{rn}"
        try:
            cdp_navigate(ws_url, url, sleep_sec=args.sleep)
            payload = cdp_evaluate(DEBUG_PORT, ws_url, EVALUATE_SCRIPT)
        except Exception as e:
            log(f"  [FAIL R{rn}] navigate/evaluate: {e}")
            summary["errors"].append(f"R{rn}: evaluate {e}")
            continue
        if not payload:
            summary["errors"].append(f"R{rn}: null payload")
            continue
        odds_map = {}
        for h in (payload.get("horses") or []):
            odds_map[int(h["number"])] = {
                "odds_win": float(h.get("odds_win") or "nan"),
                "odds_place": float(h.get("odds_place") or "nan"),
            }
        ok_write = apply_odds_to_current(cp, odds_map)
        rn_summary = OrderedDict([
            ("race", rn), ("horses_parsed", len(odds_map)),
            ("update_time", payload.get("updateTime")),
            ("ok", ok_write), ("file", os.path.basename(cp)),
        ])
        summary["races"].append(rn_summary)
        log(f"  [OK R{rn}] parsed={len(odds_map)}匹 updated file={os.path.basename(cp)}")
        if ok_write:
            total_updated += 1
    summary["updated_files"] = total_updated
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
