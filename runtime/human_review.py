"""Phase 12：Human Review——正式发布前的强制环节。

PLAN 12：审核界面显示 原始研究 / 来源 / AI 生成内容 / Claims / Evidence /
AI 建议 / 修改记录，避免 Agent 无依据地产生内容。

边界：
    approve / request_changes 是人的动作，这里只做记录与状态推进
    只有 REVIEW 状态可审批；驳回必须写明要改什么
"""

from __future__ import annotations

from typing import Any

from runtime.content_store import ContentStore
from runtime.research_store import ResearchStore

SECTION_TITLES = {
    "status": "状态",
    "research": "原始研究",
    "sources": "来源",
    "generated": "AI 生成内容",
    "claims": "Claims（待核查断言）",
    "evidence": "Evidence（证据摘录）",
    "ai_suggestions": "AI 建议",
    "review_notes": "修改记录",
}


def build_packet(
    store: ContentStore,
    content_id: str,
    research_store: ResearchStore | None = None,
) -> dict[str, Any]:
    """汇总一条内容的完整审核材料；找不到对象抛 FileNotFoundError。"""
    obj = store.get(content_id)
    if obj is None:
        raise FileNotFoundError(f"内容对象不存在：{content_id}")

    research: list[dict[str, Any]] = []
    if research_store is not None:
        for url in obj.sources:
            material = research_store.get(url)
            if material:
                research.append(
                    {
                        "url": url,
                        "title": material.get("title") or "",
                        "content": material.get("content") or "",
                        "fetched_at": material.get("fetched_at") or "",
                    }
                )

    return {
        "ok": True,
        "content_id": content_id,
        "status": obj.status,
        "evidence_status": obj.evidence_status,
        "content_source": obj.content_source,
        "title_candidates": list(obj.title_candidates),
        "can_approve": obj.status == "REVIEW",
        "research": research,
        "sources": list(obj.sources),
        "generated": {"hook": obj.hook, "core_content": obj.core_content, "posts": obj.platform_posts.get("X") or obj.core_content.splitlines()},
        "claims": list(obj.claims),
        "evidence": list(obj.evidence),
        "ai_suggestions": list(obj.ai_suggestions),
        "review_notes": list(obj.review_notes),
    }


def render(packet: dict[str, Any]) -> str:
    """审核界面（终端文本版）：PLAN 12 要求的七块信息。"""
    lines = [
        f"## 审核：{packet['content_id']} — {packet['status']}",
        f"可审批：{'是（REVIEW）' if packet['can_approve'] else '否（只有 REVIEW 状态可审批）'}",
    ]
    lines.append(f"### {SECTION_TITLES['research']}")
    if packet["research"]:
        for item in packet["research"]:
            lines.append(f"- {item['title'] or item['url']}（{item['fetched_at']}）")
            lines.append(f"  {item['content'][:200]}")
    else:
        lines.append("- （原始研究不在 ResearchStore，仅凭来源链接核对）")

    lines.append(f"### {SECTION_TITLES['sources']}")
    lines += [f"- {url}" for url in packet["sources"]] or ["- （无）"]

    lines.append(f"### {SECTION_TITLES['generated']}")
    lines.append(f"- Hook：{packet['generated']['hook']}")
    lines += [f"  {post}" for post in packet["generated"]["posts"]]

    lines.append(f"### {SECTION_TITLES['claims']}")
    lines += [f"- {claim}" for claim in packet["claims"]] or ["- （无断言）"]

    lines.append(f"### {SECTION_TITLES['evidence']}")
    lines += [f"- {item['url']} — {item['quote']}" for item in packet["evidence"]] or ["- （无证据摘录）"]

    lines.append(f"### {SECTION_TITLES['ai_suggestions']}")
    lines += [f"- {line}" for line in packet["ai_suggestions"]] or ["- （无）"]

    lines.append(f"### {SECTION_TITLES['review_notes']}")
    for item in packet["review_notes"]:
        lines.append(f"- [{item['at']}] {item['action']} by {item['reviewer'] or '?'}：{item['note'] or '—'}")
    if not packet["review_notes"]:
        lines.append("- （无）")
    return "\n".join(lines)


def approve(store: ContentStore, content_id: str, reviewer: str, note: str = "") -> dict[str, Any]:
    """人审通过：REVIEW → APPROVED，并记录审核人与意见。"""
    obj = _require_review(store, content_id, "审批")
    obj.append_review_note("APPROVED", reviewer, note)
    obj.transition("APPROVED")
    store.save(obj)
    return {"ok": True, "content_id": content_id, "status": obj.status, "reviewer": reviewer}


def request_changes(store: ContentStore, content_id: str, reviewer: str, note: str) -> dict[str, Any]:
    """人审驳回：REVIEW → DRAFT；必须写明要改什么。"""
    if not (note or "").strip():
        raise ValueError("驳回必须写明要改什么，否则作者只能靠猜。")
    obj = _require_review(store, content_id, "驳回")
    obj.append_review_note("CHANGES_REQUESTED", reviewer, note)
    obj.transition("DRAFT")
    store.save(obj)
    return {"ok": True, "content_id": content_id, "status": obj.status, "reviewer": reviewer}


def _require_review(store: ContentStore, content_id: str, action: str):
    obj = store.get(content_id)
    if obj is None:
        raise FileNotFoundError(f"内容对象不存在：{content_id}")
    if obj.status != "REVIEW":
        raise ValueError(f"{action}只能针对 REVIEW 状态，当前是 {obj.status}。")
    return obj
