#!/usr/bin/env bash
set -u

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$PROJECT_ROOT/.venv/bin/python"
DATA_DIR="$PROJECT_ROOT/data"
PID_FILE="$DATA_DIR/review-server.pid"
LOG_FILE="$DATA_DIR/review-server.log"
PORT="${CREATOROS_REVIEW_PORT:-8765}"

if [ ! -x "$PYTHON" ]; then
  echo "缺少 Python 虚拟环境：$PYTHON" >&2
  exit 1
fi
mkdir -p "$DATA_DIR"

if [ -f "$PID_FILE" ]; then
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    echo "Review API 已运行：http://127.0.0.1:$PORT"
    echo "Dashboard：$DATA_DIR/dashboard.html"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

"$PYTHON" "$PROJECT_ROOT/scripts/build_dashboard.py" >/dev/null
nohup "$PYTHON" "$PROJECT_ROOT/scripts/review_server.py" --host 127.0.0.1 --port "$PORT" >>"$LOG_FILE" 2>&1 &
pid=$!
echo "$pid" > "$PID_FILE"
sleep 0.3
if ! kill -0 "$pid" 2>/dev/null; then
  rm -f "$PID_FILE"
  echo "Review API 启动失败，查看：$LOG_FILE" >&2
  exit 1
fi
echo "Review API：http://127.0.0.1:$PORT"
echo "Dashboard：$DATA_DIR/dashboard.html"
