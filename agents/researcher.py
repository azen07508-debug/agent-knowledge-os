"""Research Agent（Phase 5）。

流程：信息源 -> 搜索 -> 抓取 -> 去重 -> 分类 -> 提取事实/观点/证据 -> 候选选题。

只做编排和结构化：抽取逻辑默认走 `runtime.topics` 的规则，可在构造时注入；
候选选题不写记忆——没经过复核的选题不是长期记忆。
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

from agents.base_agent import BaseAgent
from runtime.reach_research import ReachResearch
from runtime.topics import build_candidates, dedupe_items


class ResearcherAgent(BaseAgent):
    """持续研究互联网，产出 Topic Candidate。"""

    def __init__(
        self,
        reach: ReachResearch | None = None,
        extractor: Callable[[Mapping[str, Any]], dict[str, list[Any]]] | None = None,
    ) -> None:
        super().__init__("Researcher Agent", "资料研究", 2500)
        self._reach = reach
        self.extractor = extractor

    @property
    def reach(self) -> ReachResearch:
        """按需创建：不联网的用法（传 materials）不应触发通道配置。"""
        if self._reach is None:
            self._reach = ReachResearch()
        return self._reach

    def _harvest(self, query: str, task: str, context: dict[str, Any]) -> dict[str, Any]:
        return self.reach.harvest(
            query,
            channel=context.get("channel", "web"),
            limit=int(context.get("limit", 5)),
            topic=context.get("topic", task),
        )

    def run(self, task: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        materials = context.get("materials")
        used_query = ""  # 实际用的检索词（整句 0 结果时会被拆分兜底）
        note = ""        # 拆分兜底的提示，进 summary 给日志看

        if materials is None:
            # 检索词：query（人显式给）> topic > 任务名；别拿「2026-10-02 每日流程」去搜
            query = str(context.get("query") or context.get("topic") or task)
            harvest = self._harvest(query, task, context)
            used_query = query
            if not harvest.get("ok"):
                for alt in _query_fallbacks(query):
                    trial = self._harvest(alt, task, context)
                    if trial.get("ok"):
                        harvest, used_query = trial, alt
                        note = f"（拆分检索词：{alt}）"
                        break
            if not harvest.get("ok"):
                message = f"{harvest.get('message', '未知原因')}（检索词：{used_query}）"
                failure = self.build_result(
                    task=task,
                    summary=f"调研失败：{message}",
                    details="抓取失败，未生成候选选题，也未写入任何记忆。",
                    errors=[message],
                    next_actions=["检查 agent-reach 通道配置", "稍后重试或改用其他通道"],
                )
                failure["candidates"] = []
                failure["material_count"] = 0
                failure["query"] = used_query
                return failure
            materials = harvest["items"]

        items = dedupe_items(_as_mappings(materials))
        candidates = build_candidates(items, extractor=self.extractor)

        result = self.build_result(
            task=task,
            summary=f"抓取 {len(items)} 条材料，产出 {len(candidates)} 个候选选题{note}",
            details=_render_details(candidates),
            knowledge_points=sorted({candidate.category for candidate in candidates}),
            next_actions=["人工复核候选选题及其证据", "复核通过的选题交给 Topic Engine 评分"],
        )
        result["candidates"] = [candidate.to_dict() for candidate in candidates]
        result["material_count"] = len(items)
        result["query"] = used_query
        return result


_QUERY_SPLIT = re.compile(r"[、，,；;]")


def _query_fallbacks(query: str) -> list[str]:
    """整句常 0 结果（gh 对「AI 工具、开源项目、Agent 基础设施」这类长句搜不到），按顿号拆开逐个试。"""
    parts = [part.strip() for part in _QUERY_SPLIT.split(query) if part.strip()]
    return list(dict.fromkeys(part for part in parts if part != query))


def default_research_query(memory: Any | None = None) -> str:
    """没显式给检索词时的默认搜索词：Account Memory 的内容领域（研究要围绕账号定位）。"""
    from runtime.memory_api import MemoryAPI

    api = memory or MemoryAPI()
    found = api.get("account")
    sections = found.get("sections") or {}
    return str(sections.get("内容领域") or sections.get("账号定位") or "").strip()


def _as_mappings(materials: Iterable[Any]) -> list[Mapping[str, Any]]:
    mappings: list[Mapping[str, Any]] = []
    for item in materials:
        if is_dataclass(item) and not isinstance(item, type):
            mappings.append(asdict(item))
        else:
            mappings.append(dict(item))
    return mappings


def _render_details(candidates: list[Any]) -> str:
    if not candidates:
        return "没有形成候选选题：材料不足或全部被判为无信息量。"
    blocks = []
    for index, candidate in enumerate(candidates, start=1):
        lines = [f"### {index}. {candidate.topic}（{candidate.category}）"]
        if candidate.sources:
            lines.append("- 来源：" + "、".join(candidate.sources))
        if candidate.facts:
            lines += [f"- 事实线索：{fact}" for fact in candidate.facts]
        if candidate.opinions:
            lines += [f"- 观点：{opinion}" for opinion in candidate.opinions]
        for proof in candidate.evidence:
            lines.append(f"- 证据：{proof['url']} — {proof['quote']}")
        lines.append(f"- 置信度：{candidate.confidence}（规则抽取，待人工复核）")
        blocks.append("\n".join(lines))
    return "## 候选选题\n\n" + "\n\n".join(blocks)
