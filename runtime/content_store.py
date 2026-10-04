"""Phase 8：ContentObject 的 SQLite 存储（生产管线数据，可查可回溯）。

与 ResearchStore 同层：都是运行数据。区别——
    ResearchStore：抓过什么（原始材料）
    ContentStore：在做什么（内容生命周期）
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from runtime.content_object import STATUSES, ContentObject

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "content.sqlite3"

JSON_FIELDS = ("title_candidates", "sources", "evidence", "claims", "media", "platform_versions", "platform_posts", "ai_suggestions", "review_notes")

SCHEMA = """
CREATE TABLE IF NOT EXISTS content_objects (
    id                TEXT PRIMARY KEY,
    topic             TEXT NOT NULL,
    title_candidates  TEXT NOT NULL DEFAULT '[]',
    evidence_status   TEXT NOT NULL DEFAULT 'UNKNOWN',
    content_source    TEXT NOT NULL DEFAULT '',
    angle             TEXT NOT NULL DEFAULT '',
    audience          TEXT NOT NULL DEFAULT '',
    sources           TEXT NOT NULL DEFAULT '[]',
    evidence          TEXT NOT NULL DEFAULT '[]',
    claims            TEXT NOT NULL DEFAULT '[]',
    hook              TEXT NOT NULL DEFAULT '',
    core_content      TEXT NOT NULL DEFAULT '',
    media             TEXT NOT NULL DEFAULT '[]',
    platform_versions TEXT NOT NULL DEFAULT '{}',
    platform_posts    TEXT NOT NULL DEFAULT '{}',
    ai_suggestions    TEXT NOT NULL DEFAULT '[]',
    review_notes      TEXT NOT NULL DEFAULT '[]',
    status            TEXT NOT NULL DEFAULT 'IDEA',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_content_status ON content_objects(status);
CREATE INDEX IF NOT EXISTS idx_content_topic ON content_objects(topic);
"""


class ContentStore:
    """ContentObject 的存取；状态变化必须走 transition()（状态机校验）。"""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._ensure_columns()
        self._conn.commit()

    def _ensure_columns(self) -> None:
        """Add fields introduced after the initial SQLite schema without destroying local data."""
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(content_objects)")}
        additions = {
            "title_candidates": "TEXT NOT NULL DEFAULT '[]'",
            "evidence_status": "TEXT NOT NULL DEFAULT 'UNKNOWN'",
            "content_source": "TEXT NOT NULL DEFAULT ''",
            "platform_posts": "TEXT NOT NULL DEFAULT '{}'",
        }
        for name, definition in additions.items():
            if name not in columns:
                self._conn.execute(f"ALTER TABLE content_objects ADD COLUMN {name} {definition}")

    def save(self, obj: ContentObject) -> dict[str, Any]:
        """新建或覆盖一条内容对象，返回是否新建。"""
        existed = self.get(obj.id) is not None
        row = obj.to_dict()
        for name in JSON_FIELDS:
            row[name] = json.dumps(row[name], ensure_ascii=False)
        columns = ", ".join(row)
        placeholders = ", ".join(f":{name}" for name in row)
        updates = ", ".join(f"{name} = excluded.{name}" for name in row if name != "id")
        self._conn.execute(
            f"INSERT INTO content_objects ({columns}) VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}",
            row,
        )
        self._conn.commit()
        return {"ok": True, "id": obj.id, "status": obj.status, "created": not existed}

    def save_many(self, objects: Iterable[ContentObject]) -> dict[str, Any]:
        created = updated = 0
        for obj in objects:
            result = self.save(obj)
            created += 1 if result["created"] else 0
            updated += 0 if result["created"] else 1
        return {"ok": True, "created": created, "updated": updated, "count": created + updated}

    def get(self, object_id: str) -> ContentObject | None:
        row = self._conn.execute(
            "SELECT * FROM content_objects WHERE id = ?", (object_id,)
        ).fetchone()
        return _to_object(row) if row else None

    def list(self, status: str = "", topic: str = "") -> list[dict[str, Any]]:
        """列出内容对象；可按状态或主题过滤，按创建时间倒序。"""
        clauses, params = [], []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if topic:
            clauses.append("topic LIKE ?")
            params.append(f"%{topic}%")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM content_objects {where} ORDER BY created_at DESC, rowid DESC",
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def transition(self, object_id: str, target: str) -> dict[str, Any]:
        """推进状态并落库；状态机或必填字段不满足时抛 ValueError 且不落库。"""
        obj = self.get(object_id)
        if obj is None:
            raise FileNotFoundError(f"内容对象不存在：{object_id}")
        origin = obj.status
        obj.transition(target)
        self.save(obj)
        return {"ok": True, "id": object_id, "from": origin, "to": target}

    def fill(self, object_id: str, fields: Mapping[str, Any]) -> dict[str, Any]:
        """补齐内容字段（hook/coreContent/claims/platformVersions 等），不改状态。"""
        obj = self.get(object_id)
        if obj is None:
            raise FileNotFoundError(f"内容对象不存在：{object_id}")
        if obj.status in ("APPROVED", "SCHEDULED", "PUBLISHED"):
            raise ValueError(f"{obj.status} 内容不可直接修改；先回到 REVIEW/DRAFT 或创建新版本。")
        obj.fill(fields)
        self.save(obj)
        return {"ok": True, "id": object_id, "status": obj.status, "fields": sorted(fields)}

    def count(self, status: str = "") -> int:
        if status:
            return self._conn.execute(
                "SELECT COUNT(*) FROM content_objects WHERE status = ?", (status,)
            ).fetchone()[0]
        return self._conn.execute("SELECT COUNT(*) FROM content_objects").fetchone()[0]

    def status_counts(self) -> dict[str, int]:
        counts = {status: 0 for status in STATUSES}
        rows = self._conn.execute(
            "SELECT status, COUNT(*) AS n FROM content_objects GROUP BY status"
        ).fetchall()
        for row in rows:
            counts[row["status"]] = row["n"]
        return counts

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> ContentStore:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _to_object(row: sqlite3.Row) -> ContentObject:
    data = dict(row)
    for name in JSON_FIELDS:
        try:
            data[name] = json.loads(data.get(name) or ("{}" if name == "platform_versions" else "[]"))
        except json.JSONDecodeError:
            data[name] = {} if name == "platform_versions" else []
    return ContentObject.from_dict(data)
