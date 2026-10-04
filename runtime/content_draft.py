"""Phase 9：内容生产规则层（大纲 / 起草 / 事实核查 / 风格检查 / AI 味检查）。

边界：不接 LLM key——默认全部规则式实现，可由调用方注入 drafter 换成更强的生成器。
    事实核查只回答「这条断言能否在证据里找到出处」，不冒充「证明为真/为假」。
    检查不过就是不过：Agent 不会自己放行，最后一步永远是 Human Review。
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

X_POST_LIMIT = 280
"""X 单条上限。"""

AI_FLAVOR_PATTERNS: tuple[str, ...] = (
    "首先", "其次", "总之", "综上所述", "让我们", "在当今", "值得注意的是",
    "赋能", "抓手", "闭环", "深入探讨", "希望本文", "不难发现", "众所周知",
)
"""典型机器腔/套话，命中即扣分。"""

SUPPORTED = "supported"
UNVERIFIABLE = "unverifiable"


def build_outline(candidate: Mapping[str, Any]) -> list[str]:
    """从候选选题生成大纲行：问题 → 事实 → 观点 → 角度 → 结论。"""
    topic = str(candidate.get("topic") or "该选题")
    angle = str(candidate.get("angle") or "")
    lines = [f"问题：{topic} 为什么值得开发者看？"]
    for fact in list(candidate.get("facts") or [])[:3]:
        lines.append(f"事实：{fact}")
    for opinion in list(candidate.get("opinions") or [])[:2]:
        lines.append(f"观点：{opinion}")
    if angle:
        lines.append(f"角度：{angle}")
    lines.append("结论：给出可操作的下一步，不喊口号")
    return lines


def draft_thread(
    candidate: Mapping[str, Any],
    outline: Sequence[str],
    drafter: Callable[..., list[str]] | None = None,
) -> list[str]:
    """产出 X Thread 的各条内容（首条是 Hook）；注入 drafter 时以它为准。"""
    topic = str(candidate.get("topic") or "")
    angle = str(candidate.get("angle") or "")
    audience = str(candidate.get("audience") or "")
    title_candidates = [str(item).strip() for item in candidate.get("title_candidates") or [] if str(item).strip()]
    hook = title_candidates[0] if title_candidates else (angle or topic or "一条实测")
    if angle and hook != angle and len(hook) + len(angle) + 2 <= X_POST_LIMIT:
        hook = f"{hook}\n\n{angle}"

    if drafter is not None:
        posts = list(drafter(hook=hook, outline=list(outline), audience=audience))
        if posts:
            return [_shorten(post) for post in posts]

    posts = [_shorten(hook)]
    posts += [_shorten(line) for line in outline]
    sources = list(candidate.get("sources") or [])
    if sources:
        posts.append(_shorten("来源：" + "、".join(sources[:3])))
    return posts


def fact_check(claims: Sequence[str], evidence: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """逐条断言找出处：证据摘录里能找到 → supported，找不到 → unverifiable。"""
    haystack = " ".join(
        str(item.get("quote") or "") + " " + str(item.get("url") or "")
        for item in evidence
    ).lower()
    items = []
    for claim in claims:
        normalized = _normalize(str(claim))
        status = SUPPORTED if normalized and normalized in _normalize(haystack) else UNVERIFIABLE
        items.append({"claim": str(claim), "status": status})
    return {
        "ok": all(item["status"] == SUPPORTED for item in items),
        "checked": len(items),
        "supported": sum(1 for item in items if item["status"] == SUPPORTED),
        "items": items,
    }


def style_check(posts: Sequence[str], banned_words: Sequence[str] = ()) -> dict[str, Any]:
    """X 形式检查：单条长度、Hook 存在、禁用词（来自账号「禁止内容」）。"""
    issues: list[str] = []
    if not posts:
        issues.append("没有内容可发。")
    else:
        first_post = str(posts[0]).strip()
        if len(posts) > 1 and not first_post:
            issues.append("第一条必须有标题或首句 Hook。")
        if any(r"\n" in post or r"\t" in post for post in posts):
            issues.append("内容包含字面量转义符号 \\n 或 \\t，必须改为真实换行或自然段。")
        if any(_crowded_colon(post) for post in posts):
            issues.append("排版过密：冒号后紧接长段落，需拆成引导句与下一段。")
        if not str(posts[0]).strip():
            issues.append("首条 Hook 为空。")
        if len(posts) > 20:
            issues.append(f"Thread 过长：{len(posts)} 条，超过 20 条上限。")
    for index, post in enumerate(posts, start=1):
        if len(post) > X_POST_LIMIT:
            issues.append(f"第 {index} 条超长：{len(post)} 字符 > {X_POST_LIMIT}。")
        for word in banned_words:
            if word and word in post:
                issues.append(f"第 {index} 条命中账号禁用词「{word}」。")
    return {"ok": not issues, "issues": issues}


def _crowded_colon(post: str) -> bool:
    """长文中冒号后的长文本应另起段，避免工具清单挤成文字墙。"""
    text = str(post)
    for index, char in enumerate(text):
        if char != "：" or index + 1 >= len(text) or text[index + 1] == "\n":
            continue
        tail = text[index + 1 :].split("\n", 1)[0]
        if len(tail.strip()) > 80:
            return True
    return False


def ai_flavor_check(text: str) -> dict[str, Any]:
    """AI 味检查：套话、模板腔命中即列出，命中即不过。"""
    hits = [pattern for pattern in AI_FLAVOR_PATTERNS if pattern in text]
    return {"ok": not hits, "hits": hits}


def all_checks_passed(checks: Mapping[str, Any]) -> bool:
    return all(section.get("ok") for section in checks.values())


def _shorten(text: str, limit: int = X_POST_LIMIT) -> str:
    text = str(text).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()
