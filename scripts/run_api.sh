#!/usr/bin/env bash
# 启动 MingLi Agent 的 API 与 Web 控制台（http://HOST:PORT/）。
# 需要已激活虚拟环境；未设置 MINGLI_API_KEY 时为本地开放模式。
set -euo pipefail

cd "$(dirname "$0")/.."

HOST="${MINGLI_HOST:-127.0.0.1}"
PORT="${MINGLI_PORT:-8000}"
# 用户记忆是单进程 JSON 文件，多 worker 会互相覆盖写入，所以默认只起一个进程。
WORKERS="${MINGLI_WORKERS:-1}"

exec python -m uvicorn api.server:app --host "$HOST" --port "$PORT" --workers "$WORKERS"
