"""Phase 5：Topic Candidate（候选选题）数据模型与规则式抽取。

边界：
    Research Agent 负责编排（搜索/抓取/去重/分类/成候选），不负责「理解」
    事实、观点、证据的抽取默认走规则（数字=事实、建议词=观点、URL=证据），
    可由调用方注入更强的 extractor 覆盖；规则式结果一律 LOW 置信度
    候选不写记忆：没有经过验证的选题不是长期记忆
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

MAX_FACTS = 5
MAX_OPINIONS = 3
MAX_EVIDENCE = 3
TOPIC_CHARS = 60

CATEGORIES: dict[str, tuple[str, ...]] = {
    "记忆系统": ("记忆", "memory", "obsidian", "everos", "知识库", "rag", "召回", "向量"),
    "AI 工具": ("agent", "ai", "llm", "claude", "gpt", "模型", "prompt", "mcp", "自动化"),
    "内容创作": ("内容", "选题", "hook", "thread", "写作", "文案", "涨粉", "创作", "自媒体"),
    "平台运营": ("小红书", "抖音", "b站", "公众号", "微博", "twitter", "发布", "排期", "运营"),
    "数据增长": ("互动率", "分析", "数据", "转化", "engagement", "analytics", "增长", "指标"),
}
"""分类关键词表：命中最多者胜，全不中归入「未分类」。可由调用方扩展。"""

OPINION_SIGNAL = ("建议", "应该", "最好", "值得", "不如", "推荐", "认为", "观点", "似乎", "可能", "个人觉得")

NUMBER_LINE = re.compile(r"\d")
MEASURE_HINT = re.compile(r"[%％万亿]|条|个|次|天|年|月|日|份|小时|分钟|20\d\d")


@dataclass
class TopicCandidate:
    """一个候选选题：主题 + 分类 + 来源 + 证据 + 抽出来的事实/观点。"""

    topic: str
    category: str
    sources: list[str] = field(default_factory=list)
    evidence: list[dict[str, str]] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    opinions: list[str] = field(default_factory=list)
    freshness: str = ""
    confidence: str = "LOW"
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify(text: str) -> str:
    """按关键词表给材料打分类标签。"""
    lowered = text.lower()
    scores = {
        category: sum(lowered.count(word.lower()) for word in words)
        for category, words in CATEGORIES.items()
    }
    best = max(scores, key=lambda name: scores[name])
    return best if scores[best] > 0 else "未分类"


def extract(item: Mapping[str, Any]) -> dict[str, list[Any]]:
    """规则式抽取：带数字的行=事实线索，建议词的行=观点，URL+摘录=证据。"""
    url = str(item.get("url") or "")
    lines = [_clean(line) for line in str(item.get("content") or "").splitlines()]
    lines = [line for line in lines if len(line) >= 8]

    facts = [line for line in lines if NUMBER_LINE.search(line) and MEASURE_HINT.search(line)][:MAX_FACTS]
    opinions = [line for line in lines if _is_opinion(line)][:MAX_OPINIONS]

    evidence = []
    if url:
        if facts:
            # 摘录要能支撑事实：不然事实核查永远「无出处」
            quote = "；".join(facts)
        else:
            quote = lines[0][:80] if lines else str(item.get("title") or "")[:80]
        evidence.append({"url": url, "quote": quote})
    return {"facts": facts, "opinions": opinions, "evidence": evidence[:MAX_EVIDENCE]}


def build_candidates(
    items: Iterable[Mapping[str, Any]],
    extractor: Callable[[Mapping[str, Any]], dict[str, list[Any]]] | None = None,
) -> list[TopicCandidate]:
    """把材料按主题合并成候选选题；同标题的不同来源合并到同一候选。"""
    extract_one = extractor or extract
    grouped: dict[str, TopicCandidate] = {}

    for item in items:
        title = str(item.get("title") or "").strip() or str(item.get("url") or "未命名材料")
        key = _topic_key(title)
        url = str(item.get("url") or "")
        extracted = extract_one(item) or {"facts": [], "opinions": [], "evidence": []}

        candidate = grouped.get(key)
        if candidate is None:
            candidate = TopicCandidate(
                topic=title[:TOPIC_CHARS],
                category=classify(f"{title} {item.get('content', '')}"),
                freshness=_date(str(item.get("timestamp") or "")) or _date(str(item.get("fetched_at") or "")),
            )
            grouped[key] = candidate

        if url and url not in candidate.sources:
            candidate.sources.append(url)
        for quote in extracted.get("evidence", []):
            if quote not in candidate.evidence and len(candidate.evidence) < MAX_EVIDENCE:
                candidate.evidence.append(quote)
        for fact in extracted.get("facts", []):
            if fact not in candidate.facts and len(candidate.facts) < MAX_FACTS:
                candidate.facts.append(fact)
        for opinion in extracted.get("opinions", []):
            if opinion not in candidate.opinions and len(candidate.opinions) < MAX_OPINIONS:
                candidate.opinions.append(opinion)
        candidate.freshness = max(candidate.freshness, _date(str(item.get("timestamp") or "")))

    return sorted(grouped.values(), key=lambda item: (-len(item.sources), item.topic))


def dedupe_items(items: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """按 URL 去重（同一地址只算一次）；同标题的不同来源留给 build_candidates 合并。"""
    seen_url: set[str] = set()
    result = []
    for item in items:
        url = str(item.get("url") or "")
        if url and url in seen_url:
            continue
        if url:
            seen_url.add(url)
        result.append(item)
    return result


DATE_PATTERN = re.compile(r"20\d\d-\d\d-\d\d")


def _date(value: str) -> str:
    """从时间字段里取 YYYY-MM-DD；取不到（如 "N/A"）返回空串，不当作日期。"""
    match = DATE_PATTERN.search(value or "")
    return match.group(0) if match else ""


def _topic_key(title: str) -> str:
    return re.sub(r"\s+", "", title).lower()


def _clean(line: str) -> str:
    return re.sub(r"^[|\-*>#\s]+|[|\s]+$", "", line).strip()


def _is_opinion(line: str) -> bool:
    return any(signal in line for signal in OPINION_SIGNAL)
