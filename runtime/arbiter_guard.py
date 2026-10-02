"""Arbiter 预算保护层。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


class ArbiterGuard:
    """封装 arbiter-lite；未安装时保持友好提示，不让 demo 崩溃。"""

    def __init__(
        self,
        vault_path: str | Path = "obsidian_vault",
        default_budget: int = 8000,
        agent_names: list[str] | None = None,
    ) -> None:
        self.vault_path = Path(vault_path)
        self.default_budget = default_budget
        self.agent_names = agent_names or ["Planner Agent", "Researcher Agent", "Coder Agent", "Reviewer Agent"]
        self.local_usage: dict[str, int] = {}
        self._manager: Any | None = None
        self._error_message = ""
        try:
            from arbiter_lite import QuotaManager  # type: ignore

            # arbiter-lite 0.1.0 需要总预算和 Agent 名称；给每个默认 Agent 保留 default_budget。
            self._manager = QuotaManager(max_tokens=default_budget * len(self.agent_names), agent_names=self.agent_names)
        except Exception as exc:
            self._error_message = f"arbiter-lite 未安装或不可用，请运行：pip install arbiter-lite。原因：{exc}"

    @property
    def available(self) -> bool:
        return self._manager is not None

    def request_budget(self, agent_name: str, tokens: int) -> dict[str, Any]:
        """申请预算；没有 arbiter-lite 时使用本地轻量预算记录。"""
        manager = self._manager
        if manager is None:  # 等价于 not self.available：没有 arbiter-lite 的本地兜底
            allowed = tokens <= self.default_budget
            result = {"allowed": allowed, "message": self._error_message, "tokens": tokens}
            self.write_budget_log(agent_name, tokens, result)
            return result
        try:
            request = getattr(manager, "request_budget", None)
            if callable(request):
                raw_result = request(agent_name, tokens)
                result = {"allowed": bool(raw_result), "message": "Arbiter 预算申请完成。", "tokens": tokens}
            elif callable(getattr(manager, "request", None)):
                granted = manager.request(agent_name, tokens)
                result = {
                    "allowed": granted >= tokens,
                    "message": f"Arbiter 预算申请完成，批准数量：{granted}。",
                    "tokens": tokens,
                }
            else:
                result = {"allowed": True, "message": "QuotaManager 已加载，但未暴露 request_budget，使用兼容模式。", "tokens": tokens}
        except Exception as exc:
            result = {"allowed": False, "message": f"Arbiter 预算申请失败：{exc}", "tokens": tokens}
        self.local_usage[agent_name] = self.local_usage.get(agent_name, 0) + tokens
        self.write_budget_log(agent_name, tokens, result)
        return result

    def release_budget(self, agent_name: str) -> dict[str, Any]:
        released = self.local_usage.pop(agent_name, 0)
        return {"agent": agent_name, "released_tokens": released, "message": "预算已释放。"}

    def status(self) -> dict[str, Any]:
        manager = self._manager
        if manager is not None and callable(getattr(manager, "status", None)):
            try:
                return {"available": True, "message": "Arbiter 可用。", "usage": manager.status()}
            except Exception as exc:
                return {"available": False, "message": f"Arbiter 状态读取失败：{exc}", "usage": dict(self.local_usage)}
        return {
            "available": self.available,
            "message": "Arbiter 可用。" if self.available else self._error_message,
            "usage": dict(self.local_usage),
        }

    def write_budget_log(self, agent_name: str, tokens: int, result: dict[str, Any]) -> Path:
        target = self.vault_path / "05-Agents" / "arbiter-budget-log.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_text("# Arbiter 预算日志\n\n", encoding="utf-8")
        line = (
            f"- {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
            f"执行者：{agent_name} | 预算数量：{tokens} | 结果：{result.get('message', result)}\n"
        )
        with target.open("a", encoding="utf-8") as file:
            file.write(line)
        return target
