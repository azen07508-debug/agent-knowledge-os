#!/usr/bin/env bash
set -u

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$PROJECT_ROOT/data/review-server.pid"

if [ ! -f "$PID_FILE" ]; then
  echo "Review API 未由本项目启动。"
  exit 0
fi
pid="$(cat "$PID_FILE" 2>/dev/null || true)"
if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
  rm -f "$PID_FILE"
  echo "Review API 已停止。"
  exit 0
fi
kill "$pid"
rm -f "$PID_FILE"
echo "Review API 已停止：$pid"
