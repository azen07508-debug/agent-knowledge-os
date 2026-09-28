"""Phase 10：X Layer——所有 X API 逻辑只允许出现在这个文件（PLAN Phase 10）。

边界：
    后端可注入（x-mcp / agent-reach 的 X 渠道装好后接进来）；未配置时所有调用
    返回 ok=False + 明确提示，不猜、不假装成功
    默认 dry_run=True：post / thread / schedule 只回显内容、不真实发送；
    真实发送必须显式 dry_run=False（对外操作，由上层把关）
    读接口（search / timeline / mentions / analytics）不受 dry_run 影响
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

X_POST_LIMIT = 280
X_THREAD_LIMIT = 20

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

    # ── 写（默认演练） ───────────────────────────────────────────────────

    def post(self, text: str, dry_run: bool | None = None) -> dict[str, Any]:
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
        posts = [str(post) for post in posts]
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
                    "message": f"第 {index}/{len(posts)} 条发送失败：{result.get('message', '未知原因')}",
                }
            ids.append(str(result.get("id") or f"#{index}"))
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
    which: "Callable[[str], Any] | None" = None,
) -> "XAdapter":
    """探测可用后端：OpenCLI（浏览器登录态）优先，其次 twitter-cli 凭据；都没有就返回未配置的 adapter（不假装成功）。"""
    from runtime.opencli_x_backend import OpenCliXBackend
    from runtime.twitter_backend import TwitterCliXBackend

    opencli = OpenCliXBackend(**({"which": which} if which else {}))
    if opencli.available:
        return XAdapter(backend=opencli)
    kwargs = {"config_path": config_path} if config_path else {}
    twitter = TwitterCliXBackend(**kwargs)
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
