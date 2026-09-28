"""Phase 8：ContentObject——CreatorOS 最重要的数据结构之一。

一条内容从 IDEA 到 ARCHIVED 的全生命周期载体：
    topic / angle / audience / sources / evidence / claims / hook / coreContent /
    media / platformVersions / status

边界：
    这是「生产管线数据」，存 SQLite（ContentStore）；不是长期记忆，不进 Obsidian
    想长期复用的结论走 Memory（11-Research / 17-Insights）
    状态只能沿状态机前进，跳步或缺字段一律拒绝——避免没有证据就 APPROVED
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Mapping

STATUSES: tuple[str, ...] = (
    "IDEA",
    "RESEARCHED",
    "DRAFT",
    "REVIEW",
    "APPROVED",
    "SCHEDULED",
    "PUBLISHED",
    "ARCHIVED",
)

TRANSITIONS: dict[str, tuple[str, ...]] = {
    "IDEA": ("RESEARCHED", "ARCHIVED"),
    "RESEARCHED": ("DRAFT", "ARCHIVED"),
    "DRAFT": ("REVIEW", "ARCHIVED"),
    "REVIEW": ("APPROVED", "DRAFT", "ARCHIVED"),
    "APPROVED": ("SCHEDULED", "ARCHIVED"),
    "SCHEDULED": ("PUBLISHED", "ARCHIVED"),
    "PUBLISHED": ("ARCHIVED",),
    "ARCHIVED": (),
}

REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "RESEARCHED": ("sources", "evidence"),
    "DRAFT": ("hook", "core_content"),
    "SCHEDULED": ("platform_versions",),
    "PUBLISHED": ("platform_versions",),
}
"""进入某状态前必须先补齐的字段：没有证据不能算 RESEARCHED，没有钩子不能进 DRAFT。

REVIEW 不强制 claims：空断言清单 = 无可核查项（观点型内容合法），三道检查在
Content Agent 层完成；但发布前必须有平台版本。
"""

FIELD_LABELS = {
    "sources": "来源",
    "evidence": "证据",
    "hook": "Hook",
    "core_content": "核心内容",
    "platform_versions": "平台版本",
}


@dataclass
class ContentObject:
    """一条内容的完整生命周期记录。"""

    topic: str
    angle: str = ""
    audience: str = ""
    sources: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    claims: list[str] = field(default_factory=list)
    hook: str = ""
    core_content: str = ""
    media: list[str] = field(default_factory=list)
    platform_versions: dict[str, str] = field(default_factory=dict)
    status: str = "IDEA"
    id: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not (self.topic or "").strip():
            raise ValueError("ContentObject 必须有 topic。")
        if self.status not in STATUSES:
            raise ValueError(f"非法状态：{self.status}；只能是 {'/'.join(STATUSES)}")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
        if not self.id:
            self.id = uuid.uuid4().hex[:12]

    # ── 状态机 ──────────────────────────────────────────────────────────

    def allowed_transitions(self) -> tuple[str, ...]:
        return TRANSITIONS[self.status]

    def missing_fields(self, target: str) -> list[str]:
        """进入 target 前缺失的必填字段（英文字段名）。"""
        missing = []
        for name in REQUIRED_FIELDS.get(target, ()):
            value = getattr(self, name)
            if not value:
                missing.append(name)
        return missing

    def transition(self, target: str) -> None:
        """推进状态；非法跳步或缺字段抛 ValueError，对象保持原状态。"""
        if target not in STATUSES:
            raise ValueError(f"非法状态：{target}；只能是 {'/'.join(STATUSES)}")
        if target == self.status:
            return
        if target not in TRANSITIONS[self.status]:
            raise ValueError(
                f"状态机不允许 {self.status} → {target}；"
                f"可选：{'/'.join(TRANSITIONS[self.status]) or '（终态，无去向）'}"
            )
        missing = self.missing_fields(target)
        if missing:
            labels = "、".join(FIELD_LABELS.get(name, name) for name in missing)
            raise ValueError(f"进入 {target} 前必须补齐：{labels}（字段 {'/'.join(missing)} 为空）。")
        self.status = target
        self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def fill(self, fields: Mapping[str, Any]) -> None:
        """补齐/更新内容字段（不能改 status：状态只能走 transition）。"""
        updatable = {
            "topic", "angle", "audience", "sources", "evidence", "claims",
            "hook", "core_content", "media", "platform_versions",
        }
        unknown = set(fields) - updatable
        if unknown:
            raise ValueError(f"不可更新的字段：{'、'.join(sorted(unknown))}；状态请用 transition()。")
        for name, value in fields.items():
            setattr(self, name, value)
        self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ContentObject":
        known = {field_name for field_name in cls.__dataclass_fields__}
        return cls(**{key: value for key, value in data.items() if key in known})


def idea_from_recommendation(
    recommendation: Mapping[str, Any],
    brief: Mapping[str, Any] | None = None,
) -> ContentObject:
    """把 Topic Engine 的推荐（可选附带 StrategyBrief）落成 IDEA 状态的内容对象。

    facts 是规则式抽出来的「事实线索」，未经核对，所以进 claims（待核查断言），
    等 REVIEW 阶段逐条核查后才算数。
    """
    angles = list(recommendation.get("angles") or [])
    audience = str(recommendation.get("audience") or "")
    if audience == "UNKNOWN" and brief:
        answer = " ".join(str(line) for line in brief.get("answer") or [])
        audience = answer or ""
    return ContentObject(
        topic=str(recommendation.get("topic") or "").strip(),
        angle=angles[0] if angles else "",
        audience=audience,
        sources=list(recommendation.get("sources") or []),
        evidence=list(recommendation.get("evidence") or []),
        claims=list(recommendation.get("facts") or []),
        status="IDEA",
    )
