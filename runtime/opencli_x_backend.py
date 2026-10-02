"""Phase 10 后端实现：OpenCLI（浏览器登录态，复用用户已有的 x.com 会话）。

只做「拼 opencli 命令 + 解析 JSON 输出」；读写语义仍归 XAdapter。
输出解析不了就报失败，不猜；写操作仍由 XAdapter 的 dry_run 把关。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping
from typing import Any

OPENCLI_BIN = "opencli"
NO_SCHEDULE = "opencli 不支持定时发布；定时排期由 Phase 15 PublishJob 承担。"
NOT_LOGGED_IN = "浏览器未登录 x.com：先在 Chrome 里登录 X，或运行 opencli twitter login。"


class OpenCliXBackend:
    """把 X 读写翻译成 `opencli twitter ...` 命令（浏览器登录态）。"""

    def __init__(
        self,
        runner: Callable[..., Any] | None = None,
        opencli_bin: str = OPENCLI_BIN,
        which: Callable[[str], Any] | None = None,
        timeout: int = 120,
    ) -> None:
        self._run = runner or _default_run
        self.opencli_bin = opencli_bin
        self._which = which or shutil.which
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self._which(self.opencli_bin))

    # ── 命令执行 ──────────────────────────────────────────────────────────

    def _call(self, argv: list[str]) -> dict[str, Any]:
        try:
            proc = self._run([self.opencli_bin, *argv], timeout=self.timeout)
        except Exception as exc:  # 后端异常 -> 可解释失败，不假装成功
            return {"ok": False, "message": f"opencli 调用失败：{exc}"}
        stdout = str(getattr(proc, "stdout", "") or "")
        if getattr(proc, "returncode", 1) != 0:
            detail = str(getattr(proc, "stderr", "") or "").strip() or stdout.strip()
            return {"ok": False, "message": f"opencli 退出码 {proc.returncode}：{detail[:300]}"}
        return {"ok": True, "stdout": stdout}

    def _read(self, argv: list[str]) -> dict[str, Any]:
        called = self._call(argv)
        if not called["ok"]:
            return called
        payload = _json(called["stdout"])
        if payload is None:
            return {"ok": False, "message": "opencli 输出不是 JSON（加 -f json 后仍非 JSON，解析不了就不猜）。"}
        items = [item for item in (_normalize(raw) for raw in _rows(payload)) if item]
        return {"ok": True, "items": items}

    # ── XAdapter 需要的六个方法 ──────────────────────────────────────────

    def search(self, query: str, limit: int = 10) -> dict[str, Any]:
        return self._read(["twitter", "search", query, "--limit", str(limit), "-f", "json"])

    def timeline(self, limit: int = 20) -> dict[str, Any]:
        return self._read(["twitter", "timeline", "--limit", str(limit), "-f", "json"])

    def mentions(self, limit: int = 20) -> dict[str, Any]:
        who = self._call(["twitter", "whoami", "-f", "json"])
        if not who["ok"]:
            return who
        payload = _json(who["stdout"])
        if isinstance(payload, Mapping) and payload.get("logged_in") is False:
            return {"ok": False, "message": NOT_LOGGED_IN}
        handle = _handle(payload)
        if not handle:
            return {"ok": False, "message": "whoami 没返回用户名，查不了 Mentions。"}
        return self._read(["twitter", "search", f"@{handle}", "--limit", str(limit), "-f", "json"])

    def post(self, text: str) -> dict[str, Any]:
        called = self._call(["twitter", "post", text, "-f", "json"])
        if not called["ok"]:
            # opencli 超时/导航被拒 ≠ 没发出：以最近时间线对账，找到就认（今天就栽在这）
            return self._find_landed(text) or called
        payload = _json(called["stdout"])
        if payload is None:
            return self._find_landed(text) or {
                "ok": False, "message": "opencli 输出不是 JSON，发布结果无法确认（内容可能已发出，请人工检查）。"}
        raw = payload[0] if isinstance(payload, list) and payload else payload
        if not isinstance(raw, Mapping):
            return {"ok": False, "message": "发布输出结构无法解析（内容可能已发出，请人工检查）。"}
        status = str(raw.get("status") or "").lower()
        if status and status not in ("ok", "success", "posted"):
            return {"ok": False, "message": str(raw.get("message") or f"发布失败：status={status}")}
        return {"ok": True, "id": str(raw.get("id") or ""), "url": str(raw.get("url") or "")}

    def _find_landed(self, text: str) -> dict[str, Any] | None:
        """在最近推文里找刚发的这条；找到返回 ok（附 id/url），没有就返回 None。"""
        rows = self._read(["twitter", "tweets", "--limit", "10", "-f", "json"])
        if not rows.get("ok"):
            return None
        want = _matchable(text)
        for row in list(rows.get("items") or [])[:5]:  # 只认最近几条，不翻旧账
            landed = str(row.get("text") or "")
            if landed and _matchable(landed) == want:
                url = str(row.get("url") or "")
                match = re.search(r"/status/(\d+)", url)
                return {"ok": True, "id": match.group(1) if match else "", "url": url}
        return None

    def schedule(self, text: str, at: str) -> dict[str, Any]:
        return {"ok": False, "message": NO_SCHEDULE}

    def analytics(self, post_id: str) -> dict[str, Any]:
        called = self._call(["twitter", "tweets", "--limit", "100", "-f", "json"])
        if not called["ok"]:
            return called
        payload = _json(called["stdout"])
        if payload is None:
            return {"ok": False, "message": "opencli 输出不是 JSON，解析不了互动指标。"}
        target = _find_row(payload, post_id)
        if target is None:
            return {"ok": False, "message": f"自己最近 100 条推文里没有 {post_id}（可能太旧或已被删除）。"}
        metrics = _metrics(target)
        if not metrics:
            return {"ok": False, "message": "该推文数据里没有互动指标。"}
        return {
            "ok": True,
            "metrics": metrics,
            "is_retweet": _is_retweet(target),
            "publish_time": str(target.get("created_at") or ""),
        }


def _is_retweet(row: Mapping[str, Any]) -> bool:
    """转发行的互动指标属于原作者，不算自己内容的表现（Phase 16 归属判定）。"""
    if isinstance(row.get("is_retweet"), bool):
        return row["is_retweet"]
    text = str(row.get("text") or row.get("full_text") or "")
    return text.startswith("RT @")


def _default_run(argv: list[str], timeout: int):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


# ── 输出解析（容忍字段差异，解析不了就返回空而不是编造） ────────────────


def _json(stdout: str) -> Any | None:
    try:
        return json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return None


def _rows(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("tweets", "results", "data", "items", "posts"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, Mapping)]
        return [payload]
    return []


def _find_row(payload: Any, post_id: str) -> Mapping[str, Any] | None:
    for row in _rows(payload):
        if str(row.get("id") or "") == str(post_id):
            return row
    return None


def _normalize(raw: Mapping[str, Any]) -> dict[str, str] | None:
    text = str(raw.get("text") or raw.get("full_text") or "")
    author = str(raw.get("author") or "").lstrip("@")
    row_id = str(raw.get("id_str") or raw.get("id") or "")
    url = str(raw.get("url") or "")
    if not url and author and row_id:
        url = f"https://x.com/{author}/status/{row_id}"
    if not text and not url:
        return None
    return {
        "url": url,
        "author": author,
        "text": text,
        "time": str(raw.get("created_at") or ""),
    }


def _matchable(text: str) -> str:
    """比对用的归一化：去掉 URL 和空白——X 会把链接改写成 t.co，原文直接对不上。"""
    return re.sub(r"\s+", "", re.sub(r"https?://\S+", "", str(text)))


def _handle(payload: Any) -> str:
    if isinstance(payload, Mapping):
        for key in ("username", "screen_name", "handle"):
            value = payload.get(key)
            if value:
                return str(value).lstrip("@")
        if isinstance(payload.get("user"), Mapping):
            return _handle(payload["user"])
    return ""


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            number = float(value)
        except ValueError:
            return None
        return int(number) if number.is_integer() else number
    return None


def _metrics(raw: Mapping[str, Any]) -> dict[str, int | float]:
    pairs = {
        "likes": ("likes", "like_count", "favorite_count"),
        "reposts": ("retweets", "retweet_count", "reposts"),
        "replies": ("replies", "reply_count"),
        "views": ("views", "view_count", "impression_count"),
        "bookmarks": ("bookmarks", "bookmark_count"),
    }
    metrics: dict[str, int | float] = {}
    for output, keys in pairs.items():
        for key in keys:
            number = _number(raw.get(key))
            if number is not None:
                metrics[output] = number
                break
    return metrics
