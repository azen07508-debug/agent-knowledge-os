"""Phase 10 后端实现：twitter-cli（XAdapter 的 backend）。

凭据：~/.agent-reach/config.yaml 的 twitter_auth_token / twitter_ct0
（由 `agent-reach configure twitter-cookies` 隐藏输入写入），只注入子进程 env，
不打印、不写日志。代理：同文件 proxy → HTTP(S)_PROXY。

边界：只做「拼命令 + 解析输出」，读写语义仍归 XAdapter；解析不了就报失败，不猜。
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping

DEFAULT_CONFIG = Path.home() / ".agent-reach" / "config.yaml"

MISSING_CREDS = "X 凭据缺失：先运行 `agent-reach configure twitter-cookies`（隐藏输入 auth_token/ct0）。"
NO_SCHEDULE = "twitter-cli 不支持定时发布；定时排期由 Phase 15 PublishJob 承担。"


def load_config(path: Path) -> dict[str, str]:
    """读 agent-reach 的 config.yaml（`key: value` 简单格式，不引第三方 YAML）。"""
    config: dict[str, str] = {}
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError:
        return config
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        config[key.strip()] = value.strip()
    return config


class TwitterCliXBackend:
    """把 X 读写翻译成 twitter-cli 命令；未配凭据时 available=False。"""

    def __init__(
        self,
        runner: Callable[..., Any] | None = None,
        twitter_bin: str = "twitter",
        config_path: str | Path = DEFAULT_CONFIG,
        env: Mapping[str, str] | None = None,
        timeout: int = 45,
    ) -> None:
        self._run = runner or _default_run
        self.twitter_bin = twitter_bin
        self.config_path = Path(config_path)
        self._env_override = dict(env or {})
        self.timeout = timeout

    # ── 环境与凭据 ────────────────────────────────────────────────────────

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        config = load_config(self.config_path)
        proxy = config.get("proxy") or ""
        if proxy:
            for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
                env[name] = proxy
        for key, name in (("twitter_auth_token", "TWITTER_AUTH_TOKEN"), ("twitter_ct0", "TWITTER_CT0")):
            value = config.get(key) or ""
            if value:
                env[name] = value
        env.update(self._env_override)  # 显式传入的 env 优先
        return env

    @property
    def available(self) -> bool:
        env = self._env()
        return bool(env.get("TWITTER_AUTH_TOKEN") and env.get("TWITTER_CT0"))

    # ── 命令执行 ──────────────────────────────────────────────────────────

    def _call(self, argv: list[str]) -> dict[str, Any]:
        env = self._env()
        if not (env.get("TWITTER_AUTH_TOKEN") and env.get("TWITTER_CT0")):
            return {"ok": False, "message": MISSING_CREDS}
        try:
            proc = self._run(argv, timeout=self.timeout, env=env)
        except Exception as exc:  # 后端异常 -> 可解释失败，不假装成功
            return {"ok": False, "message": f"twitter-cli 调用失败：{exc}"}
        stdout = str(getattr(proc, "stdout", "") or "")
        if getattr(proc, "returncode", 1) != 0:
            detail = str(getattr(proc, "stderr", "") or "").strip() or stdout.strip()
            return {"ok": False, "message": f"twitter-cli 退出码 {proc.returncode}：{detail[:300]}"}
        return {"ok": True, "stdout": stdout}

    def _read(self, argv: list[str]) -> dict[str, Any]:
        called = self._call(argv)
        if not called["ok"]:
            return called
        payload = _json(called["stdout"])
        if payload is None:
            return {"ok": False, "message": "twitter-cli 输出不是 JSON（加 --json 后仍非 JSON，解析不了就不猜）。"}
        items = [item for item in (_normalize(raw) for raw in _tweets(payload)) if item]
        return {"ok": True, "items": items}

    # ── XAdapter 需要的六个方法 ──────────────────────────────────────────

    def search(self, query: str, limit: int = 10) -> dict[str, Any]:
        return self._read([self.twitter_bin, "search", query, "-n", str(limit), "--json"])

    def timeline(self, limit: int = 20) -> dict[str, Any]:
        return self._read([self.twitter_bin, "feed", "-n", str(limit), "--json"])

    def mentions(self, limit: int = 20) -> dict[str, Any]:
        who = self._call([self.twitter_bin, "whoami", "--json"])
        if not who["ok"]:
            return who
        payload = _json(who["stdout"])
        handle = _handle(payload)
        if not handle:
            return {"ok": False, "message": "whoami 没返回用户名，查不了 Mentions。"}
        return self._read([self.twitter_bin, "search", "--to", handle, "-n", str(limit), "--json"])

    def post(self, text: str) -> dict[str, Any]:
        called = self._call([self.twitter_bin, "post", text, "--json"])
        if not called["ok"]:
            return called
        payload = _json(called["stdout"])
        return {"ok": True, "id": _tweet_id(payload)}

    def schedule(self, text: str, at: str) -> dict[str, Any]:
        return {"ok": False, "message": NO_SCHEDULE}

    def analytics(self, post_id: str) -> dict[str, Any]:
        called = self._call([self.twitter_bin, "tweet", post_id, "--json"])
        if not called["ok"]:
            return called
        payload = _json(called["stdout"])
        if payload is None:
            return {"ok": False, "message": "twitter-cli 输出不是 JSON，解析不了互动指标。"}
        metrics = _metrics(_first_tweet(payload))
        if not metrics:
            return {"ok": False, "message": "推文数据里没有互动指标。"}
        return {"ok": True, "metrics": metrics}


def _default_run(argv: list[str], timeout: int, env: dict[str, str]):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env)


# ── 输出解析（容忍字段差异，解析不了就返回空而不是编造） ────────────────


def _json(stdout: str) -> Any | None:
    try:
        return json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return None


def _tweets(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("tweets", "results", "data", "items", "posts"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, Mapping)]
            if isinstance(value, Mapping) and key == "data":
                return _tweets(value)
        return [payload]
    return []


def _first_tweet(payload: Any) -> Mapping[str, Any]:
    tweets = _tweets(payload)
    return tweets[0] if tweets else {}


def _normalize(raw: Mapping[str, Any]) -> dict[str, str] | None:
    text = str(raw.get("text") or raw.get("full_text") or "")
    author = _author(raw)
    tweet_id = str(raw.get("id_str") or raw.get("id") or "")
    url = str(raw.get("url") or "")
    if not url and author and tweet_id:
        url = f"https://x.com/{author}/status/{tweet_id}"
    if not text and not url:
        return None
    return {
        "url": url,
        "author": author,
        "text": text,
        "time": str(raw.get("created_at") or ""),
    }


def _author(raw: Mapping[str, Any]) -> str:
    user = raw.get("user") or raw.get("author") or {}
    candidates = [user] if isinstance(user, Mapping) else []
    candidates.append(raw)
    for candidate in candidates:
        for key in ("screen_name", "username", "handle"):
            value = candidate.get(key)
            if value:
                return str(value).lstrip("@")
    return ""


def _handle(payload: Any) -> str:
    if isinstance(payload, Mapping):
        for key in ("screen_name", "username", "handle"):
            if payload.get(key):
                return str(payload[key]).lstrip("@")
        if isinstance(payload.get("user"), Mapping):
            return _handle(payload["user"])
    return ""


def _tweet_id(payload: Any) -> str:
    if isinstance(payload, Mapping):
        for key in ("id_str", "id", "tweet_id"):
            if payload.get(key):
                return str(payload[key])
        tweet = _first_tweet(payload)
        if tweet:
            return _tweet_id(tweet)
    if isinstance(payload, list) and payload:
        return _tweet_id(payload[0])
    return ""


def _metrics(raw: Mapping[str, Any]) -> dict[str, int | float]:
    pairs = {
        "likes": ("like_count", "likes", "favorite_count"),
        "reposts": ("retweet_count", "reposts", "retweets"),
        "replies": ("reply_count", "replies"),
        "views": ("views", "view_count", "impression_count"),
        "bookmarks": ("bookmark_count", "bookmarks"),
    }
    metrics: dict[str, int | float] = {}
    for output, keys in pairs.items():
        for key in keys:
            value = raw.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                metrics[output] = value
                break
    return metrics
