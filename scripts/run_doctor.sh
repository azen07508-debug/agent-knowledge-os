#!/usr/bin/env bash
set -u

REPORT="obsidian_vault/05-Agents/arbiter-doctor-report.md"
mkdir -p "$(dirname "$REPORT")"

if ! command -v arbiter-doctor >/dev/null 2>&1; then
  {
    echo "# Arbiter Doctor 报告"
    echo
    echo "状态：未运行"
    echo
    echo "原因：未找到 arbiter-doctor 命令。"
    echo
    echo "处理方式：请先运行 pip install arbiter-lite。"
  } > "$REPORT"
  echo "未找到 arbiter-doctor。请先运行：pip install arbiter-lite"
  echo "报告已写入：$REPORT"
  exit 0
fi

{
  echo "# Arbiter Doctor 报告"
  echo
  echo "生成时间：$(date '+%Y-%m-%d %H:%M:%S')"
  echo
  echo '```text'
  arbiter-doctor . 2>&1
  echo '```'
} > "$REPORT"

echo "arbiter-doctor 已运行，报告已写入：$REPORT"
