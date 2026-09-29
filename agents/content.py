"""Content Agent（Phase 9）。

流程：Topic → Research → Evidence → Outline → Draft → Fact Check → Style Check
      → AI味检查 → Human Review

第一阶段只做 X Post / X Thread。三道检查全过才进 REVIEW；过了也只到 REVIEW——
APPROVED 永远由人来点。不接 LLM key，起草默认走规则，可注入 drafter。
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

from agents.base_agent import BaseAgent
from runtime.content_draft import (
    ai_flavor_check,
    all_checks_passed,
    build_outline,
    draft_thread,
    fact_check,
    style_check,
)
from runtime.content_object import ContentObject, idea_from_recommendation
from runtime.content_store import ContentStore
from runtime.memory_api import MemoryAPI


class ContentAgent(BaseAgent):
    """把一个候选选题做成待人审的 X Thread 草稿。"""

    def __init__(
        self,
        store: ContentStore | None = None,
        memory: MemoryAPI | None = None,
        drafter: Callable[..., list[str]] | None = None,
    ) -> None:
        super().__init__("Content Agent", "内容生产", 3000)
        self._store = store
        self._memory = memory
        self.drafter = drafter

    @property
    def store(self) -> ContentStore:
        if self._store is None:
            self._store = ContentStore()
        return self._store

    @property
    def memory(self) -> MemoryAPI:
        if self._memory is None:
            self._memory = MemoryAPI()
        return self._memory

    def run(self, task: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        recommendation = context.get("recommendation") or context.get("candidate")
        if recommendation is None:
            return self._failure(
                task,
                "缺少输入：需要 recommendation（Phase 6）或 candidate（Phase 5）",
                ["先跑 ResearchAgent / TopicEngine 得到选题"],
            )

        candidate = dict(recommendation)
        if not candidate.get("sources") or not candidate.get("evidence"):
            return self._failure(
                task,
                "缺少研究证据：没有 sources/evidence 的选题不能起草",
                ["先跑 ResearchAgent 抓材料并提取证据"],
            )

        brief = context.get("brief")
        content = idea_from_recommendation(candidate, brief)
        self.store.save(content)

        # Evidence：材料齐了才算研究过
        content.transition("RESEARCHED")

        outline = build_outline(candidate)
        posts = draft_thread({**candidate, "audience": _audience(candidate, brief)}, outline, self.drafter)
        hook = posts[0] if posts else ""
        content.fill({"hook": hook, "core_content": "\n".join(posts)})
        content.transition("DRAFT")

        checks = {
            "fact_check": fact_check(content.claims, content.evidence),
            "style_check": style_check(posts, self._banned_words()),
            "ai_flavor_check": ai_flavor_check(content.core_content),
        }

        issues = _issues(checks)
        next_actions = ["Human Review：人工决定是否 APPROVED，Agent 不自己放行"]
        if all_checks_passed(checks):
            try:
                content.transition("REVIEW")
                summary = f"草稿完成并通过检查：{len(posts)} 条 X Thread，已进入 REVIEW 等人审"
            except ValueError as exc:  # 状态机必填没满足：如没有任何待核查断言
                issues.append(str(exc))
                summary = f"草稿已生成但状态机未放行：{exc}"
                next_actions = ["补齐必填字段后重新提交 REVIEW", *next_actions]
        else:
            summary = f"草稿已生成但检查未通过：{len(issues)} 个问题，状态停在 DRAFT"
            next_actions = ["修复检查问题后重新提交 REVIEW", *next_actions]

        self.store.save(content)  # 对象上的 transition/fill 不自动落库，这里统一写回

        result = self.build_result(
            task=task,
            summary=summary,
            details=_render(content, posts, checks),
            knowledge_points=[name for name, section in checks.items() if section["ok"]],
            errors=issues,
            next_actions=next_actions,
        )
        result["content"] = content.to_dict()
        result["posts"] = posts
        result["checks"] = checks
        result["pending_human_review"] = content.status == "REVIEW"
        return result

    # ── 辅助 ────────────────────────────────────────────────────────────

    def _failure(self, task: str, summary: str, next_actions: list[str]) -> dict[str, Any]:
        result = self.build_result(
            task=task,
            summary=summary,
            details="没有生成内容，也没有写入 ContentStore。",
            errors=[summary],
            next_actions=next_actions,
        )
        result["content"] = None
        result["posts"] = []
        result["checks"] = {}
        result["pending_human_review"] = False
        return result

    def _banned_words(self) -> list[str]:
        """账号「禁止内容」拆成词表；读不到就不设禁用词（不编造）。"""
        try:
            found = self.memory.get("account")
        except Exception:
            return []
        if not found["ok"]:
            return []
        raw = str(found["sections"].get("禁止内容") or "")
        return [word.strip() for word in re.split(r"[、,，/;；]", raw) if word.strip()]


def _audience(candidate: Mapping[str, Any], brief: Mapping[str, Any] | None) -> str:
    audience = str(candidate.get("audience") or "")
    if audience in ("", "UNKNOWN") and brief:
        audience = " ".join(str(line) for line in brief.get("answer") or [])
    return audience


def _issues(checks: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    fact = checks.get("fact_check") or {}
    for item in fact.get("items", []):
        if item["status"] != "supported":
            issues.append(f"事实核查：断言无出处——{item['claim']}")
    issues += list((checks.get("style_check") or {}).get("issues") or [])
    hits = (checks.get("ai_flavor_check") or {}).get("hits") or []
    if hits:
        issues.append("AI 味：命中套话 " + "、".join(hits))
    return issues


def _render(content: ContentObject, posts: list[str], checks: Mapping[str, Any]) -> str:
    lines = [
        f"### {content.topic}（{content.status}）",
        f"- Hook：{content.hook}",
        f"- 断言 {len(content.claims)} 条，来源 {len(content.sources)} 条",
        "",
        "Thread：",
    ]
    lines += [f"{index}. {post}" for index, post in enumerate(posts, start=1)]
    lines.append("")
    for name, section in checks.items():
        mark = "✓" if section.get("ok") else "✗"
        lines.append(f"- {mark} {name}")
    return "\n".join(lines)
