"""Coder Agent。"""

from __future__ import annotations

from typing import Any

from agents.base_agent import BaseAgent
from runtime.llm_mock import mock_llm_call


class CoderAgent(BaseAgent):
    """负责生成代码实现建议和运行命令。"""

    def __init__(self) -> None:
        super().__init__("Coder Agent", "代码实现", 3500)

    def run(self, task: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        details = "\n".join(
            [
                "## 需要创建或修改的文件",
                "- agents/：实现四个 Agent",
                "- runtime/：实现预算、记忆和导出器",
                "- workflows/：实现常见知识库工作流",
                "- tests/：固定核心行为",
                "## 核心代码说明",
                "使用统一 AgentResult 结构返回结果，ObsidianExporter 负责写入带 YAML frontmatter 的 Markdown。",
                "## 运行命令",
                "- python -m runtime.main",
                "## 测试命令",
                "- pytest",
            ]
        )
        return self.build_result(
            task=task,
            summary=mock_llm_call(f"实现：{task}"),
            details=details,
            knowledge_points=["结构化输出", "Markdown 导出", "本地 mock"],
            errors=[],
            next_actions=["运行 demo", "运行 pytest", "根据审查结果修复"],
        )
