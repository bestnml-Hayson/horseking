#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
香港賽馬 AI 分析系統 - HTTP 後端伺服器 (Supabase v2)
功能：
  1. 靜態文件伺服（前端頁面）
  2. REST API 提供賽事數據、Bill Benter 量化分析（MNL 25/75 + 1/4 凱利）
  3. 優先從 Supabase 讀取 race_data；失敗時 fallback 本地 JSON
  4. 缺失數據中性化：odds_win / best_time_sec 取同場次中位數
運行：python app.py   # 瀏覽 http://localhost:8080
"""
import json
import os
import sys
import random
import threading
import time
import math
import statistics
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, 'public')
DATA_DIR = os.path.join(BASE_DIR, 'data')
RACE_FILE = os.path.join(DATA_DIR, 'race_data.json')
ANALYSIS_FILE = os.path.join(DATA_DIR, 'latest_analysis.json')
AUTO_REFRESH_INTERVAL = 300  # 5 分鐘自動刷新

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "").strip()

sys.path.insert(0, os.path.join(BASE_DIR, 'scripts'))
try:
    from ai_engine import run_analysis, simulate_update, bill_benter_quant
    HAS_AI = True
except Exception as e:
    try:
        from ai_engine import run_analysis, simulate_update
        bill_benter_quant = None
        HAS_AI = True
    except Exception as e2:
        bill_benter_quant = None
        HAS_AI = False
        print(f"[WARN] AI 模組載入失敗: {e}，將以數據直出模式運行")


_SB_CLIENT = None
_SB_INIT_ERR = None


def get_supabase_client():
    """延遲初始化 Supabase Client（匿名 key 唯讀）"""
    global _SB_CLIENT, _SB_INIT_ERR
    if _SB_CLIENT is not None:
        return _SB_CLIENT, None
    if _SB_INIT_ERR is not None:
        return None, _SB_INIT_ERR
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        _SB_INIT_ERR = "SUPABASE_URL / SUPABASE_ANON_KEY 未設定"
        return None, _SB_INIT_ERR
    try:
        from supabase import create_client
        _SB_CLIENT = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        return _SB_CLIENT, None
    except Exception as e:
        _SB_INIT_ERR = f"Supabase init fail: {e}"
        return None, _SB_INIT_ERR


def ensure_analysis():
    if not os.path.exists(ANALYSIS_FILE) and HAS_AI:
        try:
            run_analysis()
        except Exception as e:
            print(f"[ERROR] 首次分析失敗: {e}")


def load_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        return {'error': str(e)}


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# =====================================================================
# Supabase 資料讀取 & 缺失值中性化
# =====================================================================
def _is_valid_odds(o):
    if o is None:
        return False
    try:
        v = float(o)
    except Exception:
        return False
    return 1.0 < v < 900  # 排除 0 / 999 等 placeholder


def _is_valid_time(t):
    if t is None:
        return False
    try:
        v = float(t)
    except Exception:
        return False
    return 0 < v < 900  # 排除 0 / 999


def _safe_median(values):
    if not values:
        return 0.0
    try:
        return float(statistics.median(values))
    except Exception:
        return sum(values) / len(values)


def _row_to_horse(row):
    """Supabase race_data row → 前端 horses[i] dict"""
    hn = int(row.get("horse_no") or 0)
    odds_win_raw = float(row.get("odds_win") or 0)
    odds_place_raw = float(row.get("odds_place") or 0)
    bt_raw = float(row.get("best_time_sec") or 0)
    sr_raw = float(row.get("speed_rating") or 0)
    last3_raw = row.get("last_3") or []
    if isinstance(last3_raw, str):
        try:
            last3_raw = json.loads(last3_raw)
        except Exception:
            last3_raw = []
    last3 = [int(x) for x in (last3_raw or [])][:3]
    scores_total = sr_raw if sr_raw > 0 else 0
    horse = {
        "number": hn,
        "code": str(row.get("horse_code") or f"UNK{hn}"),
        "name": str(row.get("horse_name") or f"#{hn}"),
        "draw": int(row.get("draw") or 0),
        "rating": int(row.get("rating") or 0),
        "weight": float(row.get("weight") or 0),
        "jockey": str(row.get("jockey") or ""),
        "trainer": str(row.get("trainer") or ""),
        "gear": str(row.get("gear") or ""),
        "last_6": str(row.get("last_6") or ""),
        "best_time_sec": bt_raw,
        "odds_win": odds_win_raw,
        "odds_place": odds_place_raw,
        "last_3": last3,
        "scores": {
            "total": round(scores_total, 2)
        } if scores_total > 0 else {"total": 0}
    }
    return horse


def neutralize_missing_values(horses):
    """
    缺失數據中性化（依 Project Memory 硬性約束）：
      - odds_win 為 0 或 999 → 取同場其他有效 odds_win 中位數
      - best_time_sec 為 0 或 999 → 取同場中位數
    """
    if not horses:
        return horses
    valid_odds = [float(h["odds_win"]) for h in horses if _is_valid_odds(h.get("odds_win"))]
    valid_bt = [float(h["best_time_sec"]) for h in horses if _is_valid_time(h.get("best_time_sec"))]
    med_odds = _safe_median(valid_odds)
    med_bt = _safe_median(valid_bt)
    for h in horses:
        if not _is_valid_odds(h.get("odds_win")):
            h["odds_win"] = round(med_odds, 2) if med_odds > 0 else 10.0
        if not _is_valid_time(h.get("best_time_sec")):
            h["best_time_sec"] = round(med_bt, 2) if med_bt > 0 else 60.0
    return horses


def fetch_race_from_supabase(race_date=None, race_no=None, venue=None, next_race=True):
    """
    從 Supabase 查詢賽事；回傳 {race_info, horses, meta} 或 None
    預設找「下一場未開賽」：最近日期 → 最小 race_no
    """
    client, err = get_supabase_client()
    if client is None:
        return None, err
    try:
        q = client.table("race_data").select("*")
        if race_date:
            q = q.eq("race_date", str(race_date))
        if race_no:
            q = q.eq("race_no", int(race_no))
        if venue:
            q = q.eq("venue", str(venue).upper())
        if next_race and not race_date:
            q = q.gte("race_date", datetime.now().strftime("%Y-%m-%d"))
        q = q.order("race_date", desc=False).order("race_no", desc=False).order("horse_no", desc=True)
        q = q.limit(500)
        res = q.execute()
        rows = res.data or []
        if not rows:
            return None, "Supabase 尚無符合條件之 race_data"
        # 取第一場賽事 (date + no + venue 最小組合)
        first = rows[0]
        key = (first["race_date"], first["race_no"], first["venue"])
        chosen = [r for r in rows if (r["race_date"], r["race_no"], r["venue"]) == key]
        horses = [_row_to_horse(r) for r in chosen]
        horses.sort(key=lambda h: h["number"])
        neutralize_missing_values(horses)
        race_info = {
            "race_id": f"{key[2]}-{str(key[0]).replace('-','')}-{key[1]:02d}",
            "race_date": str(key[0]),
            "race_number": int(key[1]),
            "venue": "沙田" if str(key[2]).upper() == "ST" else "跑馬地",
            "venue_code": str(key[2]).upper(),
            "num_horses": len(horses)
        }
        meta = {
            "source": "supabase",
            "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "supabase_updated_at": str(first.get("updated_at") or "")
        }
        return {"race_info": race_info, "horses": horses, "meta": meta}, None
    except Exception as e:
        return None, f"Supabase query fail: {e}"


def compute_scores_if_missing(horses):
    """
    如果 Supabase speed_rating 為 0（亦即 AI 評分未預先計算），
    在本地用 6 維度模型補算 scores.total，令 Softmax 有意義。
    """
    if not horses:
        return horses
    scored_total = sum(1 for h in horses if h.get("scores", {}).get("total", 0) > 0)
    if scored_total >= max(1, len(horses) // 2):
        return horses
    try:
        last3_scores = []
        ratings = []
        best_times = []
        draws = []
        weights = []
        odds_list = []
        for h in horses:
            def ana(lst):
                if not lst:
                    return 0
                ws = [0.5, 0.3, 0.2]
                s = 0
                for i in range(min(len(lst), 3)):
                    r = lst[i]
                    s += max(0, 100 - (r - 1) * 8) * ws[i]
                return round(s, 2)
            last3_scores.append(ana(h.get("last_3", [])))
            ratings.append(h.get("rating", 0))
            best_times.append(h.get("best_time_sec", 999))
            draws.append(h.get("draw", 100))
            weights.append(h.get("weight", 0))
            odds_list.append(h.get("odds_win", 999))
        def mm(vs, rev=False):
            if not vs: return {}
            mn, mx = min(vs), max(vs)
            if mn == mx: return {v: 100.0 for v in vs}
            if rev: return {v: round(100 * (1 - (v - mn) / (mx - mn)), 2) for v in vs}
            return {v: round(100 * (v - mn) / (mx - mn), 2) for v in vs}
        r_map = mm(ratings)
        t_map = mm(best_times, True)
        d_map = mm(draws, True)
        w_map = mm(weights)
        inv_odds = [100 / o if o > 0 else 0 for o in odds_list]
        o_map = mm(inv_odds)
        for idx, h in enumerate(horses):
            s_l3 = last3_scores[idx]
            s_r = r_map.get(h["rating"], 0)
            s_t = t_map.get(h["best_time_sec"], 0)
            s_d = d_map.get(h["draw"], 0)
            s_w = w_map.get(h["weight"], 0)
            inv = 100 / h["odds_win"] if h["odds_win"] > 0 else 0
            s_o = o_map.get(inv, 0)
            total = round(s_l3 * 0.30 + s_r * 0.20 + s_t * 0.15 + s_d * 0.15 + s_w * 0.10 + s_o * 0.10, 2)
            h["scores"] = {"last3": s_l3, "rating": s_r, "time": s_t, "draw": s_d, "weight": s_w, "odds": s_o, "total": total}
    except Exception as e:
        print(f"[WARN] compute_scores_if_missing 失敗: {e}")
    return horses


def load_race_unified():
    """
    統一載入入口：
      1) 優先嘗試 Supabase（下一場賽事）
      2) 失敗則 fallback 本地 RACE_FILE JSON
    回傳格式與 load_json(RACE_FILE) 相同 dict，並已 neutralize + compute_scores
    """
    data, err = fetch_race_from_supabase(next_race=True)
    if data is None:
        if err:
            print(f"[INFO] Supabase 未使用: {err}")
        race = load_json(RACE_FILE)
        if isinstance(race, dict) and isinstance(race.get("horses"), list):
            race["horses"] = neutralize_missing_values(list(race["horses"]))
            race["horses"] = compute_scores_if_missing(race["horses"])
        return race
    return data


def refresh_data_simulation():
    """模擬自動更新：輕微擾動賠率 + 重跑 AI"""
    data = load_json(RACE_FILE)
    if 'error' in data:
        return {'error': data['error']}
    now = datetime.now()
    data.setdefault('meta', {})
    data['meta']['update_time'] = now.strftime('%Y-%m-%d %H:%M:%S')
    data['meta']['source'] = 'auto_refresh_simulated'
    for h in data.get('horses', []):
        delta = random.choice([-0.4, -0.2, 0.0, 0.2, 0.4])
        new_odds = max(1.1, round(h.get('odds_win', 10) + delta, 1))
        h['odds_win'] = new_odds
    save_json(RACE_FILE, data)
    if HAS_AI:
        try:
            run_analysis()
        except Exception as e:
            print(f"[ERROR] refresh analysis failed: {e}")
    return {
        'updated_at': data['meta']['update_time'],
        'horses_refreshed': len(data.get('horses', [])),
        'analysis_regenerated': HAS_AI
    }


def auto_refresh_worker():
    """後台定時自動更新線程"""
    print(f"[AUTO] 自動更新線程啟動，每 {AUTO_REFRESH_INTERVAL} 秒刷新一次")
    while True:
        try:
            result = refresh_data_simulation()
            print(f"[AUTO] 數據已自動刷新 @ {result.get('updated_at')}")
        except Exception as e:
            print(f"[AUTO] 刷新異常: {e}")
        time.sleep(AUTO_REFRESH_INTERVAL)


class RacingHTTPRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PUBLIC_DIR, **kwargs)

    def log_message(self, fmt, *args):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {fmt % args}")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/')

        if path == '/':
            self.path = '/index.html'
            return super().do_GET()

        if path.startswith('/api/'):
            return self._handle_api(path, parsed)

        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/')
        if path.startswith('/api/'):
            return self._handle_api(path, parsed, method='POST')
        self._send_error(404, 'Not Found')

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, code, msg):
        self._send_json({'error': msg, 'code': code}, status=code)

    def _handle_api(self, path, parsed, method='GET'):
        try:
            if path == '/api/race':
                race = load_race_unified()
                if isinstance(race, dict) and isinstance(race.get('horses'), list) and callable(bill_benter_quant):
                    try:
                        race = dict(race)
                        race['horses'] = bill_benter_quant(list(race.get('horses', [])), total_bankroll=100000)
                        race['horses'] = sorted(race['horses'], key=lambda h: float(h.get('ev') or 0), reverse=True)
                    except Exception as e:
                        print(f"[WARN] /api/race bill_benter failed: {e}")
                race.setdefault('meta', {})
                race['meta']['engine'] = 'bill_benter_25_75_kelly_1_4'
                return self._send_json(race)
            if path == '/api/predict':
                if method == 'POST':
                    length = int(self.headers.get('Content-Length') or 0)
                    body = self.rfile.read(length) if length > 0 else b'{}'
                    payload = {}
                    try:
                        payload = json.loads(body.decode('utf-8') or '{}')
                    except Exception:
                        payload = {}
                else:
                    raw = parse_qs(parsed.query)
                    horses_raw = (raw.get('horses') or [None])[0]
                    payload = {}
                    if isinstance(horses_raw, str) and horses_raw:
                        try:
                            payload = json.loads(horses_raw)
                        except Exception:
                            payload = {}
                horses = None
                if isinstance(payload, list):
                    horses = payload
                elif isinstance(payload, dict):
                    if isinstance(payload.get('horses'), list):
                        horses = payload['horses']
                    elif isinstance(payload.get('race'), dict) and isinstance(payload['race'].get('horses'), list):
                        horses = payload['race']['horses']
                if not isinstance(horses, list):
                    race0 = load_race_unified()
                    horses = list(race0.get('horses', [])) if isinstance(race0, dict) else []
                bankroll = 100000
                if isinstance(payload, dict):
                    try:
                        br = payload.get('total_bankroll') or payload.get('bankroll')
                        if isinstance(br, (int, float)) and br > 0:
                            bankroll = int(br)
                    except Exception:
                        pass
                horses = neutralize_missing_values([dict(h) for h in (horses or [])])
                horses = compute_scores_if_missing(horses)
                if callable(bill_benter_quant):
                    out = bill_benter_quant(list(horses), total_bankroll=bankroll)
                else:
                    out = [dict(h) for h in (horses or [])]
                out_sorted = sorted(out, key=lambda h: float(h.get('ev') or 0), reverse=True)
                return self._send_json({
                    'ok': True,
                    'engine': 'bill_benter_25_75_kelly_1_4',
                    'total_bankroll': bankroll,
                    'num_horses': len(out_sorted),
                    'horses': out_sorted
                })
            if path == '/api/analysis':
                if not os.path.exists(ANALYSIS_FILE):
                    if HAS_AI:
                        try:
                            run_analysis()
                        except Exception as e:
                            return self._send_json({'error': f'分析失敗: {e}', 'fallback': True})
                    else:
                        return self._send_json({'error': '分析文件不存在', 'fallback': True})
                return self._send_json(load_json(ANALYSIS_FILE))
            if path == '/api/dashboard':
                race = load_race_unified()
                analysis = load_json(ANALYSIS_FILE) if os.path.exists(ANALYSIS_FILE) else {}
                return self._send_json({'race': race, 'analysis': analysis})
            if path == '/api/supabase/status':
                sb_client, sb_err = get_supabase_client()
                latest_row = None
                rows_count = None
                if sb_client is not None:
                    try:
                        r = sb_client.table("race_data").select("*").order("updated_at", desc=True).limit(1).execute()
                        latest_row = r.data[0] if (r.data and len(r.data) > 0) else None
                    except Exception as e:
                        sb_err = f"{sb_err or ''}; query_fail: {e}"
                    try:
                        rc = sb_client.table("race_data").select("id", count="exact").execute()
                        rows_count = getattr(rc, 'count', None)
                    except Exception:
                        pass
                return self._send_json({
                    'ok': sb_client is not None,
                    'supabase_url_set': bool(SUPABASE_URL),
                    'supabase_anon_key_set': bool(SUPABASE_ANON_KEY),
                    'error': sb_err,
                    'rows_count': rows_count,
                    'latest_row': latest_row
                })
            if path == '/api/refresh':
                result = refresh_data_simulation()
                return self._send_json(result)
            if path == '/api/reanalyze':
                if not HAS_AI:
                    return self._send_json({'ok': False, 'error': 'AI 引擎未載入'})
                analysis = run_analysis()
                return self._send_json({
                    'ok': True,
                    'generated_at': analysis.get('generated_at'),
                    'top4': [
                        {'rank': p['rank'], 'code': p['horse']['code'],
                         'name': p['horse'].get('name', ''),
                         'total_score': p['horse']['scores']['total']}
                        for p in analysis.get('top4_predictions', [])
                    ]
                })
            if path == '/api/status':
                sb_client, sb_err = get_supabase_client()
                return self._send_json({
                    'server_ok': True,
                    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'ai_available': HAS_AI,
                    'auto_refresh_seconds': AUTO_REFRESH_INTERVAL,
                    'data_file_exists': os.path.exists(RACE_FILE),
                    'analysis_file_exists': os.path.exists(ANALYSIS_FILE),
                    'public_dir': PUBLIC_DIR,
                    'supabase': {
                        'available': sb_client is not None,
                        'url_set': bool(SUPABASE_URL),
                        'anon_key_set': bool(SUPABASE_ANON_KEY),
                        'error': sb_err
                    }
                })
            return self._send_error(404, f'未知 API: {path}')
        except Exception as e:
            import traceback
            traceback.print_exc()
            return self._send_error(500, f'Server Error: {e}')


def main():
    port = int(os.environ.get('PORT', 8080))
    ensure_analysis()
    try:
        t = threading.Thread(target=auto_refresh_worker, daemon=True)
        t.start()
    except Exception as e:
        print(f"[WARN] 自動更新線程啟動失敗: {e}")
    sb_client, sb_err = get_supabase_client()
    sb_status = "✅ 已連線" if sb_client is not None else f"⏸ 未使用 ({sb_err})"
    server = HTTPServer(('0.0.0.0', port), RacingHTTPRequestHandler)
    print("=" * 60)
    print("  🐎 香港賽馬 AI 自動分析系統 (Supabase v2)")
    print("=" * 60)
    print(f"  ✅ 後端服務運行中 →  http://localhost:{port}")
    print(f"  📊 賽事數據 API  →  http://localhost:{port}/api/race")
    print(f"  🤖 量化預測 API   →  http://localhost:{port}/api/predict  (Bill Benter 25/75 + 1/4 Kelly)")
    print(f"  🧪 Supabase 狀態   →  {sb_status}")
    print(f"  🧪 Supabase 健檢   →  http://localhost:{port}/api/supabase/status")
    print(f"  📊 系統狀態 API   →  http://localhost:{port}/api/status")
    print(f"  🔄 手動刷新      →  http://localhost:{port}/api/refresh")
    print(f"  ⏰ 自動刷新間隔  →  {AUTO_REFRESH_INTERVAL} 秒 (5 分鐘)")
    print(f"  🧠 AI 引擎       →  {'已載入' if HAS_AI else '未載入(前端 fallback)'}")
    print("=" * 60)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 伺服器已關閉")
        server.server_close()


if __name__ == '__main__':
    main()
