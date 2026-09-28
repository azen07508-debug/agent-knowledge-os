"""Phase 4：Agent-Reach 联网调研 -> 写入 Research 记忆。

边界：
    fetch()   只读。调 agent-reach 通道抓材料，返回截断摘要 + 来源 URL 给 Agent，不落盘
    research() 需要联网成功才写入。结论由调用方（Agent）给出，本层不生成内容、不存原文

    结论缺失、抓取失败、通道不存在时都不写记忆：宁可没有记忆，也不要凭空记忆。
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Iterable

from runtime.memory_api import MemoryAPI

DIGEST_CHARS = 1500
"""返回给 Agent 的材料摘要上限：原始返回不进记忆，也不整段塞给下游。"""

URL_PATTERN = re.compile(r"https?://[A-Za-z0-9\-._~:/?#%&=+@!$]+")

ChannelCommand = Callable[[str, int], list[str]]


def _web_command(query: str, limit: int) -> list[str]:
    """Exa 网页搜索（零配置）。"""
    return ["mcporter", "call", "exa.web_search_exa", f"query={query}", f"numResults={limit}"]


def _github_command(query: str, limit: int) -> list[str]:
    """GitHub 仓库搜索（零配置）。"""
    return ["gh", "search", "repos", query, "--limit", str(limit)]


GITHUB_ROW = re.compile(r"^([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\t", re.MULTILINE)


def _github_sources(text: str) -> list[str]:
    """gh 输出是 owner/repo + 描述的 TSV，没有 URL，按行还原成仓库地址。"""
    return [f"https://github.com/{match.group(1)}" for match in GITHUB_ROW.finditer(text)]


ERROR_MARKER = (
    "error",
    "exception",
    "traceback",
    "failed",
    "failure",
    "rate limit",
    "over capacity",
    "unauthorized",
)

NOTICE_MARKER = (
    "rate limit",
    "api key",
    "over capacity",
    "error (",
    "you've hit",
    "fix:",
    "unauthorized",
    "forbidden",
    "quota",
)


def _is_failure(digest: str, sources: list[str]) -> bool:
    """通道偶尔会以退出码 0 返回报错/限流通知，别把它当成调研材料。

    短文本 + 工具通知关键词 -> 失败；没有来源 + 报错关键词 -> 失败。
    """
    lowered = digest.lower()
    if len(digest) <= 400 and any(marker in lowered for marker in NOTICE_MARKER):
        return True
    return not sources and any(marker in lowered for marker in ERROR_MARKER)


def _page_command(query: str, limit: int) -> list[str]:
    """通用网页阅读：query 传 URL，经 Jina Reader 转成 Markdown。"""
    return ["curl", "-sL", f"https://r.jina.ai/{query}"]


CHANNELS: dict[str, ChannelCommand] = {
    "web": _web_command,
    "github": _github_command,
    "page": _page_command,
}


def _default_run(argv: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


class ReachResearch:
    """通过 agent-reach 通道做外部调研，并把结论写进 11-Research。"""

    def __init__(
        self,
        memory: MemoryAPI | None = None,
        vault_path: str | Path | None = None,
        runner: Callable[[list[str], int], Any] = _default_run,
        which: Callable[[str], str | None] = shutil.which,
        timeout: int = 60,
    ) -> None:
        self.memory = memory or MemoryAPI(vault_path=vault_path)
        self._run = runner
        self._which = which
        self.timeout = timeout

    # ── 只读：抓材料 ─────────────────────────────────────────────────────

    def fetch(self, query: str, channel: str = "web", limit: int = 5) -> dict[str, Any]:
        """调 agent-reach 通道抓材料，返回截断摘要与来源 URL；失败返回 ok=False，不抛。"""
        if channel not in CHANNELS:
            raise ValueError(f"未知调研通道：{channel}，可选：{', '.join(CHANNELS)}")

        argv = CHANNELS[channel](query, limit)
        binary = argv[0]
        if self._which(binary) is None:
            return {
                "ok": False,
                "channel": channel,
                "query": query,
                "message": f"通道不可用：找不到命令 {binary}，请先安装或接入 agent-reach。",
            }

        try:
            result = self._run(argv, self.timeout)
        except (OSError, subprocess.SubprocessError) as exc:
            return {"ok": False, "channel": channel, "query": query, "message": f"调研命令执行失败：{exc}"}

        output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
        if getattr(result, "returncode", 1) != 0:
            return {
                "ok": False,
                "channel": channel,
                "query": query,
                "message": f"调研命令退出码 {getattr(result, 'returncode', '?')}：{(result.stderr or '').strip()[:200]}",
            }
        if not output.strip():
            return {"ok": False, "channel": channel, "query": query, "message": "调研通道返回空结果。"}

        digest = output.strip()
        if len(digest) > DIGEST_CHARS:
            digest = digest[:DIGEST_CHARS] + "…"

        sources = _dedupe(list(_github_sources(output)) + extract_sources(output)) if channel == "github" else extract_sources(output)
        if _is_failure(digest, sources):
            return {
                "ok": False,
                "channel": channel,
                "query": query,
                "message": f"调研通道返回报错文本：{digest[:200]}",
            }

        return {
            "ok": True,
            "channel": channel,
            "query": query,
            "digest": digest,
            "sources": sources,
        }

    # ── 写入：结论进记忆 ─────────────────────────────────────────────────

    def research(
        self,
        topic: str,
        conclusions: str | Iterable[str],
        query: str,
        channel: str = "web",
        limit: int = 5,
        verified: str | Iterable[str] | None = None,
        unverified: str | Iterable[str] | None = None,
        sources: str | Iterable[str] | None = None,
    ) -> dict[str, Any]:
        """联网调研并写入 11-Research：抓取失败一律不写，来源取抓取到的 URL。

        conclusions 必须由调用方给出（本层不生成结论）；抓取到的原文只用于返回，
        不写进记忆。
        """
        fetched = self.fetch(query, channel=channel, limit=limit)
        if not fetched["ok"]:
            raise RuntimeError(f"联网调研失败，未写入记忆：{fetched['message']}")

        merged = _dedupe(list(_as_lines(sources)) + fetched["sources"])
        if not merged:
            raise RuntimeError("调研结果里没有可用来源 URL，拒绝写入无来源结论。")

        record = self.memory.layer.save_research(
            topic=topic,
            conclusions=conclusions,
            sources=merged,
            verified=verified,
            unverified=unverified,
            source=merged[0],
        )
        record["fetched"] = {
            "channel": channel,
            "query": query,
            "sources": merged,
            "digest_chars": len(fetched["digest"]),
        }
        return record


def extract_sources(text: str) -> list[str]:
    """从工具输出里抽取去重后的 URL（保留出现顺序）。"""
    return _dedupe(match.group(0).rstrip(".,;") for match in URL_PATTERN.finditer(text))


def _as_lines(value: str | Iterable[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(item).strip() for item in value if str(item).strip()]


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
