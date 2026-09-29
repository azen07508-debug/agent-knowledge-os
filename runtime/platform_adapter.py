"""Phase 13：国内平台统一适配层（小红书/抖音/B站/公众号/微博/视频号）。

PLAN 接口 → 代码（snake_case，与 XAdapter 一致）：
    createDraft → create_draft()    validate()    publish()
    schedule()   getStatus → get_status()          getAnalytics → get_analytics()

约定（与 XAdapter 同一套）：
- 六个平台先立契约：create_draft / validate / publish(dry_run=True) 本地全可跑；
- 真实 publish / schedule / getStatus / getAnalytics 必须注入 backend，
  没配就如实返回 ok=False + 明确提示，不假装成功；
- backend 契约：同名方法返回 {"ok": ...}；
- 标题/正文字数上限是本地规则常量（可被 limits 覆盖），平台改版时改这里。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

# ── 平台规格 ────────────────────────────────────────────────────────────
# limits 里 0 = 不限制；tag_max 按标签个数字面计。


@dataclass(frozen=True)
class PlatformSpec:
    key: str
    label: str
    limits: Mapping[str, int]
    requires_title: bool
    requires_media: bool  # 视频平台必须有媒体文件


SPECS: dict[str, PlatformSpec] = {
    "xiaohongshu": PlatformSpec("xiaohongshu", "小红书",
                                {"title_max": 20, "body_max": 1000, "tag_max": 10},
                                requires_title=True, requires_media=False),
    "douyin": PlatformSpec("douyin", "抖音",
                           {"title_max": 0, "body_max": 1000, "tag_max": 10},
                           requires_title=False, requires_media=True),
    "bilibili": PlatformSpec("bilibili", "B站",
                             {"title_max": 80, "body_max": 2000, "tag_max": 12},
                             requires_title=True, requires_media=True),
    "wechat_mp": PlatformSpec("wechat_mp", "公众号",
                              {"title_max": 64, "body_max": 0, "tag_max": 0},
                              requires_title=True, requires_media=False),
    "weibo": PlatformSpec("weibo", "微博",
                          {"title_max": 0, "body_max": 2000, "tag_max": 10},
                          requires_title=False, requires_media=False),
    "channels": PlatformSpec("channels", "视频号",
                             {"title_max": 20, "body_max": 1000, "tag_max": 10},
                             requires_title=True, requires_media=True),
}


@dataclass
class Draft:
    """平台草稿（Phase 15 PublishJob 会持有它排队，Phase 14 Formatter 负责产出它的字段）。"""

    platform: str
    title: str = ""
    body: str = ""
    tags: list[str] = field(default_factory=list)
    media: list[str] = field(default_factory=list)
    content_id: str = ""  # 关联的 ContentObject id
    status: str = "DRAFT"  # DRAFT → PUBLISHED（平台侧状态查询走 get_status）
    id: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = uuid4().hex[:12]
        if not self.created_at:
            self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def check_contract(
    spec: PlatformSpec,
    *,
    title: str,
    body: str,
    tags: list[str] | tuple[str, ...],
    media: list[str] | tuple[str, ...],
    limits: Mapping[str, int] | None = None,
) -> list[str]:
    """按平台契约（SPECS）校验字段，返回错误列表（空 = 通过）。

    这是全项目唯一的平台规则实现：PlatformAdapter.validate 和
    PlatformFormatter 都调它，不允许各自再写一套。
    """
    merged = dict(spec.limits)
    merged.update(limits or {})

    errors: list[str] = []
    if not (body or "").strip():
        errors.append("正文为空。")
    if spec.requires_title and not (title or "").strip():
        errors.append(f"{spec.label}需要标题。")
    title_max = merged.get("title_max", 0)
    if title_max and len(title or "") > title_max:
        errors.append(f"标题 {len(title or '')} 字，超过 {spec.label} 上限 {title_max} 字。")
    body_max = merged.get("body_max", 0)
    if body_max and len(body or "") > body_max:
        errors.append(f"正文 {len(body or '')} 字，超过 {spec.label} 上限 {body_max} 字。")
    tag_max = merged.get("tag_max", 0)
    if tag_max and len(tags) > tag_max:
        errors.append(f"标签 {len(tags)} 个，超过 {spec.label} 上限 {tag_max} 个。")
    if spec.requires_media and not media:
        errors.append(f"{spec.label}是视频平台，必须有媒体文件。")
    return errors


# ── 基类 ────────────────────────────────────────────────────────────────


class PlatformAdapter:
    """六接口基类；子类只声明 platform 与后端缺失提示。"""

    platform = ""
    backend_hint = "尚未接入平台后端，注入 backend=…() 后才允许真实操作。"

    def __init__(self, backend: Any | None = None, limits: Mapping[str, int] | None = None) -> None:
        self.backend = backend
        self._limits = dict(limits or {})

    # ── 元信息 ────────────────────────────────────────────────────────────

    @property
    def spec(self) -> PlatformSpec:
        return SPECS[self.platform]

    @property
    def label(self) -> str:
        return self.spec.label

    @property
    def limits(self) -> dict[str, int]:
        merged = dict(self.spec.limits)
        merged.update(self._limits)
        return merged

    # ── createDraft ───────────────────────────────────────────────────────

    def create_draft(self, content: Mapping[str, Any]) -> Draft:
        """把内容映射（title/topic/body 或 core_content/tags/media）落成平台草稿。"""
        body = str(content.get("body") or content.get("core_content") or "").strip()
        if not body:
            raise ValueError(f"{self.label}草稿必须有正文。")
        title = str(content.get("title") or content.get("topic") or "").strip()
        tags = [str(tag).strip().lstrip("#") for tag in content.get("tags") or [] if str(tag).strip()]
        media = [str(item).strip() for item in content.get("media") or [] if str(item).strip()]
        return Draft(
            platform=self.platform,
            title=title,
            body=body,
            tags=[tag for tag in tags if tag],
            media=media,
            content_id=str(content.get("content_id") or ""),
        )

    # ── validate ──────────────────────────────────────────────────────────

    def validate(self, draft: Draft) -> dict[str, Any]:
        """平台规则校验；errors 为空才允许真实发布。"""
        errors: list[str] = []
        if draft.platform != self.platform:
            errors.append(f"平台不符：草稿是 {draft.platform}，适配器是 {self.platform}。")
        errors += check_contract(
            self.spec,
            title=draft.title,
            body=draft.body,
            tags=draft.tags,
            media=draft.media,
            limits=self._limits,
        )
        return {"ok": not errors, "platform": self.platform, "errors": errors}

    # ── publish / schedule ────────────────────────────────────────────────

    def publish(self, draft: Draft, dry_run: bool = True) -> dict[str, Any]:
        checked = self.validate(draft)
        if not checked["ok"]:
            return {
                "ok": False,
                "action": "publish",
                "platform": self.platform,
                "message": "校验未通过，不发布。",
                "errors": checked["errors"],
            }
        if dry_run:
            return {
                "ok": True,
                "action": "publish",
                "platform": self.platform,
                "dry_run": True,
                "preview": {"title": draft.title, "body": draft.body, "tags": list(draft.tags)},
            }
        called = self._backend_call("publish", {"draft": draft})
        if not called.get("ok"):
            return {"action": "publish", "platform": self.platform, "dry_run": False, **called}
        draft.status = "PUBLISHED"
        return {
            "ok": True,
            "action": "publish",
            "platform": self.platform,
            "dry_run": False,
            "id": str(called.get("id") or ""),
            "url": str(called.get("url") or ""),
        }

    def schedule(self, draft: Draft, at: str, dry_run: bool = True) -> dict[str, Any]:
        checked = self.validate(draft)
        if not checked["ok"]:
            return {
                "ok": False,
                "action": "schedule",
                "platform": self.platform,
                "message": "校验未通过，不定时。",
                "errors": checked["errors"],
            }
        if dry_run:
            return {
                "ok": True,
                "action": "schedule",
                "platform": self.platform,
                "dry_run": True,
                "at": at,
                "preview": {"title": draft.title, "body": draft.body},
            }
        called = self._backend_call("schedule", {"draft": draft, "at": at})
        if not called.get("ok"):
            return {"action": "schedule", "platform": self.platform, "dry_run": False, **called}
        return {"ok": True, "action": "schedule", "platform": self.platform, "dry_run": False, "at": at}

    # ── getStatus / getAnalytics ──────────────────────────────────────────

    def get_status(self, draft_id: str) -> dict[str, Any]:
        return self._backend_call("get_status", {"draft_id": draft_id},
                                  action="get_status")

    def get_analytics(self, draft_id: str) -> dict[str, Any]:
        return self._backend_call("get_analytics", {"draft_id": draft_id},
                                  action="get_analytics")

    # ── backend 调用 ──────────────────────────────────────────────────────

    def _backend_call(self, method: str, params: Mapping[str, Any], action: str | None = None) -> dict[str, Any]:
        if self.backend is None:
            return {
                "ok": False,
                "action": action or method,
                "platform": self.platform,
                "message": f"{self.label}后端未配置：{self.backend_hint}",
            }
        handler = getattr(self.backend, method, None)
        if handler is None:
            return {
                "ok": False,
                "action": action or method,
                "platform": self.platform,
                "message": f"{self.label}后端没有 {method} 方法。",
            }
        try:
            result = handler(**params)
        except Exception as exc:  # 后端异常 -> 可解释失败，不假装成功
            return {
                "ok": False,
                "action": action or method,
                "platform": self.platform,
                "message": f"{self.label}后端调用失败：{exc}",
            }
        if not isinstance(result, Mapping) or "ok" not in result:
            return {
                "ok": False,
                "action": action or method,
                "platform": self.platform,
                "message": f"{self.label}后端返回不符合契约（需要含 ok 字段的 dict）。",
            }
        return dict(result)


# ── 六个平台 ────────────────────────────────────────────────────────────


class XiaohongshuAdapter(PlatformAdapter):
    platform = "xiaohongshu"
    backend_hint = "可接 OpenCLI（opencli xiaohongshu，只读已验证）或 xhs-cli；写操作接入前先人工确认。"


class DouyinAdapter(PlatformAdapter):
    platform = "douyin"
    backend_hint = "本机尚无抖音后端（开放平台凭据未配）。"


class BilibiliAdapter(PlatformAdapter):
    platform = "bilibili"
    backend_hint = "bili-cli / OpenCLI 只覆盖搜索与读取，投稿（upload）未接入。"


class WechatMpAdapter(PlatformAdapter):
    platform = "wechat_mp"
    backend_hint = "公众号需要 app_id/app_secret 的草稿箱/发布 API，凭据未配。"


class WeiboAdapter(PlatformAdapter):
    platform = "weibo"
    backend_hint = "微博需要开放平台 access_token，凭据未配。"


class ChannelsAdapter(PlatformAdapter):
    platform = "channels"
    backend_hint = "视频号暂无 CLI/API 后端，只能手工发布。"


ADAPTERS: dict[str, type[PlatformAdapter]] = {
    "xiaohongshu": XiaohongshuAdapter,
    "douyin": DouyinAdapter,
    "bilibili": BilibiliAdapter,
    "wechat_mp": WechatMpAdapter,
    "weibo": WeiboAdapter,
    "channels": ChannelsAdapter,
}


def get_adapter(platform: str, **kwargs: Any) -> PlatformAdapter:
    """按平台 key 取适配器；未知平台报错并列出可选项。"""
    key = (platform or "").strip().lower()
    adapter_cls = ADAPTERS.get(key)
    if adapter_cls is None:
        raise ValueError(f"未知平台：{platform}；可选：{', '.join(SPECS)}")
    return adapter_cls(**kwargs)
