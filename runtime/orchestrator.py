"""Personal Media OS 轻量阶段编排器。

每个阶段有真实执行器；执行器需要的外部能力通过 `deps` 注入，未注入时如实
skipped（不伪造成功）。默认不联网、不发布、不采集。

ponytail: RESEARCH/BUILD_DRAFTS 走规则式实现，当前不调用模型；`allow_model`
只为将来注入 LLM 起草器保留，现阶段没有闸门消费它。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

STAGES = (
    "IMPORT_AI_HOT", "RESEARCH", "BUILD_TOPICS", "BUILD_DRAFTS", "RUN_CHECKS",
    "WAIT_HUMAN_REVIEW", "PUBLISH_APPROVED", "COLLECT_ANALYTICS", "WRITE_INSIGHT_CANDIDATE",
)
DEFAULT_LOG = Path(__file__).resolve().parents[1] / "data" / "orchestrator_runs.jsonl"
AIHOT_BASE_URL = "http://127.0.0.1:3000"


def _contents(orchestrator: Orchestrator) -> list[dict[str, Any]]:
    if "contents" in orchestrator.deps:
        return list(orchestrator.deps["contents"])
    from runtime.content_store import ContentStore

    return ContentStore().list()


# ── 执行器 ────────────────────────────────────────────────────────────────


def _exec_import(orchestrator: Orchestrator) -> dict[str, Any]:
    from runtime.aihot_bridge import fetch_selected_snapshot, import_selected_snapshot

    fetch = orchestrator.deps.get("fetch_snapshot") or (
        lambda: fetch_selected_snapshot(orchestrator.deps.get("aihot_base_url", AIHOT_BASE_URL))
    )
    importer = orchestrator.deps.get("import_snapshot") or import_selected_snapshot
    store = orchestrator.deps.get("research_store")
    if store is None:
        from runtime.research_store import ResearchStore

        store = ResearchStore()
    payload = fetch()
    result = dict(importer(payload, store))
    return {
        "status": "ran",
        "message": f"导入 AIHOT 精选：新建 {result.get('created', 0)} 条，"
                   f"更新 {result.get('updated', 0)} 条，跳过 {result.get('skipped', 0)} 条。",
        "external_side_effects": ["network"],
        "data": result,
    }


def _exec_research(orchestrator: Orchestrator) -> dict[str, Any]:
    researcher = orchestrator.deps.get("researcher")
    if researcher is None:
        from agents.researcher import ResearcherAgent, default_research_query

        researcher = ResearcherAgent()
    query = str(orchestrator.deps.get("research_query") or default_research_query())
    result = researcher.run("Orchestrator RESEARCH", {"query": query})
    candidates = list(result.get("candidates") or [])
    if not candidates:
        return {
            "status": "failed",
            "message": f"研究失败：{result.get('summary') or '没有产出候选选题'}（query={query}）",
            "external_side_effects": ["network"],
            "data": {"query": query},
        }
    return {
        "status": "ran",
        "message": f"研究「{query}」：{len(candidates)} 个候选选题。",
        "external_side_effects": ["network"],
        "data": {"query": query, "candidates": len(candidates)},
    }


def _exec_topics(orchestrator: Orchestrator) -> dict[str, Any]:
    candidates = list(orchestrator.deps.get("candidates") or [])
    if not candidates:
        return {
            "status": "skipped",
            "message": "缺选题候选：先跑 RESEARCH 阶段（deps['candidates']）。",
            "external_side_effects": [],
            "data": {},
        }
    engine = orchestrator.deps.get("topic_engine")
    if engine is None:
        from runtime.topic_engine import TopicEngine

        engine = TopicEngine()
    result = engine.recommend(candidates, top_k=int(orchestrator.deps.get("top_k", 5)))
    recommendations = list(result.get("recommendations") or [])
    return {
        "status": "ran",
        "message": f"评分 {result.get('checked', len(candidates))} 个候选，"
                   f"产出 {len(recommendations)} 条推荐。",
        "external_side_effects": [],
        "data": {"checked": result.get("checked"), "recommendations": len(recommendations)},
    }


def _exec_drafts(orchestrator: Orchestrator) -> dict[str, Any]:
    recommendation = orchestrator.deps.get("recommendation")
    if not recommendation:
        return {
            "status": "skipped",
            "message": "缺 recommendation：先 BUILD_TOPICS 并人工选定（deps['recommendation']）。",
            "external_side_effects": [],
            "data": {},
        }
    agent = orchestrator.deps.get("content_agent")
    if agent is None:
        from agents.content import ContentAgent

        agent = ContentAgent()
    result = agent.run("Orchestrator BUILD_DRAFTS",
                       {"recommendation": recommendation, "brief": orchestrator.deps.get("brief")})
    content = result.get("content")
    if not content:
        return {
            "status": "skipped",
            "message": str(result.get("summary") or "没有生成内容。"),
            "external_side_effects": [],
            "data": {},
        }
    return {
        "status": "ran",
        "message": str(result.get("summary") or "草稿已生成，进入检查。"),
        "external_side_effects": [],
        "data": {"content_id": getattr(content, "id", None) or (content or {}).get("id"),
                 "status": getattr(content, "status", None) or (content or {}).get("status")},
    }


def _exec_checks(orchestrator: Orchestrator) -> dict[str, Any]:
    from runtime.content_draft import style_check

    problems: list[str] = []
    watch = [item for item in _contents(orchestrator)
             if item.get("status") in ("DRAFT", "REVIEW")]
    for item in watch:
        posts = [post for versions in (item.get("platform_posts") or {}).values()
                 for post in (versions or [])]
        if not posts:
            problems.append(f"{item.get('id')}: 缺平台帖")
            continue
        checked = style_check(posts, tuple(orchestrator.deps.get("banned_words") or ()))
        if not checked.get("ok"):
            issues = "；".join(str(issue) for issue in checked.get("issues") or [])
            problems.append(f"{item.get('id')}: {issues}")
    return {
        "status": "ran",
        "message": f"检查 {len(watch)} 条待审内容，{len(problems)} 条有问题。",
        "external_side_effects": [],
        "data": {"watched": len(watch), "problems": problems},
    }


def _exec_review(orchestrator: Orchestrator) -> dict[str, Any]:
    contents = _contents(orchestrator)
    review = sum(1 for item in contents if item.get("status") == "REVIEW")
    approved = sum(1 for item in contents if item.get("status") == "APPROVED")
    return {
        "status": "ran",
        "message": f"REVIEW 待审 {review} 条；APPROVED 待排期 {approved} 条。",
        "external_side_effects": [],
        "data": {"review": review, "approved": approved},
    }


def _exec_publish(orchestrator: Orchestrator) -> dict[str, Any]:
    approved = [item for item in _contents(orchestrator)
                if item.get("status") == "APPROVED"]
    if not approved:
        return {"status": "skipped", "message": "没有 APPROVED 内容。",
                "external_side_effects": [], "data": {}}
    workflow = orchestrator.deps.get("x_workflow")
    worker = orchestrator.deps.get("worker")
    if workflow is None and worker is None:
        return {
            "status": "skipped",
            "message": f"{len(approved)} 条已过审，但未注入发布能力"
                       "（deps['x_workflow'] / deps['worker']）。",
            "external_side_effects": [], "data": {"approved": len(approved)},
        }

    outcomes: list[dict[str, Any]] = []
    if workflow is not None:
        for item in approved:
            try:
                outcome = workflow.publish(str(item.get("id")), dry_run=False)
            except Exception as exc:  # 异常原因原样带回，便于排查
                outcome = {"ok": False, "message": f"XWorkflow.publish 异常：{exc}"}
            outcomes.append({"content_id": item.get("id"), **dict(outcome)})
    if worker is not None:
        job = worker.run_once()
        if job is not None:
            outcomes.append({"job": job.get("id"), "status": job.get("status"),
                             "ok": bool(job.get("ok")), "message": job.get("message", "")})

    done = [item for item in outcomes if item.get("ok")]
    failed = [item for item in outcomes if not item.get("ok")]
    if not outcomes:
        return {"status": "skipped", "message": "发布能力已注入，但没有执行任何发布。",
                "external_side_effects": [], "data": {"approved": len(approved)}}
    reasons = "；".join(f"{item.get('content_id') or item.get('job')}：{item.get('message')}"
                        for item in failed)
    if done and not failed:
        message = f"发布成功 {len(done)} 条。"
    elif done:
        message = f"发布成功 {len(done)} 条，失败 {len(failed)} 条：{reasons}"
    else:
        message = f"{len(failed)} 条发布全部失败：{reasons}"
    return {
        "status": "ran" if done else "failed",
        "message": message,
        "external_side_effects": ["publish"],
        "data": {"published": len(done), "failed": len(failed)},
    }


def _exec_collect(orchestrator: Orchestrator) -> dict[str, Any]:
    collector = orchestrator.deps.get("collector")
    if collector is None:
        return {
            "status": "skipped",
            "message": "未注入采集器：deps['collector']（Phase 16 AnalyticsCollector）。",
            "external_side_effects": [], "data": {},
        }
    outcome = dict(collector.collect_published(
        limit=int(orchestrator.deps.get("collect_limit", 20))))
    return {
        "status": "ran",
        "message": f"采集 {outcome.get('collected', 0)} 条，失败 {outcome.get('failed', 0)} 条。",
        "external_side_effects": ["analytics"],
        "data": outcome,
    }


def _exec_insight(orchestrator: Orchestrator) -> dict[str, Any]:
    agent = orchestrator.deps.get("analytics_agent")
    store = orchestrator.deps.get("analytics_store")
    memory = orchestrator.deps.get("memory")
    if agent is None:
        from agents.analytics import AnalyticsAgent
        from runtime.analytics_store import AnalyticsStore
        from runtime.memory_api import MemoryAPI

        agent = AnalyticsAgent(memory=memory or MemoryAPI(),
                               store=store or AnalyticsStore())
    result = agent.run(
        "Orchestrator WRITE_INSIGHT_CANDIDATE",
        {"store": store, "write_memory": True,
         "limit": int(orchestrator.deps.get("insight_limit", 50))},
    )
    if not result.get("patterns"):
        return {
            "status": "skipped",
            "message": str(result.get("summary") or "没有可分析的表现数据。"),
            "external_side_effects": [], "data": {},
        }
    writes = len(result.get("memory_writes") or [])
    return {
        "status": "ran",
        "message": f"{result.get('summary', '')}；写入观察 {writes} 条（pending，等 Memory Review）。",
        "external_side_effects": [],
        "data": {"memory_writes": writes},
    }


EXECUTORS = {
    "IMPORT_AI_HOT": _exec_import,
    "RESEARCH": _exec_research,
    "BUILD_TOPICS": _exec_topics,
    "BUILD_DRAFTS": _exec_drafts,
    "RUN_CHECKS": _exec_checks,
    "WAIT_HUMAN_REVIEW": _exec_review,
    "PUBLISH_APPROVED": _exec_publish,
    "COLLECT_ANALYTICS": _exec_collect,
    "WRITE_INSIGHT_CANDIDATE": _exec_insight,
}


class Orchestrator:
    def __init__(self, log_path: str | Path | None = None,
                 deps: Mapping[str, Any] | None = None) -> None:
        self.log_path = Path(log_path or DEFAULT_LOG)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.deps = dict(deps or {})

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
            if stage in ("IMPORT_AI_HOT", "RESEARCH") and not allow_network:
                return self._record(stage, "skipped", "network 未显式开启", [], started)
            if stage == "PUBLISH_APPROVED" and not allow_publish:
                return self._record(stage, "skipped", "publish 未显式开启", [], started)
            if stage == "COLLECT_ANALYTICS" and not allow_analytics:
                return self._record(stage, "skipped", "analytics 未显式开启", [], started)
            outcome = EXECUTORS[stage](self)
            return self._record(
                stage,
                str(outcome.get("status") or "ran"),
                str(outcome.get("message") or ""),
                list(outcome.get("external_side_effects") or []),
                started,
                data=outcome.get("data"),
            )
        except Exception as exc:
            return self._record(stage, "failed", str(exc), [], started)

    def _record(self, stage: str, status: str, message: str,
                side_effects: list[str], started: str,
                data: Mapping[str, Any] | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "stage": stage,
            "status": status,
            "message": message,
            "external_side_effects": side_effects,
            "started_at": started,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }
        if data is not None:
            result["data"] = dict(data)
        if status == "failed":
            result["error"] = message
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
        return result
