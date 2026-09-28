"""统一任务数据模型。

优先使用 pydantic；如果本机还没安装依赖，使用轻量 fallback，保证 demo 和测试仍可运行。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

try:
    from pydantic import BaseModel, Field

    class AgentResult(BaseModel):
        agent: str
        task: str
        summary: str
        details: str
        knowledge_points: list[str] = Field(default_factory=list)
        errors: list[str] = Field(default_factory=list)
        next_actions: list[str] = Field(default_factory=list)

    class TaskPlan(BaseModel):
        goal: str
        phases: list[str] = Field(default_factory=list)
        agents: list[str] = Field(default_factory=list)
        deliverables: list[str] = Field(default_factory=list)
        risks: list[str] = Field(default_factory=list)

    class KnowledgeNote(BaseModel):
        title: str
        content: str
        tags: list[str] = Field(default_factory=list)
        note_type: str = "knowledge"

    class ErrorNote(BaseModel):
        title: str
        error_text: str
        solution: str
        tags: list[str] = Field(default_factory=list)

except Exception:

    @dataclass
    class _FallbackModel:
        """最小兼容层，只提供测试和 demo 需要的 model_dump。"""

        def model_dump(self) -> dict[str, Any]:
            return dict(self.__dict__)

    @dataclass
    class AgentResult(_FallbackModel):
        agent: str
        task: str
        summary: str
        details: str
        knowledge_points: list[str] = field(default_factory=list)
        errors: list[str] = field(default_factory=list)
        next_actions: list[str] = field(default_factory=list)

    @dataclass
    class TaskPlan(_FallbackModel):
        goal: str
        phases: list[str] = field(default_factory=list)
        agents: list[str] = field(default_factory=list)
        deliverables: list[str] = field(default_factory=list)
        risks: list[str] = field(default_factory=list)

    @dataclass
    class KnowledgeNote(_FallbackModel):
        title: str
        content: str
        tags: list[str] = field(default_factory=list)
        note_type: str = "knowledge"

    @dataclass
    class ErrorNote(_FallbackModel):
        title: str
        error_text: str
        solution: str
        tags: list[str] = field(default_factory=list)
