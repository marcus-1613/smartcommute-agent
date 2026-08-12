#!/usr/bin/env bash
# SmartCommute AI 一键本地启动脚本（macOS / Linux / Git Bash on Windows）
# 用法：bash scripts/dev.sh [后端端口] [前端端口]
set -euo pipefail

BACKEND_PORT="${1:-8000}"
FRONTEND_PORT="${2:-5173}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# 定位 Python 虚拟环境
if [ -f ".venv/Scripts/python.exe" ]; then
  PY=".venv/Scripts/python.exe"          # Windows
elif [ -f ".venv/bin/python" ]; then
  PY=".venv/bin/python"                  # macOS / Linux
else
  echo "[错误] 未找到 .venv，请先创建虚拟环境并安装依赖："
  echo "       python -m venv .venv && .venv/bin/pip install -r backend/requirements.txt"
  exit 1
fi

echo "==> SmartCommute AI 启动中..."
echo "    后端: http://localhost:${BACKEND_PORT}"
echo "    前端: http://localhost:${FRONTEND_PORT}"

# 后台启动后端（Windows 下不使用 --reload，避免请求竞态导致旧代码处理请求）
echo "==> 启动后端 (uvicorn, port ${BACKEND_PORT})..."
PYTHONUTF8=1 "$PY" -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "$BACKEND_PORT" \
  --app-dir backend &
BACKEND_PID=$!

# 清理钩子：退出时关闭后端
cleanup() {
  echo ""
  echo "==> 正在停止后端 (PID ${BACKEND_PID})..."
  kill "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# 等待后端就绪
echo "==> 等待后端就绪..."
for _ in $(seq 1 30); do
  if curl -s "http://localhost:${BACKEND_PORT}/api/health" >/dev/null 2>&1; then
    echo "==> 后端已就绪"
    break
  fi
  sleep 1
done

# 启动前端（前台，Ctrl+C 一并退出）
echo "==> 启动前端 (vite, port ${FRONTEND_PORT})..."
cd frontend
if [ ! -d node_modules ]; then
  echo "[提示] 首次运行，正在安装前端依赖..."
  npm install
fi
VITE_PORT="$FRONTEND_PORT" npm run dev

wait "$BACKEND_PID"
