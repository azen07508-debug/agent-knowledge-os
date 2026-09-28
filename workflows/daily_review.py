"""每日复盘工作流。"""

from __future__ import annotations

from pathlib import Path

from runtime.obsidian_exporter import ObsidianExporter


def write_daily_review(vault_path: str | Path = "obsidian_vault") -> Path:
    """生成一篇每日复盘模板。"""
    content = "\n".join(
        [
            "## 今天做了什么",
            "- 待补充",
            "## 学到了什么",
            "- 待补充",
            "## 遇到什么错误",
            "- 待补充",
            "## 哪些内容值得沉淀",
            "- 待补充",
            "## 明天第一步做什么",
            "- 待补充",
        ]
    )
    return ObsidianExporter(vault_path).write_daily_review(content)
