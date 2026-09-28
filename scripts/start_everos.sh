#!/usr/bin/env bash
set -u

if ! command -v everos >/dev/null 2>&1; then
  echo "未找到 everos 命令。请先运行：pip install everos"
  exit 0
fi

echo "准备启动本机 EverOS 服务，默认只建议绑定 127.0.0.1。"
everos server start
