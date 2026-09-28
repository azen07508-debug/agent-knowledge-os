"""Agent 基类。"""

from __future__ import annotations

from typing import Any

from runtime.task_models import AgentResult


class BaseAgent:
    """所有 Agent 的统一基类。"""

    def __init__(self, name: str, role: str, default_budget: int = 2000) -> None:
        self.name = name
        self.role = role
        self.default_budget = default_budget

    def run(self, task: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """子类必须实现具体执行逻辑。"""
        raise NotImplementedError("子类必须实现 run(task, context)。")

    def build_result(
        self,
        task: str,
        summary: str,
        details: str,
        knowledge_points: list[str] | None = None,
        errors: list[str] | None = None,
        next_actions: list[str] | None = None,
    ) -> dict[str, Any]:
        """集中构造结构化结果，避免各 Agent 输出漂移。"""
        result = AgentResult(
            agent=self.name,
            task=task,
            summary=summary,
            details=details,
            knowledge_points=knowledge_points or [],
            errors=errors or [],
            next_actions=next_actions or [],
        )
        if hasattr(result, "model_dump"):
            return result.model_dump()
        return dict(result.__dict__)
