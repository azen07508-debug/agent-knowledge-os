"""Phase 16：AnalyticsStore——PostAnalytics 快照的 SQLite 存储。

同一 post 多次采集 = 多行快照（按 collected_at 排序），可以看趋势；
查询默认排除转发（attributed=False 的指标属于原作者）。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from runtime.post_analytics import PostAnalytics

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "analytics.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS post_analytics (
    id             TEXT PRIMARY KEY,
    post_id        TEXT NOT NULL,
    platform       TEXT NOT NULL,
    content_id     TEXT NOT NULL DEFAULT '',
    collected_at   TEXT NOT NULL,
    publish_time   TEXT NOT NULL DEFAULT '',
    content_type   TEXT NOT NULL DEFAULT '',
    is_retweet     INTEGER NOT NULL DEFAULT 0,
    attributed     INTEGER NOT NULL DEFAULT 1,
    metrics        TEXT NOT NULL DEFAULT '{}',
    engagement     INTEGER NOT NULL DEFAULT 0,
    engagement_rate REAL,
    source         TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_pa_post ON post_analytics (post_id, collected_at);
CREATE INDEX IF NOT EXISTS idx_pa_content ON post_analytics (content_id);
CREATE INDEX IF NOT EXISTS idx_pa_collected ON post_analytics (collected_at);
"""


class AnalyticsStore:
    """只追加快照；不做任何策略解释（那是 Phase 17 Analytics Agent 的事）。"""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def record(self, snap: PostAnalytics) -> str:
        """追加一条采集快照，返回行 id。"""
        row_id = f"{snap.post_id}-{snap.collected_at.replace(' ', '').replace(':', '')}"
        while self.get(row_id) is not None:
            row_id += "x"  # 同秒重复采集：后缀区分，不覆盖历史
        self._conn.execute(
            "INSERT INTO post_analytics (id, post_id, platform, content_id, collected_at,"
            " publish_time, content_type, is_retweet, attributed, metrics, engagement,"
            " engagement_rate, source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (row_id, snap.post_id, snap.platform, snap.content_id, snap.collected_at,
             snap.publish_time, snap.content_type, int(snap.is_retweet),
             int(snap.attributed), json.dumps(snap.metrics, ensure_ascii=False),
             snap.engagement, snap.engagement_rate, snap.source),
        )
        self._conn.commit()
        return row_id

    @staticmethod
    def _to_snap(row: sqlite3.Row) -> PostAnalytics:
        return PostAnalytics(
            post_id=row["post_id"],
            platform=row["platform"],
            collected_at=row["collected_at"],
            content_id=row["content_id"],
            publish_time=row["publish_time"],
            content_type=row["content_type"],
            is_retweet=bool(row["is_retweet"]),
            metrics=json.loads(row["metrics"]),
            source=row["source"],
        )

    def get(self, row_id: str) -> PostAnalytics | None:
        row = self._conn.execute(
            "SELECT * FROM post_analytics WHERE id = ?", (row_id,)
        ).fetchone()
        return self._to_snap(row) if row else None

    def history(self, post_id: str, include_retweets: bool = False) -> list[PostAnalytics]:
        """一个 post 的采集历史（时间序）。默认不含转发。"""
        sql = "SELECT * FROM post_analytics WHERE post_id = ?"
        if not include_retweets:
            sql += " AND attributed = 1"
        sql += " ORDER BY collected_at"
        return [self._to_snap(row) for row in self._conn.execute(sql, (post_id,))]

    def latest(self, post_id: str) -> PostAnalytics | None:
        rows = self.history(post_id, include_retweets=True)
        return rows[-1] if rows else None

    def by_content(self, content_id: str, include_retweets: bool = False) -> list[PostAnalytics]:
        """一个 ContentObject 关联的所有 post 快照。"""
        sql = "SELECT * FROM post_analytics WHERE content_id = ?"
        if not include_retweets:
            sql += " AND attributed = 1"
        sql += " ORDER BY collected_at"
        return [self._to_snap(row) for row in self._conn.execute(sql, (content_id,))]

    def recent(self, limit: int = 20, platform: str = "",
               include_retweets: bool = False) -> list[PostAnalytics]:
        """最近的采集快照（每 post 取最新一条，去重）。给 Phase 17 模式识别用。"""
        sql = "SELECT * FROM post_analytics WHERE 1=1"
        params: list[Any] = []
        if not include_retweets:
            sql += " AND attributed = 1"
        if platform:
            sql += " AND platform = ?"
            params.append(platform)
        sql += " ORDER BY collected_at DESC"
        rows = [self._to_snap(row) for row in self._conn.execute(sql, params)]
        seen: set[str] = set()
        result: list[PostAnalytics] = []
        for snap in rows:
            if snap.post_id in seen:
                continue
            seen.add(snap.post_id)
            result.append(snap)
            if len(result) >= limit:
                break
        return result

    def counts(self) -> dict[str, int]:
        total = self._conn.execute("SELECT COUNT(*) AS n FROM post_analytics").fetchone()
        retweets = self._conn.execute(
            "SELECT COUNT(*) AS n FROM post_analytics WHERE is_retweet = 1"
        ).fetchone()
        posts = self._conn.execute(
            "SELECT COUNT(DISTINCT post_id) AS n FROM post_analytics WHERE attributed = 1"
        ).fetchone()
        return {"snapshots": int(total["n"]), "posts": int(posts["n"]),
                "retweets": int(retweets["n"])}

    def close(self) -> None:
        self._conn.close()
