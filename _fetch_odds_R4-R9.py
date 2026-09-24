import subprocess
import time
import json
import os
import sys
import urllib.request
import http.client

LOG_PATH = r"d:\Trae\horse\_fetch_odds_log.txt"
_log_f = open(LOG_PATH, "w", encoding="utf-8")

def log(msg):
    try:
        print(msg, flush=True)
    except Exception:
        pass
    _log_f.write(str(msg) + "\n")
    _log_f.flush()

OUTPUT_PATH = r"d:\Trae\horse\data\references\_odds_HV_20260923_R456789.json"
RACE_NUMS = [4, 5, 6, 7, 8, 9]
BASE_URL = "https://bet.hkjc.com/ch/racing/wp/2026-09-23/HV/{rn}"
WAIT_SECONDS = 7
CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]

USER_DATA_DIR = r"d:\Trae\horse\.cdp_profile3"
DEBUG_PORT = 9225

EVALUATE_SCRIPT = r"""
const txt = document.body.innerText;
const headerIdx = txt.indexOf('馬號\t綵衣\t馬名\t檔位\t負磅\t騎師\t練馬師\t獨贏\t位置');
const afterHeader = txt.substring(headerIdx);
const lines = afterHeader.split(/\n/);
const horses = [];
let i = 1;
while (i < lines.length) {
    const cols = lines[i].split('\t');
    const c0 = cols[0]?.trim() || '';
    if (/^\d{1,2}$/.test(c0)) {
        const horseNo = parseInt(c0);
        i++;
        while (i < lines.length && lines[i].trim() === '') i++;
        if (i >= lines.length) break;
        const infoCols = lines[i].split('\t').map(c=>c.trim());
        let name = '', draw = null, weight = null, jockey = '', trainer = '';
        let colIdx = 0;
        while (colIdx < infoCols.length && infoCols[colIdx] === '') colIdx++;
        if (colIdx < infoCols.length) name = infoCols[colIdx++];
        if (colIdx < infoCols.length) draw = infoCols[colIdx++];
        if (colIdx < infoCols.length) weight = infoCols[colIdx++];
        if (colIdx < infoCols.length) jockey = infoCols[colIdx++];
        if (colIdx < infoCols.length) trainer = infoCols[colIdx++];
        i++;
        while (i < lines.length && lines[i].trim() === '') i++;
        let oddsWin = NaN, oddsPlace = NaN;
        if (i < lines.length) {
            const wCols = lines[i].split('\t');
            if (/^\d{1,3}(\.\d)?$/.test(wCols[0]?.trim())) oddsWin = parseFloat(wCols[0]);
            i++;
        }
        while (i < lines.length && lines[i].trim() === '') i++;
        if (i < lines.length) {
            const pCols = lines[i].split('\t');
            if (/^\d{1,3}(\.\d)?$/.test(pCols[0]?.trim())) oddsPlace = parseFloat(pCols[0]);
            i++;
        }
        if (name && horseNo>=1 && horseNo<=20) horses.push({number: horseNo, name, draw, weight, jockey, trainer, odds_win: oddsWin, odds_place: oddsPlace});
    } else if (c0.includes('全餐') || lines[i].includes('總投注額')) {
        break;
    } else {
        i++;
    }
}
const rnm = txt.match(/第\s*(\d+)\s*場/);
const ut = txt.match(/更新時間:\s*([\d\s\/:]+?)\s*\n/);
JSON.stringify({url: location.href, raceNumber: rnm ? parseInt(rnm[1]) : null, updateTime: ut ? ut[1].trim() : null, horseCount: horses.length, horses});
"""


