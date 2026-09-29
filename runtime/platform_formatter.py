"""Phase 14：Platform Formatter（CanonicalPost → FormattedPayload）。

不重新研究内容、不复制业务逻辑：
- 内容从哪来、要不要发、发不发得出去，都不归 Formatter 管；
- 每个平台 Formatter 只做**平台特有格式规则**（标签放哪、怎么拆条、字段叫什么）；
- 字段限制/标题要求/媒体要求全部走 platform contract（runtime.platform_adapter.SPECS +
  check_contract），Formatter 不允许自己另立规则；
- X 的 280/20 限制复用 runtime.x_adapter 的 X_POST_LIMIT / X_THREAD_LIMIT。

输出（FormattedPayload）：rendered payload / valid / warnings / validation errors /
metadata / deterministic fingerprint；format() 是纯函数，默认 dry_run=True，
永远不产生平台写操作（写操作只在 Phase 15 的 PublishAdapter 层）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from runtime.canonical_post import CanonicalPost
from runtime.platform_adapter import SPECS, PlatformSpec, check_contract

# ── 输出模型 ────────────────────────────────────────────────────────────


@dataclass
class FormattedPayload:
    """Formatter 的统一输出；fingerprint 只由 platform+payload 决定（跨进程稳定）。"""

    platform: str
    payload: dict[str, Any]          # rendered payload（平台最终字段形状）
    valid: bool
    errors: list[str]               # validation errors（契约校验不过）
    warnings: list[str]             # 平台格式建议（不拦截）
    metadata: dict[str, Any]         # content_id/label/limits/dry_run/preview
    fingerprint: str                 # sha256(platform + canonical json(payload))

    def preview(self) -> str:
        """人类可读预览（审核界面用）；干跑/预览输出，不外发。"""
        return str(self.metadata.get("preview") or "")


def deterministic_fingerprint(platform: str, payload: Mapping[str, Any]) -> str:
    canon = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(f"{platform}\n{canon}".encode()).hexdigest()


# ── 基类 ────────────────────────────────────────────────────────────────


class PlatformFormatter:
    """平台 Formatter 基类：render（平台格式）→ contract_errors（共享契约）→ warnings。"""

    platform = ""
    body_field = "body"  # rendered payload 里承载正文的字段名（X 除外）

    def __init__(self, limits: Mapping[str, int] | None = None) -> None:
        self._limits = dict(limits or {})

    @property
    def spec(self) -> PlatformSpec:
        return SPECS[self.platform]

    @property
    def label(self) -> str:
        return self.spec.label if self.platform in SPECS else self.platform.upper()

    @property
    def limits(self) -> dict[str, int]:
        merged = dict(self.spec.limits) if self.platform in SPECS else {}
        merged.update(self._limits)
        return merged

    # ── 平台特有部分（子类实现） ──────────────────────────────────────────

    def render(self, post: CanonicalPost) -> dict[str, Any]:
        raise NotImplementedError

    def warnings_for(self, post: CanonicalPost, rendered: Mapping[str, Any]) -> list[str]:
        return []

    def preview_text(self, post: CanonicalPost, rendered: Mapping[str, Any]) -> str:
        lines = [f"【{self.label}】"]
        if rendered.get("title"):
            lines.append(f"标题：{rendered['title']}")
        body = str(rendered.get(self.body_field) or "")
        lines.append(f"正文：{body}")
        if post.media:
            lines.append(f"媒体：{', '.join(post.media)}")
        if post.links:
            lines.append(f"来源：{', '.join(post.links)}")
        return "\n".join(lines)

    # ── 共享部分（不许子类另写一套规则） ──────────────────────────────────

    def contract_errors(self, post: CanonicalPost, rendered: Mapping[str, Any]) -> list[str]:
        return check_contract(
            self.spec,
            title=str(rendered.get("title") or ""),
            body=str(rendered.get(self.body_field) or ""),
            tags=post.tags,
            media=post.media,
            limits=self._limits,
        )

    def format(self, post: CanonicalPost, dry_run: bool = True) -> FormattedPayload:
        """纯函数：渲染 + 校验 + 指纹。dry_run 恒为 True 语义（本层无写操作）。"""
        rendered = self.render(post)
        errors = self.contract_errors(post, rendered)
        warnings = self.warnings_for(post, rendered)
        metadata = {
            "content_id": post.content_id,
            "label": self.label,
            "limits": dict(self.limits),
            "dry_run": bool(dry_run),
            "preview": self.preview_text(post, rendered),
        }
        return FormattedPayload(
            platform=self.platform,
            payload=rendered,
            valid=not errors,
            errors=errors,
            warnings=warnings,
            metadata=metadata,
            fingerprint=deterministic_fingerprint(self.platform, rendered),
        )


# ── X：Thread 拆条（复用 XAdapter 的 280/20 契约常量） ──────────────────


def _is_wide(ch: str) -> bool:
    """X 计费宽度：CJK 等全角字符按 2 计（官方规则），其余按 1。"""
    code = ord(ch)
    return (
        0x1100 <= code <= 0x115F
        or 0x2E80 <= code <= 0x303E
        or 0x3041 <= code <= 0x33FF
        or 0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xA000 <= code <= 0xA4CF
        or 0xAC00 <= code <= 0xD7A3
        or 0xF900 <= code <= 0xFAFF
        or 0xFE30 <= code <= 0xFE6F
        or 0xFF00 <= code <= 0xFF60
        or 0xFFE0 <= code <= 0xFFE6
        or 0x20000 <= code <= 0x3FFFD
    )


def x_weight(text: str) -> int:
    return sum(2 if _is_wide(ch) else 1 for ch in text)


class XFormatter(PlatformFormatter):
    """X → Thread：按 280 权重贪心拆条，行边界优先。"""

    platform = "x"

    def render(self, post: CanonicalPost) -> dict[str, Any]:
        from runtime.x_adapter import X_POST_LIMIT

        full = post.body
        if post.tags:
            full = f"{full}\n\n{' '.join(f'#{tag}' for tag in post.tags)}"
        return {"posts": _split_x(full, X_POST_LIMIT)}

    def contract_errors(self, post: CanonicalPost, rendered: Mapping[str, Any]) -> list[str]:
        from runtime.x_adapter import X_POST_LIMIT, X_THREAD_LIMIT

        posts = list(rendered.get("posts") or [])
        errors: list[str] = []
        if not posts:
            errors.append("正文为空。")
        if len(posts) > X_THREAD_LIMIT:
            errors.append(f"Thread 过长：{len(posts)} > {X_THREAD_LIMIT}。")
        for index, chunk in enumerate(posts, 1):
            weight = x_weight(chunk)
            if weight > X_POST_LIMIT:
                errors.append(f"第 {index} 条超长：权重 {weight} > {X_POST_LIMIT}。")
        return errors

    def warnings_for(self, post: CanonicalPost, rendered: Mapping[str, Any]) -> list[str]:
        return []

    def preview_text(self, post: CanonicalPost, rendered: Mapping[str, Any]) -> str:
        posts = list(rendered.get("posts") or [])
        head = f"【X Thread · {len(posts)} 条】" if len(posts) > 1 else "【X】"
        parts = [f"{head}（第 {i} 条，权重 {x_weight(chunk)}）\n{chunk}"
                 for i, chunk in enumerate(posts, 1)]
        if post.links:
            parts.append(f"来源：{', '.join(post.links)}")
        return "\n".join(parts)


def _split_x(text: str, limit: int) -> list[str]:
    """确定性拆条：按行优先，单行超限再按字符贪心切。"""
    chunks: list[str] = []
    buffer = ""
    for line in text.split("\n"):
        candidate = line if not buffer else f"{buffer}\n{line}"
        if x_weight(candidate) <= limit:
            buffer = candidate
            continue
        if buffer:
            chunks.append(buffer)
            buffer = ""
        if x_weight(line) <= limit:
            buffer = line
            continue
        current = ""
        for ch in line:
            if x_weight(current + ch) > limit:
                chunks.append(current)
                current = ch
            else:
                current += ch
        buffer = current
    if buffer:
        chunks.append(buffer)
    return [chunk for chunk in chunks if chunk.strip()]


# ── 六个国内平台 ────────────────────────────────────────────────────────


def _hashtags(tags: list[str], with_hash: bool = True) -> list[str]:
    return [f"#{tag}" if with_hash else tag for tag in tags]


class XiaohongshuFormatter(PlatformFormatter):
    """小红书：标签写进正文末尾（#话题 形式），图文建议配图。"""

    platform = "xiaohongshu"
    body_field = "body"

    def render(self, post: CanonicalPost) -> dict[str, Any]:
        body = post.body
        hashtags = _hashtags(post.tags)
        if hashtags:
            body = f"{body}\n{' '.join(hashtags)}"
        return {"title": post.title, "body": body, "hashtags": hashtags}

    def warnings_for(self, post: CanonicalPost, rendered: Mapping[str, Any]) -> list[str]:
        warnings: list[str] = []
        if not post.media:
            warnings.append("小红书是图文平台，建议配图。")
        if not post.tags:
            warnings.append("建议至少带 1 个话题标签。")
        return warnings


