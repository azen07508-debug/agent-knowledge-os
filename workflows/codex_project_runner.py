"""Codex 项目执行记录工作流。"""

from __future__ import annotations

from pathlib import Path

from agents import CoderAgent, PlannerAgent, ReviewerAgent
from runtime.obsidian_exporter import ObsidianExporter


def run_codex_project_task(task: str, vault_path: str | Path = "obsidian_vault") -> Path:
    """调用 Planner、Coder、Reviewer 的 mock 流程并写入项目执行记录。"""
    results = [
        PlannerAgent().run(task, {}),
        CoderAgent().run(task, {}),
        ReviewerAgent().run(task, {}),
    ]
    content = "\n\n".join(
        f"## {result['agent']}\n\n{result['summary']}\n\n{result['details']}" for result in results
    )
    return ObsidianExporter(vault_path).write_project_note("Codex-Tasks", "项目执行记录", content)
