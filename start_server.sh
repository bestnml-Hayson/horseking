#!/bin/bash
# ============================================================
#  賽馬 AI 自動分析系統 - macOS / Linux 啟動腳本
#  chmod +x start_server.sh && ./start_server.sh
# ============================================================
cd "$(dirname "$0")"
echo "========================================================"
echo "  🐎 香港賽馬 AI 自動分析系統"
echo "========================================================"

PY=""
if command -v python3 &>/dev/null; then PY="python3"
elif command -v python &>/dev/null; then PY="python"
fi

if [ -z "$PY" ]; then
  echo "[ERROR] 找不到 Python，請先安裝 Python 3.7+"
  exit 1
fi

open "http://localhost:8080" 2>/dev/null || echo "[INFO] 請手動打開 http://localhost:8080"
$PY app.py
