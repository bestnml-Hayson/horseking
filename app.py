#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
香港賽馬 AI 分析系統 - HTTP 後端伺服器
功能：
  1. 靜態文件伺服（前端頁面）
  2. REST API 提供賽事數據、AI 分析結果
  3. 後台定時線程自動刷新數據（模擬爬蟲 + AI 重算）
運行：python app.py   # 瀏覽 http://localhost:8080
"""
import json
import os
import sys
import random
import threading
import time
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, 'public')
DATA_DIR = os.path.join(BASE_DIR, 'data')
RACE_FILE = os.path.join(DATA_DIR, 'race_data.json')
ANALYSIS_FILE = os.path.join(DATA_DIR, 'latest_analysis.json')
AUTO_REFRESH_INTERVAL = 300  # 5 分鐘自動刷新

sys.path.insert(0, os.path.join(BASE_DIR, 'scripts'))
try:
    from ai_engine import run_analysis, simulate_update
    HAS_AI = True
except Exception as e:
    HAS_AI = False
    print(f"[WARN] AI 模組載入失敗: {e}，將以數據直出模式運行")


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
                return self._send_json(load_json(RACE_FILE))
            if path == '/api/analysis':
                if not os.path.exists(ANALYSIS_FILE):
                    if HAS_AI:
                        run_analysis()
                    else:
                        return self._send_json({'error': '分析文件不存在', 'fallback': True})
                return self._send_json(load_json(ANALYSIS_FILE))
            if path == '/api/dashboard':
                race = load_json(RACE_FILE)
                analysis = load_json(ANALYSIS_FILE) if os.path.exists(ANALYSIS_FILE) else {}
                return self._send_json({'race': race, 'analysis': analysis})
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
                return self._send_json({
                    'server_ok': True,
                    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'ai_available': HAS_AI,
                    'auto_refresh_seconds': AUTO_REFRESH_INTERVAL,
                    'data_file_exists': os.path.exists(RACE_FILE),
                    'analysis_file_exists': os.path.exists(ANALYSIS_FILE),
                    'public_dir': PUBLIC_DIR
                })
            return self._send_error(404, f'未知 API: {path}')
        except Exception as e:
            return self._send_error(500, f'Server Error: {e}')


def main():
    port = int(os.environ.get('PORT', 8080))
    ensure_analysis()
    try:
        t = threading.Thread(target=auto_refresh_worker, daemon=True)
        t.start()
    except Exception as e:
        print(f"[WARN] 自動更新線程啟動失敗: {e}")
    server = HTTPServer(('0.0.0.0', port), RacingHTTPRequestHandler)
    print("=" * 60)
    print("  🐎 香港賽馬 AI 自動分析系統")
    print("=" * 60)
    print(f"  ✅ 後端服務運行中 →  http://localhost:{port}")
    print(f"  📊 賽事數據 API  →  http://localhost:{port}/api/race")
    print(f"  🤖 AI 分析 API   →  http://localhost:{port}/api/analysis")
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
