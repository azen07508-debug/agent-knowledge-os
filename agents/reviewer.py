"""Reviewer Agent。"""

from __future__ import annotations

from typing import Any

from agents.base_agent import BaseAgent
from runtime.llm_mock import mock_llm_call


class ReviewerAgent(BaseAgent):
    """负责检查潜在 bug、安全风险和架构问题。"""

    def __init__(self) -> None:
        super().__init__("Reviewer Agent", "结果审查", 2500)

    def run(self, task: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        details = "\n".join(
            [
                "## 潜在 bug",
                "- 依赖未安装时需要 fallback 或友好提示",
                "- 文件名必须清理非法字符",
                "## 安全风险",
                "- 不写入 API Key、私钥、助记词或密码",
                "- EverOS 默认只绑定 127.0.0.1",
                "## 架构问题",
                "- mock 与真实实现要保持接口一致，方便后续替换",
                "## 是否可运行",
                "当前 demo 不需要真实 API Key，应该可以本地运行。",
                "## 改进建议",
                "- 后续接入真实 LLM 前增加配置审计",
                "- 对 EverOS 写入增加重试和脱敏检查",
            ]
        )
        return self.build_result(
            task=task,
            summary=mock_llm_call(f"风险审查：{task}"),
            details=details,
            knowledge_points=["安全审查", "依赖降级", "运行验证"],
            errors=["EverOS 或 arbiter-lite 未安装时需要明确提示"],
            next_actions=["运行 arbiter-doctor", "备份 Obsidian vault", "补充真实集成测试"],
        )
