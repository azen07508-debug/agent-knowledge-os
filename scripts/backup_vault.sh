#!/usr/bin/env bash
set -u

mkdir -p backup
STAMP="$(date '+%Y%m%d_%H%M%S')"
TARGET="backup/obsidian_vault_${STAMP}.tar.gz"

if [ ! -d "obsidian_vault" ]; then
  echo "未找到 obsidian_vault 目录，无法备份。"
  exit 1
fi

tar -czf "$TARGET" obsidian_vault
echo "Obsidian vault 备份已生成：$TARGET"