def find_chrome():
    for p in CHROME_PATHS:
        if os.path.isfile(p):
            return p
    return None


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def cdp_http(port, method, params=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    payload = {"id": 1, "method": method}
    if params:
        payload["params"] = params
    body = json.dumps(payload).encode("utf-8")
    conn.request("POST", "/json/protocol", body, {"Content-Type": "application/json"})
    return None


def main():
    try:
        import websocket
    except Exception:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client", "-q"])
        except Exception as ex:
            log(f"pip install websocket-client failed: {ex}")
        try:
            import websocket
        except Exception as ex:
            log(f"FATAL websocket import: {ex}")
            sys.exit(3)

    chrome = find_chrome()
    if not chrome:
        log("ERROR: Chrome/Edge not found")
        sys.exit(1)
    log(f"Using browser: {chrome}")

    try:
        os.makedirs(USER_DATA_DIR, exist_ok=True)
    except Exception:
        pass

    proc = subprocess.Popen([
        chrome,
        f"--user-data-dir={USER_DATA_DIR}",
        f"--remote-debugging-port={DEBUG_PORT}",
        "--remote-allow-origins=*",
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--hide-scrollbars",
        "--mute-audio",
        "--disable-features=VizDisplayCompositor",
        "--disable-software-rasterizer",
        "about:blank",
    ])

    try:
        ws_url = None
        for _ in range(60):
            try:
                v = json.loads(http_get(f"http://127.0.0.1:{DEBUG_PORT}/json/version", timeout=2))
                ws_url = v.get("webSocketDebuggerUrl")
                if ws_url:
                    break
            except Exception:
                time.sleep(0.5)
        if not ws_url:
            log("ERROR: Cannot connect to Chrome debugging endpoint")
            sys.exit(2)
        log(f"Connected to CDP (browser): {ws_url}")

        results = []

        for rn in RACE_NUMS:
            url = BASE_URL.format(rn=rn)
            log(f"\n=== Fetching R{rn}: {url} ===")

            targets = json.loads(http_get(f"http://127.0.0.1:{DEBUG_PORT}/json/list", timeout=10))
            page_ws = None
            for t in targets:
                if t.get("type") == "page":
                    page_ws = t.get("webSocketDebuggerUrl")
                    break
            if page_ws is None:
                log(f"  No page target found, creating new...")
                conn = http.client.HTTPConnection("127.0.0.1", DEBUG_PORT, timeout=15)
                payload = json.dumps({"id": 1, "method": "Target.createTarget", "params": {"url": "about:blank"}}).encode("utf-8")
                conn.request("PUT", "/json/new?about:blank", b"", {"Content-Type": "application/json"})
                resp = conn.getresponse()
                resp.read()
                conn.close()
                time.sleep(1)
                targets = json.loads(http_get(f"http://127.0.0.1:{DEBUG_PORT}/json/list", timeout=10))
                for t in targets:
                    if t.get("type") == "page":
                        page_ws = t.get("webSocketDebuggerUrl")
                        break
            if page_ws is None:
                log(f"  Cannot get page target, skip R{rn}")
                results.append({"url": url, "raceNumber": rn, "updateTime": None, "horseCount": 0, "horses": []})
                continue
            log(f"  Using page WS: {page_ws[:80]}...")

            ws = websocket.create_connection(page_ws, timeout=90, suppress_origin=True)
            _next_id = [1]

            def send(method, params=None):
                payload = {"id": _next_id[0], "method": method}
                if params:
                    payload["params"] = params
                this_id = _next_id[0]
                _next_id[0] += 1
                ws.send(json.dumps(payload))
                deadline = time.time() + 30
                while time.time() < deadline:
                    try:
                        raw = ws.recv()
                        msg = json.loads(raw)
                        if msg.get("id") == this_id:
                            return msg
                    except websocket.WebSocketTimeoutException:
                        break
                return {"id": this_id, "error": {"message": "timeout"}}

            try:
                r_enable = send("Page.enable")
                if "error" in r_enable:
                    log(f"  Page.enable error: {r_enable.get('error')}")
                send("Runtime.enable")
                send("Network.enable")
                send("Network.setUserAgentOverride", {
                    "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
                })

                nav_resp = send("Page.navigate", {"url": url})
                frame_id = None
                if "result" in nav_resp:
                    frame_id = nav_resp["result"].get("frameId")
                log(f"  Navigated (frame={frame_id}). Waiting {WAIT_SECONDS}s for SPA render...")
                time.sleep(WAIT_SECONDS)

                txt_resp = send("Runtime.evaluate", {
                    "expression": "document.body ? document.body.innerText.substring(0, 500) : '[no body]'",
                    "returnByValue": True,
                })
                try:
                    snippet = txt_resp["result"]["result"]["value"]
                    log(f"  Body snippet len={len(snippet)}: {repr(snippet[:200])}")
                except Exception as ex:
                    log(f"  Body snippet ERROR: {ex} resp={txt_resp}")

                eval_resp = send("Runtime.evaluate", {
                    "expression": EVALUATE_SCRIPT,
                    "returnByValue": True,
                    "awaitPromise": True,
                })
                log(f"  eval_resp keys: {list(eval_resp.keys())}")
                result_obj = None
                try:
                    raw_value = eval_resp["result"]["result"]["value"]
                    if isinstance(raw_value, str):
                        result_obj = json.loads(raw_value)
                    else:
                        result_obj = raw_value
                    if "horses" in result_obj:
                        result_obj["horseCount"] = len(result_obj.get("horses", []))
                    log(f"  OK raceNumber={result_obj.get('raceNumber')} horseCount={result_obj.get('horseCount')} updateTime={result_obj.get('updateTime')}")
                except Exception as e:
                    log(f"  Parse ERROR: {e}")
                    log(f"  eval_resp dump: {json.dumps(eval_resp, ensure_ascii=False)[:3000]}")
                    result_obj = {"url": url, "raceNumber": rn, "updateTime": None, "horseCount": 0, "horses": []}

                results.append(result_obj)
            finally:
                try:
                    ws.close()
                except Exception:
                    pass

        try:
            os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
        except Exception:
            pass
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        log(f"\nSaved to {OUTPUT_PATH}")

        log("\n================= SUMMARY =================")
        for r in results:
            log(f"R{r.get('raceNumber')}: horseCount={r.get('horseCount')}, updateTime={r.get('updateTime')}")

    finally:
        try:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    main()
