"""Phase 21：自动化 Agent 的每日流程。

PLAN 的每日流程：
    09:00 Research → Topic → Strategy → Content → Human Review → Publisher
    → Analytics → Memory → 第二天继续

调度本身交给 cron/launchd（09:00 调 `scripts/run_daily.py`）；本类负责跑一轮并留下记录。

边界：
- 三件「对外」的事默认关闭，必须显式打开，且互不隐含：
    research=True   允许联网调研（否则只用本地 materials，research 阶段如实 skipped）
    publish_x=True  注入 XWorkflow；再加 send=True 才真实发送（dry_run=False）
    collect=True    跑 X 指标采集（要 X 后端与发布记录）
- 人审不自动过：内容最多到 REVIEW；发布只发 APPROVED。
- 每次运行追加 `data/daily_runs.jsonl`，把「今天必须人做的事」汇总成 todo。
- 本层不写 Strategy 记忆；策略候选永远 PROPOSED。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from agents.content import ContentAgent
from agents.feedback_loop import FAILED, FeedbackLoop
from agents.x_workflow import XWorkflow
from runtime.memory_api import MemoryAPI

TS = "%Y-%m-%d %H:%M:%S"
DEFAULT_LOG = Path(__file__).resolve().parents[1] / "data" / "daily_runs.jsonl"


class DailyPipeline:
    """跑一轮每日流程，交回当天的执行记录与待办清单。"""

    def __init__(
        self,
        *,
        research: bool = False,
        publish_x: bool = False,
        send: bool = False,
        collect: bool = False,
        log_path: str | Path | None = None,
        loop: FeedbackLoop | None = None,
        memory: MemoryAPI | None = None,
        content_store: Any | None = None,
        analytics_store: Any | None = None,
        publish_store: Any | None = None,
        x_workflow: Any | None = None,
        collector: Any | None = None,
        worker: Any | None = None,
    ) -> None:
        if send and not publish_x:
            raise ValueError("send=True 必须搭配 publish_x=True：不允许绕过发布开关真实发送。")
        self.research = research
        self.publish_x = publish_x
        self.send = send
        self.collect = collect
        self.log_path = Path(log_path) if log_path else DEFAULT_LOG
        self._loop = loop
        self._memory = memory
        self._content_store = content_store
        self._analytics_store = analytics_store
        self._publish_store = publish_store
        self._x_workflow = x_workflow
        self._collector = collector
        self._worker = worker

    # ── 依赖（按需创建，创建都不联网） ──────────────────────────────────

    @property
    def memory(self) -> MemoryAPI:
        if self._memory is None:
            self._memory = MemoryAPI()
        return self._memory

    @property
    def content_store(self) -> Any:
        if self._content_store is None:
            from runtime.content_store import ContentStore

            self._content_store = ContentStore()
        return self._content_store

    @property
    def loop(self) -> FeedbackLoop:
        if self._loop is None:
            self._loop = FeedbackLoop(
                memory=self.memory,
                content_agent=ContentAgent(store=self.content_store, memory=self.memory),
                worker=self._worker,
            )
        return self._loop

    # ── 主流程 ──────────────────────────────────────────────────────────

    def run(self, task: str | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
        started = datetime.now()
        date = started.strftime("%Y-%m-%d")
        context = dict(context or {})
        notes = self._gates(context)

        result = self.loop.run(task or f"{date} 每日流程", context)
        todo = self._todo(result, notes)
        record = {
            "at": started.strftime(TS),
            "date": date,
            "ok": bool(result["ok"]),
            "counts": result["counts"],
            "stages": [{"name": step["name"], "status": step["status"]}
                       for step in result["steps"]],
            "todo": len(todo),
            "duration_ms": int((datetime.now() - started).total_seconds() * 1000),
        }
        notes += self._append_log(record)

        return {
            "ok": bool(result["ok"]),
            "date": date,
            "loop": result,
            "todo": todo,
            "notes": notes,
            "log_path": str(self.log_path),
            "record": record,
        }

    # ── 对外开关 ────────────────────────────────────────────────────────

    def _gates(self, context: dict[str, Any]) -> list[str]:
        """把「默认不对外」落到 context 上，并记下因此被关掉的路径。"""
        notes: list[str] = []
        if not self.research:
            channel = context.pop("channel", None)
            if channel:
                notes.append(f"未开启联网研究（research=False），跳过 channel={channel}")
        if self.collect and "collector" not in context:
            context["collector"] = self._collector if self._collector is not None else _build_collector(
                self._analytics_store, self._publish_store
            )
        if self.publish_x and self.send and "x_workflow" not in context:
            context["x_workflow"] = self._x_workflow if self._x_workflow is not None else XWorkflow(
                store=self.content_store, memory=self.memory
            )
            notes.append("X 真实发送已开启（publish_x + send）：只发 APPROVED 内容")
        elif self.publish_x and not self.send:
            notes.append("X 发布为演练位（publish_x 未加 send）：本次不发送、不改内容状态")
        return notes

    # ── 待办与日志 ──────────────────────────────────────────────────────

    @staticmethod
    def _todo(result: dict[str, Any], notes: list[str]) -> list[str]:
        items = list(notes) + list(result["next_actions"])
        publish = next((step for step in result["steps"] if step["name"] == "publish"), None)
        if publish is not None and (
            publish["data"].get("approved") or publish["status"] in ("gated", "failed")
        ):
            items.append(f"[publish] {publish['summary']}")
        for step in result["steps"]:
            if step["status"] == FAILED:
                items.append(f"[失败] {step['name']}：{step['summary']}")
        deduped: list[str] = []
        for item in items:
            if item and item not in deduped:
                deduped.append(item)
        return deduped

    def _append_log(self, record: dict[str, Any]) -> list[str]:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:  # 日志写不进去要让人看见，但不能吞掉整轮结果
            return [f"运行日志写入失败（{self.log_path}）：{exc}"]
        return []


def _build_collector(analytics_store: Any | None, publish_store: Any | None) -> Any:
    """指标采集要 X 后端；只有 collect=True 才会走到这里。"""
    from runtime.analytics_collector import AnalyticsCollector
    from runtime.x_adapter import default_x_adapter

    if analytics_store is None:
        from runtime.analytics_store import AnalyticsStore

        analytics_store = AnalyticsStore()
    if publish_store is None:
        from runtime.publish_queue import PublishJobStore

        publish_store = PublishJobStore()
    return AnalyticsCollector(store=analytics_store, x=default_x_adapter(),
                              publish_store=publish_store)