class DouyinFormatter(PlatformFormatter):
    """抖音：无独立标题，文案即正文；必须有视频。"""

    platform = "douyin"
    body_field = "caption"

    def render(self, post: CanonicalPost) -> dict[str, Any]:
        caption = post.body
        hashtags = _hashtags(post.tags)
        if hashtags:
            caption = f"{caption}\n{' '.join(hashtags)}"
        return {
            "caption": caption,
            "video": post.media[0] if post.media else "",
            "hashtags": hashtags,
        }

    def warnings_for(self, post: CanonicalPost, rendered: Mapping[str, Any]) -> list[str]:
        warnings: list[str] = []
        if not post.tags:
            warnings.append("建议带话题标签提高分发。")
        if len(post.body) < 20:
            warnings.append("文案偏短（少于 20 字）。")
        return warnings


class BilibiliFormatter(PlatformFormatter):
    """B站：标题 + 简介分离，标签放 tags 字段；必须有视频。"""

    platform = "bilibili"
    body_field = "description"

    def render(self, post: CanonicalPost) -> dict[str, Any]:
        return {
            "title": post.title,
            "description": post.body,
            "video": post.media[0] if post.media else "",
            "tags": list(post.tags),
        }

    def warnings_for(self, post: CanonicalPost, rendered: Mapping[str, Any]) -> list[str]:
        warnings: list[str] = []
        if not post.tags:
            warnings.append("建议填写分区/标签。")
        if post.title and len(post.title) < 5:
            warnings.append("标题偏短（少于 5 字）。")
        return warnings


