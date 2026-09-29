"""Phase 4：ResearchItem 结构化存储。

边界（对应 PLAN 1.4）：
    原始抓取材料 -> 这里（SQLite，可查可弃，属于运行数据）
    值得长期使用的研究结论 -> Memory（Obsidian，MemoryAPI）
两边互不替代：数据库里是「看过什么」，记忆里是「学到什么」。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "research.sqlite3"

CONTENT_CHARS = 800
"""单条 ResearchItem 的 content 上限：是摘要不是全文。"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS research_items (
    id          TEXT PRIMARY KEY,
    url         TEXT NOT NULL UNIQUE,
    source      TEXT NOT NULL,
    author      TEXT,
    timestamp   TEXT,
    title       TEXT,
    content     TEXT NOT NULL DEFAULT '',
    engagement  TEXT NOT NULL DEFAULT '{}',
    topic       TEXT NOT NULL DEFAULT '',
    evidence    TEXT NOT NULL DEFAULT '',
    query       TEXT NOT NULL DEFAULT '',
    fetched_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_research_items_source ON research_items(source);
CREATE INDEX IF NOT EXISTS idx_research_items_topic ON research_items(topic);
"""


@dataclass
class ResearchItem:
    """一次外部抓取得到的最小信息单元。"""

    source: str
    url: str
    title: str = ""
    author: str = ""
    timestamp: str = ""
    content: str = ""
    engagement: dict[str, Any] = field(default_factory=dict)
    topic: str = ""
    evidence: str = ""
    query: str = ""
    fetched_at: str = ""

    def __post_init__(self) -> None:
        if not self.fetched_at:
            self.fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if len(self.content) > CONTENT_CHARS:
            self.content = self.content[:CONTENT_CHARS] + "…"
        self.url = self.url.strip()

    @property
    def id(self) -> str:
        return hashlib.sha1(self.url.encode("utf-8")).hexdigest()[:12]


class ResearchStore:
    """ResearchItem 的 SQLite 存取；以 URL 为唯一键，重复抓取即更新。"""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def save(self, item: ResearchItem) -> dict[str, Any]:
        """写入或更新一条研究材料，返回是否为新记录。"""
        if not item.url:
            raise ValueError("ResearchItem 必须有来源 URL。")
        existed = self.get(item.url) is not None
        row = asdict(item)
        row["id"] = item.id
        row["engagement"] = json.dumps(item.engagement, ensure_ascii=False)
        self._conn.execute(
            """
            INSERT INTO research_items (id, url, source, author, timestamp, title, content,
                                        engagement, topic, evidence, query, fetched_at)
            VALUES (:id, :url, :source, :author, :timestamp, :title, :content,
                    :engagement, :topic, :evidence, :query, :fetched_at)
            ON CONFLICT(url) DO UPDATE SET
                source = excluded.source,
                author = excluded.author,
                timestamp = excluded.timestamp,
                title = excluded.title,
                content = excluded.content,
                engagement = excluded.engagement,
                topic = excluded.topic,
                evidence = excluded.evidence,
                query = excluded.query,
                fetched_at = excluded.fetched_at
            """,
            row,
        )
        self._conn.commit()
        return {"ok": True, "id": item.id, "url": item.url, "created": not existed}

    def save_many(self, items: Iterable[ResearchItem]) -> dict[str, Any]:
        created = updated = 0
        for item in items:
            result = self.save(item)
            created += 1 if result["created"] else 0
            updated += 0 if result["created"] else 1
        return {"ok": True, "created": created, "updated": updated, "count": created + updated}

    def get(self, url_or_id: str) -> dict[str, Any] | None:
        """按 URL 或 ID 取一条研究材料。"""
        row = self._conn.execute(
            "SELECT * FROM research_items WHERE url = ? OR id = ?",
            (url_or_id, url_or_id),
        ).fetchone()
        return _to_item(row) if row else None

    def search(self, query: str = "", topic: str = "", limit: int = 10) -> list[dict[str, Any]]:
        """关键词检索抓取材料；可再按 topic 过滤。"""
        clauses, params = [], []
        if query:
            like = f"%{query}%"
            clauses.append("(title LIKE ? OR content LIKE ? OR evidence LIKE ? OR url LIKE ?)")
            params += [like, like, like, like]
        if topic:
            clauses.append("topic = ?")
            params.append(topic)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM research_items {where} ORDER BY fetched_at DESC, rowid DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [_to_item(row) for row in rows]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM research_items").fetchone()[0]

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> ResearchStore:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _to_item(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    try:
        data["engagement"] = json.loads(data.get("engagement") or "{}")
    except json.JSONDecodeError:
        data["engagement"] = {}
    return data
