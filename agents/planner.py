"""Planner Agent。"""

from __future__ import annotations

from typing import Any

from agents.base_agent import BaseAgent
from runtime.llm_mock import mock_llm_call


class PlannerAgent(BaseAgent):
    """负责把用户任务拆成阶段、文件计划和风险清单。"""

    def __init__(self) -> None:
        super().__init__("Planner Agent", "任务规划", 3000)

    def run(self, task: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        phases = [
            "确认目标和安全边界",
            "拆分 Agent 执行顺序",
            "规划 Obsidian 笔记输出",
            "安排测试和复盘",
        ]
        file_plan = [
            "runtime/：运行时连接 EverOS、Arbiter、Obsidian",
            "agents/：Planner、Researcher、Coder、Reviewer",
            "workflows/：可复用任务流",
            "obsidian_vault/：人类可读知识库",
        ]
        risks = [
            "EverOS 未启动时必须友好降级",
            "不得把 API Key 或钱包敏感信息写入 Markdown",
            "真实外部 API 接入前必须再次审查",
        ]
        details = "\n".join(
            [
                "## 项目目标",
                task,
                "## 阶段计划",
                *[f"- {item}" for item in phases],
                "## 文件创建计划",
                *[f"- {item}" for item in file_plan],
                "## 风险点",
                *[f"- {item}" for item in risks],
                "## 下一步命令",
                "- python -m runtime.main",
                "- pytest",
            ]
        )
        return self.build_result(
            task=task,
            summary=mock_llm_call(f"规划：{task}"),
            details=details,
            knowledge_points=["任务分解", "预算检查", "知识沉淀"],
            errors=[],
            next_actions=["运行 Researcher Agent", "运行 Coder Agent", "运行 Reviewer Agent"],
        )
