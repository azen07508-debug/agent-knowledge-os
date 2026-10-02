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
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from runtime.memory_api import MemoryAPI
from runtime.research_store import ResearchItem, ResearchStore
from runtime.x_adapter import XAdapter, default_x_adapter

DIGEST_CHARS = 1500
"""返回给 Agent 的材料摘要上限：原始返回不进记忆，也不整段塞给下游。"""

URL_PATTERN = re.compile(r"https?://[A-Za-z0-9\-._~:/?#%&=+@!$]+")

BLOCK_FIELD = re.compile(r"^(Title|URL|Author|Published):\s*(.*)$", re.MULTILINE)

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
        store: ResearchStore | None = None,
        x_adapter: XAdapter | None = None,
    ) -> None:
        self.memory = memory or MemoryAPI(vault_path=vault_path)
        self._run = runner
        self._which = which
        self.timeout = timeout
        self._store = store
        self._x = x_adapter

    @property
    def x(self) -> XAdapter:
        """X 读接口（search 等）；Phase 10 起 channel='x' 走这里。

        默认用 default_x_adapter()：配了 twitter-cli 凭据就自动接上，没配就保持未配置。
        """
        if self._x is None:
            self._x = default_x_adapter()
        return self._x

    @property
    def store(self) -> ResearchStore:
        """研究材料数据库（首次使用时才创建，fetch 只读不落库）。"""
        if self._store is None:
            self._store = ResearchStore()
        return self._store

    # ── 只读：抓材料 ─────────────────────────────────────────────────────

    def fetch(self, query: str, channel: str = "web", limit: int = 5) -> dict[str, Any]:
        """调 agent-reach 通道抓材料，返回截断摘要与来源 URL；失败返回 ok=False，不抛。"""
        if channel == "x":
            return self._fetch_x(query, limit)
        if channel not in CHANNELS:
            raise ValueError(f"未知调研通道：{channel}，可选：x, {', '.join(CHANNELS)}")

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

        sources = collect_sources(channel, output)
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

    def _fetch_x(self, query: str, limit: int) -> dict[str, Any]:
        """Research X：走 XAdapter.search（不散落 X API 逻辑）。"""
        result = self.x.search(query, limit)
        if not result.get("ok"):
            return {"ok": False, "channel": "x", "query": query, "message": result.get("message", "X 搜索失败。")}
        items = [item for item in result.get("items", []) if item.get("url")]
        if not items:
            return {"ok": False, "channel": "x", "query": query, "message": "X 搜索没有带链接的结果。"}
        lines = [
            "\t".join((item["url"], item.get("author", ""), item.get("text", "").replace("\n", " ")))
            for item in items
        ]
        digest = "\n".join(lines)
        if len(digest) > DIGEST_CHARS:
            digest = digest[:DIGEST_CHARS] + "…"
        return {
            "ok": True,
            "channel": "x",
            "query": query,
            "digest": digest,
            "sources": [item["url"] for item in items],
        }

    # ── 落库：原始材料进数据库 ───────────────────────────────────────────

    def harvest(
        self,
        query: str,
        channel: str = "web",
        limit: int = 5,
        topic: str = "",
    ) -> dict[str, Any]:
        """抓取并把材料存进 ResearchStore（SQLite），不写记忆。"""
        fetched = self.fetch(query, channel=channel, limit=limit)
        if not fetched["ok"]:
            return fetched
        items = parse_items(channel, query, fetched["digest"], topic=topic)
        saved = self.store.save_many(items)
        return {
            "ok": True,
            "channel": channel,
            "query": query,
            "items": [
                {
                    "id": item.id,
                    "url": item.url,
                    "source": item.source,
                    "title": item.title,
                    "content": item.content,
                    "timestamp": item.timestamp,
                    "topic": item.topic,
                    "fetched_at": item.fetched_at,
                }
                for item in items
            ],
            "stored": saved,
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

        # 原始材料进数据库（PLAN 1.4：不存进记忆）
        stored = self.store.save_many(parse_items(channel, query, fetched["digest"], topic=topic))

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
            "stored": stored,
        }
        return record


