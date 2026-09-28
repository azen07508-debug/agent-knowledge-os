#!/usr/bin/env python3
"""EverOS 到 Obsidian 的同步占位脚本。"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    # 直接运行 scripts/ 下的脚本时，需要显式加入项目根目录。
    sys.path.insert(0, str(PROJECT_ROOT))

from runtime.obsidian_exporter import ObsidianExporter


def main() -> int:
    exporter = ObsidianExporter(PROJECT_ROOT / "obsidian_vault")
    content = "\n".join(
        [
            "## 当前状态",
            "这是同步占位脚本生成的说明笔记。",
            "## 后续计划",
            "- 从 EverOS 查询相关记忆。",
            "- 提炼长期有效知识点。",
            "- 写入 Obsidian 对应目录。",
            "## 安全边界",
            "- 不同步 API Key、Token、Cookie、密码、私钥或助记词。",
            "- 默认只连接本机 EverOS 服务。",
        ]
    )
    path = exporter.write_note("05-Agents", "EverOS同步说明", content, "sync-note", ["everos", "obsidian"])
    print(f"同步说明笔记已生成：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
