"""可复用的 X 长帖内容包。

这里保存经过人工选择的选题草稿，而不是把公开资料伪装成实测结论。
内容包先进入 REVIEW；只有用户确认并完成实际验证后，才允许变更为 SELF_TESTED。
"""

from __future__ import annotations

from typing import Any

from runtime.content_object import ContentObject


def goose_public_research_pack() -> dict[str, Any]:
    """返回 Goose 的公开资料观察稿，适合作为今天的第一条候选内容。"""
    return {
        "topic": "Goose：从聊天框走向本地 Agent 工作流",
        "title_candidates": [
            "为什么我开始不信‘万能 Agent’了？看完 Goose 的本地工作流后",
            "Agent 的下一阶段，可能不是更会聊天，而是更能被控制",
            "开源 Agent 开始从聊天框走向操作系统了吗？",
            "真正有用的 Agent，不该只会回答问题",
        ],
        "angle": "把 Agent 当成可组合、可审计的本地工作流，而不是聊天机器人",
        "audience": "开发者、AI Agent 玩家、开源工具用户",
        "content_source": "公开资料观察，未完成本地实测",
        "evidence_status": "PUBLIC_SOURCES",
        "sources": [
            "https://github.com/block/goose",
            "https://goose-docs.ai/",
        ],
        "evidence": [
            {
                "url": "https://github.com/block/goose",
                "quote": "Goose is an open source AI agent that runs on your computer.",
                "kind": "official_project",
            },
            {
                "url": "https://goose-docs.ai/",
                "quote": "Desktop app, CLI, API, MCP extensions, recipes, subagents and permission controls.",
                "kind": "official_docs",
            },
        ],
        "facts": [
            "Goose提供桌面端、CLI和API形态",
            "Goose支持MCP扩展与可复用recipes",
            "Goose强调子Agent和工具权限控制",
        ],
        "title": "为什么我开始不信‘万能 Agent’了？看完 Goose 的本地工作流后",
        "posts": [
            "为什么我开始不信‘万能 Agent’了？看完 Goose 的本地工作流后。\n\n不是因为 Agent 不够聪明，而是因为很多 Agent 仍然只是一个会说话的聊天框。",
            "我最近看到 Goose，一个开源、本地优先的 Agent 项目。它的重点不是再做一个聊天界面，而是把 Agent 拆成桌面端、CLI、API、MCP 扩展和可复用工作流。",
            "这几个组件放在一起，意味着 Agent 不只负责回答：它可以接工具、跑流程、调用子 Agent，也可以被限制权限。\n\n这比“给我一个答案”更接近真实工作。",
            "对我正在做的 CreatorOS 来说，真正值得借鉴的不是某个模型，而是这条链：Research → Memory → Content → Human Review → Publish → Analytics。",
            "我的判断是：\n\nAgent 的下一阶段，不是更会聊天，而是更可组合、更可暂停、更可审计。\n\n如果一次工具调用出了问题，我想知道它调用了什么、为什么调用、能不能重放，而不是只看到一句“任务失败”。",
            "但要把话说清楚：这条内容目前是公开资料观察，不是我的本地实测。下一步我会实际跑 Goose，再验证它的权限、MCP、工作流和恢复能力。\n\n你更关心 Agent 的哪一层：工具调用、记忆、工作流，还是权限控制？",
        ],
    }


def as_recommendation(pack: dict[str, Any]) -> dict[str, Any]:
    """把内容包转换成 ContentAgent 可接受的推荐结构。"""
    return {
        key: pack[key]
        for key in (
            "topic", "title_candidates", "angle", "audience", "content_source",
            "evidence_status", "sources", "evidence", "facts",
        )
        if key in pack
    }


def content_object_from_pack(pack: dict[str, Any]) -> ContentObject:
    """把人工整理过的内容包落成 REVIEW 草稿，不自动批准或发布。"""
    posts = [str(post).strip() for post in pack.get("posts") or [] if str(post).strip()]
    if not posts:
        raise ValueError("内容包没有可发布的 posts")
    obj = ContentObject(
        topic=str(pack.get("topic") or "").strip(),
        title_candidates=list(pack.get("title_candidates") or []),
        evidence_status=str(pack.get("evidence_status") or "UNKNOWN"),
        content_source=str(pack.get("content_source") or ""),
        angle=str(pack.get("angle") or ""),
        audience=str(pack.get("audience") or ""),
        sources=list(pack.get("sources") or []),
        evidence=list(pack.get("evidence") or []),
        claims=list(pack.get("facts") or []),
        hook=posts[0],
        core_content="\n".join(posts),
        platform_versions={"X": "\n".join(posts)},
        platform_posts={"X": posts},
    )
    obj.transition("RESEARCHED")
    obj.transition("DRAFT")
    obj.transition("REVIEW")
    obj.append_review_note("content_pack_created", reviewer="system", note="公开资料草稿，等待人工核验与批准")
    return obj