def extract_sources(text: str) -> list[str]:
    """从工具输出里抽取去重后的 URL（保留出现顺序）。"""
    return _dedupe(match.group(0).rstrip(".,;") for match in URL_PATTERN.finditer(text))


def collect_sources(channel: str, output: str) -> list[str]:
    """通道相关的来源抽取：GitHub 只认结果行，描述里夹带的外链不算来源。"""
    if channel == "github":
        return _github_sources(output)
    return extract_sources(output)


def parse_items(channel: str, query: str, output: str, topic: str = "") -> list[ResearchItem]:
    """把通道输出拆成 ResearchItem。

    `Title:/URL:/Author:/Published:` 分块格式按块拆（Exa 搜索结果）；
    其余格式（GitHub TSV、Jina 页面）每个来源一条，content 用可读的材料摘要。
    """
    blocks = _parse_blocks(channel, query, output, topic)
    if blocks:
        return blocks
    digest = output.strip()
    items = []
    for url in collect_sources(channel, output):
        line = _row_for(channel, url, output) or digest
        items.append(
            ResearchItem(
                source=channel,
                url=url,
                title=_item_title(channel, url, line),
                content=_material_text(channel, line),
                query=query,
                topic=topic,
            )
        )
    return items


def _material_text(channel: str, line: str) -> str:
    """GitHub TSV 行转成可读文本——原始行带制表符，会原样进「事实」，给人看到就是事故。

    `owner/repo\\tdesc\\tpublic\\t2026-10-01T06:58:46Z` → `owner/repo：desc（更新于 2026-10-01）`
    """
    if channel != "github" or "\t" not in line:
        return line
    parts = [part.strip() for part in line.split("\t")]
    text = f"{parts[0]}：{parts[1]}" if len(parts) > 1 and parts[1] else parts[0]
    pushed = parts[-1] if len(parts) > 2 else ""
    if len(pushed) >= 10 and pushed[:4].isdigit():
        text += f"（更新于 {pushed[:10]}）"
    return text


def _item_title(channel: str, url: str, line: str) -> str:
    """GitHub 行给仓库名，X 行给推文文本（tab 分隔的最后一段）。"""
    if channel == "github":
        return "/".join(url.rstrip("/").split("/")[-2:])
    if channel == "x":
        parts = line.split("\t")
        return parts[-1][:60] if len(parts) > 1 else ""
    return ""


def _row_for(channel: str, url: str, output: str) -> str:
    """行式输出（GitHub TSV、X 结果行）：每个来源只留它自己那一行，不共享整段输出。"""
    if channel == "github":
        key = "/".join(url.rstrip("/").split("/")[-2:]) if "github.com/" in url else url
    elif channel == "x":
        key = url
    else:
        return ""
    for line in output.splitlines():
        if key and key in line:
            return line.strip()
    return ""


def _parse_blocks(channel: str, query: str, output: str, topic: str) -> list[ResearchItem]:
    lines = output.splitlines()
    starts = [index for index, line in enumerate(lines) if line.startswith("Title:")]
    items: list[ResearchItem] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(lines)
        fields: dict[str, str] = {}
        body: list[str] = []
        for line in lines[start:end]:
            match = BLOCK_FIELD.match(line)
            if match:
                fields[match.group(1).lower()] = match.group(2).strip()
            else:
                body.append(line)
        url = fields.get("url", "")
        if not url:
            continue
        items.append(
            ResearchItem(
                source=channel,
                url=url,
                title=fields.get("title", ""),
                author=fields.get("author", ""),
                timestamp=fields.get("published", ""),
                content="\n".join(body).strip(),
                query=query,
                topic=topic,
            )
        )
    return items


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
