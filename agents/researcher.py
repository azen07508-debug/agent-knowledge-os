"""Research Agent（Phase 5）。

流程：信息源 -> 搜索 -> 抓取 -> 去重 -> 分类 -> 提取事实/观点/证据 -> 候选选题。

只做编排和结构化：抽取逻辑默认走 `runtime.topics` 的规则，可在构造时注入；
候选选题不写记忆——没经过复核的选题不是长期记忆。
"""

from __future__ import annotations

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

    def run(self, task: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        materials = context.get("materials")

        if materials is None:
            harvest = self.reach.harvest(
                task,
                channel=context.get("channel", "web"),
                limit=int(context.get("limit", 5)),
                topic=context.get("topic", task),
            )
            if not harvest.get("ok"):
                message = harvest.get("message", "未知原因")
                failure = self.build_result(
                    task=task,
                    summary=f"调研失败：{message}",
                    details="抓取失败，未生成候选选题，也未写入任何记忆。",
                    errors=[message],
                    next_actions=["检查 agent-reach 通道配置", "稍后重试或改用其他通道"],
                )
                failure["candidates"] = []
                failure["material_count"] = 0
                return failure
            materials = harvest["items"]

        items = dedupe_items(_as_mappings(materials))
        candidates = build_candidates(items, extractor=self.extractor)

        result = self.build_result(
            task=task,
            summary=f"抓取 {len(items)} 条材料，产出 {len(candidates)} 个候选选题",
            details=_render_details(candidates),
            knowledge_points=sorted({candidate.category for candidate in candidates}),
            next_actions=["人工复核候选选题及其证据", "复核通过的选题交给 Topic Engine 评分"],
        )
        result["candidates"] = [candidate.to_dict() for candidate in candidates]
        result["material_count"] = len(items)
        return result


def _as_mappings(materials: Iterable[Any]) -> list[Mapping[str, Any]]:
    return [asdict(item) if is_dataclass(item) else dict(item) for item in materials]


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
