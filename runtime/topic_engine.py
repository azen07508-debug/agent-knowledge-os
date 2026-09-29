"""Phase 6：Topic Engine（选题评分与推荐）。

输入 Phase 5 的 TopicCandidate + Account Memory，输出可解释的选题推荐：
为什么值得研究、证据是什么、是否适合当前账号、有哪些可用角度。

边界：
    不做「AI 热点排行榜」：没有数据的字段写 UNKNOWN，不编造竞争度
    不改记忆：只读 Account Memory，不写任何笔记
    规则式评分，每个分数都能说清来自哪一项
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

from runtime.memory_api import MemoryAPI
from runtime.topics import CATEGORIES, TopicCandidate

EVIDENCE_MAX = 40
FRESH_MAX = 25
FIT_MAX = 35

FRESH_WINDOW = ((7, 25), (30, 15), (90, 5))
"""材料时效：7 天内满分，30 天内 15 分，90 天内 5 分，更旧或未知 0 分。"""

CONTENT_TYPE_BY_CATEGORY = {
    "内容创作": "X Thread",
    "平台运营": "X Thread",
    "记忆系统": "X Thread",
    "AI 工具": "X Thread",
    "数据增长": "X Post",
    "未分类": "X Post",
}
"""Phase 9 第一阶段只做 X Post / X Thread。"""

ANGLE_BY_CATEGORY = {
    "记忆系统": ["冷/暖/热分层实测", "两种记忆方案对比", "一次真实迁移复盘"],
    "AI 工具": ["上手实测", "工作流对比", "踩坑与边界"],
    "内容创作": ["拆解一条高互动内容", "Hook 前后对比", "反常识写作观点"],
    "平台运营": ["平台机制变化解读", "一次运营实验复盘", "节奏与排期实测"],
    "数据增长": ["一组数据的读法", "指标异常排查", "小样本结论的边界"],
    "未分类": ["实测拆解", "方案对比", "反常识观点"],
}
DEFAULT_ANGLES = ANGLE_BY_CATEGORY["未分类"]

UNKNOWN = "UNKNOWN"


@dataclass
class TopicRecommendation:
    """一个带理由的选题推荐。"""

    topic: str
    category: str
    angles: list[str] = field(default_factory=list)
    audience: str = UNKNOWN
    sources: list[str] = field(default_factory=list)
    evidence: list[dict[str, str]] = field(default_factory=list)
    freshness: str = UNKNOWN
    competition: str = UNKNOWN
    account_fit: str = UNKNOWN
    content_type: str = "X Post"
    why: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    score: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TopicEngine:
    """把候选选题按 证据/时效/账号契合 三项打分并给出理由。"""

    def __init__(self, memory: MemoryAPI | None = None) -> None:
        self.memory = memory or MemoryAPI()

    def recommend(
        self,
        candidates: Iterable[TopicCandidate | Mapping[str, Any]],
        top_k: int = 5,
    ) -> dict[str, Any]:
        account = self.account_profile()
        items = [c.to_dict() if isinstance(c, TopicCandidate) else dict(c) for c in candidates]

        ranked = []
        for item in items:
            recommendation = self._build(item, account)
            ranked.append(recommendation)
        ranked.sort(key=lambda item: item.score, reverse=True)

        warnings = []
        if not account:
            warnings.append("没有 Account Memory：账号契合度无法判断，全部标为 UNKNOWN。")

        return {
            "ok": True,
            "checked": len(ranked),
            "account": account,
            "recommendations": [item.to_dict() for item in ranked[: max(top_k, 0)]],
            "warnings": warnings,
        }

    def account_profile(self) -> dict[str, str]:
        """读 Account Memory；缺失或异常时返回空字典（不编造账号定位）。"""
        try:
            found = self.memory.get("account")
        except Exception:  # 记忆层不可用不应让选题引擎整体失败
            return {}
        if not found.get("ok"):
            return {}
        sections = found["sections"]
        return {
            "定位": sections.get("账号定位", ""),
            "受众": sections.get("目标受众", ""),
            "领域": sections.get("内容领域", ""),
            "支柱": sections.get("内容支柱", ""),
        }

    # ── 打分 ────────────────────────────────────────────────────────────

    def _build(self, item: Mapping[str, Any], account: Mapping[str, str]) -> TopicRecommendation:
        topic = str(item.get("topic") or "未命名选题")
        category = str(item.get("category") or "未分类")
        sources = list(item.get("sources") or [])
        evidence = list(item.get("evidence") or [])
        facts = list(item.get("facts") or [])
        freshness = str(item.get("freshness") or UNKNOWN)

        evidence_score = min(len(sources), 3) * 10 + (10 if facts else 0)
        fresh_score = _freshness_score(freshness)
        fit, fit_reason = self._account_fit(topic, category, account)
        fit_score = {"HIGH": FIT_MAX, "MEDIUM": 20, "LOW": 5, UNKNOWN: 10}[fit]

        recommendation = TopicRecommendation(
            topic=topic,
            category=category,
            angles=list(ANGLE_BY_CATEGORY.get(category, DEFAULT_ANGLES)),
            audience=account.get("受众") or UNKNOWN,
            sources=sources,
            evidence=evidence,
            freshness=freshness,
            account_fit=fit,
            content_type=CONTENT_TYPE_BY_CATEGORY.get(category, "X Post"),
            score=evidence_score + fresh_score + fit_score,
        )

        recommendation.why = self._why(sources, facts, fresh_score, fit_reason, evidence)
        recommendation.blockers = self._blockers(sources, facts, freshness, fit, evidence)
        return recommendation

    def _account_fit(self, topic: str, category: str, account: Mapping[str, str]) -> tuple[str, str]:
        if not account:
            return UNKNOWN, "缺少 Account Memory，无法判断是否适合当前账号。"
        account_text = " ".join(value for value in account.values() if value).lower()
        if not account_text.strip():
            return UNKNOWN, "Account Memory 字段为空。"

        keyword_hits = [word for word in CATEGORIES.get(category, ()) if word.lower() in account_text]
        if keyword_hits:
            return "HIGH", f"分类「{category}」命中账号定位词：{'、'.join(keyword_hits[:3])}。"

        topic_hits = overlap_words(topic, account_text)
        if topic_hits:
            return "MEDIUM", f"选题与账号文本有共同词：{'、'.join(topic_hits[:3])}。"
        return "LOW", "选题与当前账号定位、支柱、受众都没有直接关联。"

    @staticmethod
    def _why(sources: list[str], facts: list[str], fresh_score: int, fit_reason: str, evidence: list) -> list[str]:
        reasons = []
        if sources:
            reasons.append(f"有 {len(sources)} 条来源" + (f"、{len(facts)} 条事实线索" if facts else ""))
        if evidence:
            reasons.append("证据可追溯到具体摘录")
        if fresh_score >= 15:
            reasons.append("材料仍在时效窗口内")
        reasons.append(fit_reason)
        return reasons

    @staticmethod
    def _blockers(sources: list[str], facts: list[str], freshness: str, fit: str, evidence: list) -> list[str]:
        blockers = []
        if not sources:
            blockers.append("没有来源，先补材料")
        if not facts:
            blockers.append("缺少可引用的事实线索，先补证据")
        if not evidence:
            blockers.append("没有可展示的证据摘录")
        if freshness == UNKNOWN:
            blockers.append("材料时间未知，需要确认时效")
        if fit == "LOW":
            blockers.append("与当前账号定位关联弱，先人工判断要不要做")
        if fit == UNKNOWN:
            blockers.append("缺 Account Memory，无法判断账号契合度")
        return blockers


def _freshness_score(freshness: str) -> int:
    """按材料日期给时效分；日期未知或无法解析一律 0 分。"""
    from datetime import datetime

    if freshness == UNKNOWN or not freshness:
        return 0
    try:
        days = (datetime.now() - datetime.strptime(freshness[:10], "%Y-%m-%d")).days
    except ValueError:
        return 0
    if days < 0:
        return 0
    for window, score in FRESH_WINDOW:
        if days <= window:
            return score
    return 0


def overlap_words(text: str, account_text: str) -> list[str]:
    """找共同词：拉丁词按整词（≥3 字符，避免 ag/ge 这种子串噪声），中文按二字滑窗。"""
    right = set(_tokens(account_text))
    hits: list[str] = []
    for token in _tokens(text):
        if token in right and token not in hits:
            hits.append(token)
    return hits


LATIN_TOKEN = re.compile(r"[a-z0-9#+]{3,}")
CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")


def _tokens(text: str) -> list[str]:
    lowered = text.lower()
    tokens = LATIN_TOKEN.findall(lowered)
    for run in CJK_RUN.findall(lowered):
        tokens += [run[index : index + 2] for index in range(len(run) - 1)]
    return tokens