class WechatMpFormatter(PlatformFormatter):
    """公众号：标题 + 正文分离；封面只提示不拦截。"""

    platform = "wechat_mp"
    body_field = "content"

    def render(self, post: CanonicalPost) -> dict[str, Any]:
        return {
            "title": post.title,
            "content": post.body,
            "cover": post.media[0] if post.media else "",
        }

    def warnings_for(self, post: CanonicalPost, rendered: Mapping[str, Any]) -> list[str]:
        warnings: list[str] = []
        if not post.media:
            warnings.append("公众号群发需要封面图（本地仅提示，不拦截）。")
        if post.links:
            warnings.append(f"来源链接需在编辑器中人工确认：{', '.join(post.links)}")
        return warnings


class WeiboFormatter(PlatformFormatter):
    """微博：话题写进正文，超 140 字提示折叠（契约上限仍按 SPECS 2000）。"""

    platform = "weibo"
    body_field = "text"

    def render(self, post: CanonicalPost) -> dict[str, Any]:
        text = post.body
        hashtags = _hashtags(post.tags)
        if hashtags:
            text = f"{text}\n{' '.join(hashtags)}"
        return {"text": text, "hashtags": hashtags}

    def warnings_for(self, post: CanonicalPost, rendered: Mapping[str, Any]) -> list[str]:
        warnings: list[str] = []
        if len(str(rendered.get("text") or "")) > 140:
            warnings.append("正文超 140 字，发布后将折叠为长文（仅提示）。")
        if not post.tags:
            warnings.append("建议带 #话题# 提高分发。")
        return warnings


class ChannelsFormatter(PlatformFormatter):
    """视频号：标题 + 简短描述 + 视频；必须有视频。"""

    platform = "channels"
    body_field = "desc"

    def render(self, post: CanonicalPost) -> dict[str, Any]:
        desc = post.body
        hashtags = _hashtags(post.tags)
        if hashtags:
            desc = f"{desc}\n{' '.join(hashtags)}"
        return {
            "title": post.title,
            "desc": desc,
            "video": post.media[0] if post.media else "",
            "hashtags": hashtags,
        }

    def warnings_for(self, post: CanonicalPost, rendered: Mapping[str, Any]) -> list[str]:
        warnings: list[str] = []
        if not post.tags:
            warnings.append("建议带话题标签。")
        if len(post.body) > 200:
            warnings.append("视频号描述偏长，建议 200 字以内。")
        return warnings


# ── 注册表 ──────────────────────────────────────────────────────────────

FORMATTERS: dict[str, type[PlatformFormatter]] = {
    "x": XFormatter,
    "xiaohongshu": XiaohongshuFormatter,
    "douyin": DouyinFormatter,
    "bilibili": BilibiliFormatter,
    "wechat_mp": WechatMpFormatter,
    "weibo": WeiboFormatter,
    "channels": ChannelsFormatter,
}


def get_formatter(platform: str, **kwargs: Any) -> PlatformFormatter:
    key = (platform or "").strip().lower()
    formatter_cls = FORMATTERS.get(key)
    if formatter_cls is None:
        raise ValueError(f"未知平台：{platform}；可选：{', '.join(FORMATTERS)}")
    return formatter_cls(**kwargs)
