"""Personal Media OS 轻量阶段编排器。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

STAGES = (
    "IMPORT_AI_HOT", "RESEARCH", "BUILD_TOPICS", "BUILD_DRAFTS", "RUN_CHECKS",
    "WAIT_HUMAN_REVIEW", "PUBLISH_APPROVED", "COLLECT_ANALYTICS", "WRITE_INSIGHT_CANDIDATE",
)
DEFAULT_LOG = Path(__file__).resolve().parents[1] / "data" / "orchestrator_runs.jsonl"


class Orchestrator:
    def __init__(self, log_path: str | Path | None = None) -> None:
        self.log_path = Path(log_path or DEFAULT_LOG)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        stage: str,
        *,
        allow_network: bool = False,
        allow_model: bool = False,
        allow_publish: bool = False,
        allow_analytics: bool = False,
    ) -> dict[str, Any]:
        started = datetime.now().isoformat(timespec="seconds")
        try:
            if stage not in STAGES:
                raise ValueError(f"未知 Orchestrator 阶段：{stage}")
            if stage == "IMPORT_AI_HOT" and not allow_network:
                return self._record(stage, "skipped", "network 未显式开启", [], started)
            if stage in ("PUBLISH_APPROVED",) and not allow_publish:
                return self._record(stage, "skipped", "publish 未显式开启", [], started)
            if stage in ("COLLECT_ANALYTICS",) and not allow_analytics:
                return self._record(stage, "skipped", "analytics 未显式开启", [], started)
            if stage in ("RESEARCH", "BUILD_DRAFTS") and not allow_model:
                return self._record(stage, "skipped", "model 未显式开启", [], started)
            return self._record(stage, "ran", "阶段已通过安全闸门，具体执行器待接入", [], started)
        except Exception as exc:
            return self._record(stage, "failed", str(exc), [], started)

    def _record(self, stage: str, status: str, message: str, side_effects: list[str], started: str) -> dict[str, Any]:
        result = {"stage": stage, "status": status, "message": message, "external_side_effects": side_effects, "started_at": started, "finished_at": datetime.now().isoformat(timespec="seconds")}
        if status == "failed":
            result["error"] = message
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
        return result
