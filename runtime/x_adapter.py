"""Phase 10：X Layer——所有 X API 逻辑只允许出现在这个文件（PLAN Phase 10）。

边界：
    后端可注入（x-mcp / agent-reach 的 X 渠道装好后接进来）；未配置时所有调用
    返回 ok=False + 明确提示，不猜、不假装成功
    默认 dry_run=True：post / thread / schedule 只回显内容、不真实发送；
    真实发送必须显式 dry_run=False（对外操作，由上层把关）
    读接口（search / timeline / mentions / analytics）不受 dry_run 影响
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

X_POST_LIMIT = 280
X_THREAD_LIMIT = 20


def normalize_post_text(text: str) -> str:
    """把外部脚本常见的字面量转义符转换为真正的排版换行。"""
    return str(text).replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")


def validate_thread_sequence(posts: Sequence[str]) -> list[str]:
    """发布前去重并拒绝空帖/字面量转义，避免评论重复根帖内容。"""
    normalized = [normalize_post_text(str(post)).strip() for post in posts]
    if any(not post for post in normalized):
        raise ValueError("Thread 含空帖：有一条内容为空")
    if len(normalized) > X_THREAD_LIMIT:
        raise ValueError(f"Thread 过长：{len(normalized)} > {X_THREAD_LIMIT}。")
    if any("\\n" in post or "\\t" in post for post in normalized):
        raise ValueError("Thread 含字面量转义符号，必须使用真实换行")
    seen: set[str] = set()
    unique: list[str] = []
    for post in normalized:
        key = " ".join(post.split())
        if key in seen:
            raise ValueError("Thread 含重复段落，不发送重复内容")
        seen.add(key)
        unique.append(post)
    return unique

NOT_CONFIGURED = "X 后端未配置：装好 x-mcp 或 agent-reach 的 X 渠道后注入 backend=XxxBackend()。"
BACKEND_CONTRACT = (
    "backend 需提供同名方法 search/timeline/mentions/post/schedule/analytics，"
    "返回 dict 且含 ok 字段（读接口的 items 含 url/author/text/time）。"
)


class XAdapter:
    """X 的读写入口：Post / Thread / Search / Timeline / Mentions / Schedule / Analytics。"""

    def __init__(self, backend: Any | None = None, dry_run: bool = True) -> None:
        self.backend = backend
        self.dry_run = dry_run

    @property
    def configured(self) -> bool:
        return self.backend is not None

    # ── 读 ──────────────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 10) -> dict[str, Any]:
        return self._read("search", query=query, limit=limit)

    def timeline(self, limit: int = 20) -> dict[str, Any]:
        return self._read("timeline", limit=limit)

    def mentions(self, limit: int = 20) -> dict[str, Any]:
        return self._read("mentions", limit=limit)

    def analytics(self, post_id: str) -> dict[str, Any]:
        if not post_id:
            return {"ok": False, "action": "analytics", "message": "缺少 post_id。"}
        if not self.configured:
            return self._not_configured("analytics")
        return _call(self.backend, "analytics", {"post_id": post_id})

    def delete(self, post_id: str) -> dict[str, Any]:
        """删除自己的推文；OpenCLI 失败时 fallback 到显式凭据的 twitter-cli。"""
        if not str(post_id).isdigit():
            return {"ok": False, "action": "delete", "message": "删除需要纯数字 post_id。"}
        if not self.configured:
            return self._not_configured("delete")
        result = _call(self.backend, "delete", {"post_id": str(post_id)})
        if result.get("ok"):
            return result
        try:
            from runtime.twitter_backend import TwitterCliXBackend
            fallback = TwitterCliXBackend()
            if fallback.available and fallback is not self.backend:
                alternate = fallback.delete(str(post_id))
                if alternate.get("ok"):
                    return {**alternate, "fallback": "twitter-cli"}
                result["fallback_message"] = alternate.get("message", "twitter-cli 删除失败")
        except Exception as exc:
            result["fallback_message"] = f"twitter-cli fallback 异常：{exc}"
        return result

    # ── 写（默认演练） ───────────────────────────────────────────────────

    def post(self, text: str, dry_run: bool | None = None) -> dict[str, Any]:
        text = normalize_post_text(text)
        if not (text or "").strip():
            return {"ok": False, "action": "post", "message": "内容为空，不发空帖。"}
        if len(text) > X_POST_LIMIT:
            return {"ok": False, "action": "post", "message": f"超长：{len(text)} > {X_POST_LIMIT}。"}
        if not self.configured:
            return self._not_configured("post")
        if self._dry(dry_run):
            return {
                "ok": True,
                "action": "post",
                "dry_run": True,
                "text": text,
                "message": "演练：未真实发送。",
            }
        return _call(self.backend, "post", {"text": text})

    def thread(self, posts: Sequence[str], dry_run: bool | None = None) -> dict[str, Any]:
        try:
            posts = validate_thread_sequence(posts)
        except ValueError as exc:
            return {"ok": False, "action": "thread", "message": str(exc)}
        if not posts:
            return {"ok": False, "action": "thread", "message": "Thread 没有内容。"}
        if len(posts) > X_THREAD_LIMIT:
            return {"ok": False, "action": "thread", "message": f"Thread 过长：{len(posts)} > {X_THREAD_LIMIT}。"}
        for index, post in enumerate(posts, start=1):
            if not post.strip():
                return {"ok": False, "action": "thread", "message": f"第 {index} 条为空。"}
            if len(post) > X_POST_LIMIT:
                return {"ok": False, "action": "thread", "message": f"第 {index} 条超长：{len(post)} > {X_POST_LIMIT}。"}
        if not self.configured:
            return self._not_configured("thread")
        if self._dry(dry_run):
            return {
                "ok": True,
                "action": "thread",
                "dry_run": True,
                "posts": posts,
                "ids": [],
                "message": "演练：未真实发送。",
            }

        ids: list[str] = []
        for index, post in enumerate(posts, start=1):
            result = _call(self.backend, "post", {"text": post})
            if not result.get("ok"):
                return {
                    "ok": False,
                    "action": "thread",
                    "posted": len(ids),
                    "ids": ids,
                    "error_code": result.get("error_code", ""),
                    "provider_request_id": result.get("provider_request_id", ""),
                    "message": f"第 {index}/{len(posts)} 条发送失败：{result.get('message', '未知原因')}",
                }
            post_id = str(result.get("id") or "").strip()
            if not post_id or re.fullmatch(r"#\d+", post_id):
                return {
                    "ok": False,
                    "action": "thread",
                    "posted": len(ids),
                    "ids": ids,
                    "uncertain": True,
                    "error_code": "MISSING_POST_ID",
                    "message": f"第 {index}/{len(posts)} 条返回成功但缺少有效 post_id，结果无法确认。",
                }
            ids.append(post_id)
        return {"ok": True, "action": "thread", "dry_run": False, "posts": posts, "ids": ids}

    def schedule(self, text: str, at: str, dry_run: bool | None = None) -> dict[str, Any]:
        if not (text or "").strip() or not (at or "").strip():
            return {"ok": False, "action": "schedule", "message": "定时发布需要内容和时间。"}
        if not self.configured:
            return self._not_configured("schedule")
        if self._dry(dry_run):
            return {
                "ok": True,
                "action": "schedule",
                "dry_run": True,
                "text": text,
                "at": at,
                "message": "演练：未创建真实定时任务。",
            }
        return _call(self.backend, "schedule", {"text": text, "at": at})

    # ── 内部 ────────────────────────────────────────────────────────────

    def _dry(self, override: bool | None) -> bool:
        return self.dry_run if override is None else override

    def _not_configured(self, action: str) -> dict[str, Any]:
        return {"ok": False, "action": action, "message": NOT_CONFIGURED}

    def _read(self, action: str, **params: Any) -> dict[str, Any]:
        if not self.configured:
            return self._not_configured(action)
        result = _call(self.backend, action, params)
        if not result.get("ok"):
            return result
        items = _normalize_items(result.get("items") or [])
        return {"ok": True, "action": action, "items": items, "count": len(items)}


def default_x_adapter(
    config_path: str | None = None,
    which: Callable[[str], Any] | None = None,
) -> XAdapter:
    """探测可用后端：OpenCLI（浏览器登录态）优先，其次 twitter-cli 凭据；都没有就返回未配置的 adapter（不假装成功）。"""
    from runtime.opencli_x_backend import OpenCliXBackend
    from runtime.twitter_backend import TwitterCliXBackend

    opencli = OpenCliXBackend(which=which) if which else OpenCliXBackend()
    if opencli.available:
        return XAdapter(backend=opencli)
    twitter = TwitterCliXBackend(config_path=config_path) if config_path else TwitterCliXBackend()
    return XAdapter(backend=twitter if twitter.available else None)


def _call(backend: Any, method: str, params: Mapping[str, Any]) -> dict[str, Any]:
    """调后端并兜底：没实现的方法当作未配置，异常转成失败结果，绝不假装成功。"""
    func: Callable[..., Any] | None = getattr(backend, method, None)
    if func is None:
        return {"ok": False, "action": method, "message": f"后端未实现 {method}()。{BACKEND_CONTRACT}"}
    try:
        result = func(**params)
    except Exception as exc:  # 后端异常要变成可解释的失败
        return {"ok": False, "action": method, "message": f"X 后端调用失败：{exc}"}
    if not isinstance(result, Mapping):
        return {"ok": False, "action": method, "message": f"后端 {method}() 返回了 {type(result).__name__}，应为 dict。"}
    data = dict(result)
    data["action"] = method
    if not data.get("ok"):
        data["ok"] = False
        data.setdefault("message", f"后端 {method}() 未返回 ok=True。")
    return data


def _normalize_items(raw: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """统一后端字段差异：只要 url/author/text/time。"""
    items = []
    for item in raw:
        text = str(item.get("text") or item.get("content") or item.get("full_text") or "")
        url = str(item.get("url") or item.get("id_str") or "")
        if not url and not text:
            continue
        items.append(
            {
                "url": url,
                "author": str(item.get("author") or item.get("screen_name") or ""),
                "text": text,
                "time": str(item.get("time") or item.get("created_at") or ""),
            }
        )
    return items
