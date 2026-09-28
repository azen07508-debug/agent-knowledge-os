"""Researcher Agent。"""

from __future__ import annotations

from typing import Any

from agents.base_agent import BaseAgent
from runtime.llm_mock import mock_llm_call


class ResearcherAgent(BaseAgent):
    """负责 mock 技术调研、仓库分析和知识点提炼。"""

    def __init__(self) -> None:
        super().__init__("Researcher Agent", "资料分析", 2500)

    def run(self, task: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        details = "\n".join(
            [
                "## 一句话总结",
                "EverOS、Arbiter、Obsidian 和 Codex 可以组成本地优先的 Agent 知识闭环。",
                "## 核心功能",
                "- EverOS 保存长期记忆线索",
                "- Arbiter 记录预算和运行风险",
                "- Obsidian 保存人类可读 Markdown",
                "- Codex 负责本地开发和验证",
                "## 可结合方式",
                "先用 mock 流程打通，再逐步替换真实 EverOS 与 LLM。",
                "## 学习价值",
                "学习 Agent 编排、知识库结构化和本地安全边界。",
                "## Obsidian 知识点",
                "- 长期记忆系统",
                "- 本地 Agent 工作流",
                "- 预算守卫",
            ]
        )
        return self.build_result(
            task=task,
            summary=mock_llm_call(f"研究：{task}"),
            details=details,
            knowledge_points=["EverOS", "Arbiter", "Obsidian", "Codex 工作流"],
            errors=[],
            next_actions=["把研究结果写入概念卡", "继续生成实现建议"],
        )
