"""Phase 15：PublishAdapter（发布侧接口层）。

interface PublishAdapter: validate(payload) / publish(payload) / reconcile(query)

- 六个国内平台当前全部 **CONTRACT_ONLY**：真实写 API 不接、不伪造成功，
  publish/reconcile 返回明确的 `NOT_IMPLEMENTED` 错误码；
- MockPublishAdapter 供 Phase 15 测试与端到端流程，同样走完整状态机；
- payload = FormattedPayload（runtime.platform_formatter 的输出，含 fingerprint）。
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from runtime.platform_formatter import FormattedPayload
from runtime.publish_queue import TS

NOT_IMPLEMENTED = "NOT_IMPLEMENTED"

# reconcile(query) 的查询形状（Reconciler 构造）
RECONCILE_QUERY_KEYS = ("fingerprint", "provider_request_id", "window_start", "window_end", "digest")


class PublishAdapter(ABC):
    """发布适配接口：校验 / 发布 / 对账。"""

    platform = ""

    def validate(self, payload: FormattedPayload) -> dict[str, Any]:
        """契约校验（与 Formatter 同源：FormattedPayload.errors 由 SPECS 规则产生）。"""
        return {"ok": bool(payload.valid), "errors": list(payload.errors)}

    @abstractmethod
    def publish(self, payload: FormattedPayload) -> dict[str, Any]:
        """成功 → {"ok": True, "id", "url", "provider_request_id"?}；
        失败 → {"ok": False, "error_code", "error_message", "retry_after"?}。"""

    @abstractmethod
    def reconcile(self, query: Mapping[str, Any]) -> dict[str, Any]:
        """对账 → {"ok": True, "status": "found"|"not_found"|"ambiguous", "post_id"?}。"""


class ContractOnlyAdapter(PublishAdapter):
    """contract-only 实现：只声明契约，绝不假装发布成功。"""

    def publish(self, payload: FormattedPayload) -> dict[str, Any]:
        return {
            "ok": False,
            "error_code": NOT_IMPLEMENTED,
            "error_message": (
                f"{self.platform} 当前为 CONTRACT_ONLY：未接入真实写 API，"
                "不实现真实发布、不伪造成功。"
            ),
        }

    def reconcile(self, query: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "ok": False,
            "error_code": NOT_IMPLEMENTED,
            "error_message": f"{self.platform} 当前为 CONTRACT_ONLY：无平台查询接口，无法对账。",
        }


class XiaohongshuPublishAdapter(ContractOnlyAdapter):
    platform = "xiaohongshu"


class DouyinPublishAdapter(ContractOnlyAdapter):
    platform = "douyin"


class BilibiliPublishAdapter(ContractOnlyAdapter):
    platform = "bilibili"


class WechatMpPublishAdapter(ContractOnlyAdapter):
    platform = "wechat_mp"


class WeiboPublishAdapter(ContractOnlyAdapter):
    platform = "weibo"


class ChannelsPublishAdapter(ContractOnlyAdapter):
    platform = "channels"


PUBLISH_ADAPTERS: dict[str, type[PublishAdapter]] = {
    "xiaohongshu": XiaohongshuPublishAdapter,
    "douyin": DouyinPublishAdapter,
    "bilibili": BilibiliPublishAdapter,
    "wechat_mp": WechatMpPublishAdapter,
    "weibo": WeiboPublishAdapter,
    "channels": ChannelsPublishAdapter,
}


def get_publish_adapter(platform: str) -> PublishAdapter:
    key = (platform or "").strip().lower()
    adapter_cls = PUBLISH_ADAPTERS.get(key)
    if adapter_cls is None:
        raise ValueError(f"未知平台：{platform}；可选：{', '.join(PUBLISH_ADAPTERS)}")
    return adapter_cls()


# ── Mock（测试与端到端流程用） ──────────────────────────────────────────


def payload_digest(payload: FormattedPayload) -> str:
    """内容摘要：canonical JSON 的 sha256（对账匹配用，与 fingerprint 区分口径）。"""
    canon = json.dumps(payload.payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


class MockPublishAdapter(PublishAdapter):
    """可编排的假后端：按 script 返回结果，记录已发记录供 reconcile 匹配。

    - script：按顺序消费的结果 dict（不消费完则默认成功）；
      结果里的 `_actually_posted: True` 模拟「超时但实际已发出」
      （真实世界 opencli 的 TIMEOUT 就是这样）；
    - reconcile_result："auto" 按指纹/请求 id/摘要+时间窗匹配；
      或直接固定 "found" / "not_found" / "ambiguous"。
    """

    def __init__(
        self,
        platform: str = "mock",
        script: list[dict[str, Any]] | None = None,
        reconcile_result: str = "auto",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.platform = platform
        self.script = list(script or [])
        self.reconcile_result = reconcile_result
        self._clock = clock or datetime.now
        self.posts: list[dict[str, Any]] = []
        self.publish_calls: list[dict[str, Any]] = []
        self.reconcile_calls: list[dict[str, Any]] = []
        self._counter = 0

    def publish(self, payload: FormattedPayload) -> dict[str, Any]:
        self.publish_calls.append({"platform": payload.platform, "fingerprint": payload.fingerprint})
        result = dict(self.script.pop(0)) if self.script else {}
        if not result:
            result = {"ok": True}
        actually_posted = bool(result.pop("_actually_posted", False))

        if result.get("ok"):
            self._counter += 1
            post_id = f"mock-{self._counter}"
            self._record(payload, post_id, result.get("provider_request_id", ""))
            return {"ok": True, "id": post_id, "url": f"https://mock/{post_id}",
                    "provider_request_id": post_id}
        if actually_posted:
            self._counter += 1
            post_id = f"mock-{self._counter}"
            self._record(payload, post_id, result.get("provider_request_id", ""))
            result.setdefault("provider_request_id", "")
        return result

    def _record(self, payload: FormattedPayload, post_id: str, provider_request_id: str) -> None:
        self.posts.append({
            "post_id": post_id,
            "fingerprint": payload.fingerprint,
            "digest": payload_digest(payload),
            "provider_request_id": str(provider_request_id or ""),
            "published_at": self._clock().strftime(TS),
        })

    def reconcile(self, query: Mapping[str, Any]) -> dict[str, Any]:
        self.reconcile_calls.append(dict(query))
        if self.reconcile_result != "auto":
            found = self.posts[0]["post_id"] if self.posts else "mock-found"
            return {"ok": True, "status": self.reconcile_result, "post_id": found}

        fingerprint = str(query.get("fingerprint") or "")
        provider_id = str(query.get("provider_request_id") or "")
        digest = str(query.get("digest") or "")
        window_start = str(query.get("window_start") or "")
        window_end = str(query.get("window_end") or "")

        for post in self.posts:
            if provider_id and post["provider_request_id"] == provider_id:
                return {"ok": True, "status": "found", "post_id": post["post_id"],
                        "published_at": post["published_at"]}
            if fingerprint and post["fingerprint"] == fingerprint:
                return {"ok": True, "status": "found", "post_id": post["post_id"],
                        "published_at": post["published_at"]}
        for post in self.posts:
            if digest and post["digest"] == digest:
                if window_start <= post["published_at"] <= window_end:
                    return {"ok": True, "status": "found", "post_id": post["post_id"],
                            "published_at": post["published_at"]}
                return {"ok": True, "status": "ambiguous", "post_id": post["post_id"]}
        return {"ok": True, "status": "not_found"}
