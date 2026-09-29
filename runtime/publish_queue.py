"""Phase 15：PublishJob 队列（发布基础设施，与 Workflow 状态严格分离）。

- Workflow（ContentObject）：DRAFT → REVIEW → APPROVED，**发布失败绝不改它**；
- PublishJob：QUEUED → RUNNING → SUCCEEDED / FAILED / TIMEOUT_UNVERIFIED →
  RECONCILING → SUCCEEDED / FAILED / NEEDS_REVIEW；
- TIMEOUT 不允许直接转 retry（状态机里没有这条边），必须走对账；
- 重试产生新 attempt（UNIQUE(job_id, attempt_no)），不覆盖旧 attempt；
- 幂等：idempotency_key = sha256(content_id|platform|fingerprint)，
  UNIQUE 约束保证 worker 重启后重复入队不会产生第二个 job。
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, fields
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

DEFAULT_DB = Path("data/publish.sqlite3")
TS = "%Y-%m-%d %H:%M:%S"

# ── 状态机 ──────────────────────────────────────────────────────────────

JOB_STATUSES: tuple[str, ...] = (
    "QUEUED",
    "RUNNING",
    "RETRYING",
    "SUCCEEDED",
    "FAILED",
    "TIMEOUT_UNVERIFIED",
    "RECONCILING",
    "NEEDS_REVIEW",
    "CANCELLED",
)

JOB_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "QUEUED": ("RUNNING", "CANCELLED"),
    "RUNNING": ("SUCCEEDED", "FAILED", "TIMEOUT_UNVERIFIED", "RETRYING"),
    "RETRYING": ("RUNNING", "CANCELLED", "FAILED"),  # FAILED = 重试次数用尽
    "TIMEOUT_UNVERIFIED": ("RECONCILING",),          # 唯一出路是对账，禁止直连 retry
    "RECONCILING": ("SUCCEEDED", "FAILED", "NEEDS_REVIEW"),
    "NEEDS_REVIEW": ("RECONCILING", "FAILED"),       # 人工再跑对账，或人工判死
    "SUCCEEDED": (),
    "FAILED": (),
    "CANCELLED": (),
}

ATTEMPT_STATUSES: tuple[str, ...] = (
    "STARTED",
    "SUCCEEDED",
    "FAILED",
    "TIMEOUT_UNVERIFIED",
    "RECONCILED_SUCCESS",
    "RECONCILED_FAILED",
    "NEEDS_REVIEW",
)

ATTEMPT_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "STARTED": ("SUCCEEDED", "FAILED", "TIMEOUT_UNVERIFIED"),
    "TIMEOUT_UNVERIFIED": ("RECONCILED_SUCCESS", "RECONCILED_FAILED", "NEEDS_REVIEW"),
    "NEEDS_REVIEW": ("RECONCILED_SUCCESS", "RECONCILED_FAILED"),
    "SUCCEEDED": (),
    "FAILED": (),
    "RECONCILED_SUCCESS": (),
    "RECONCILED_FAILED": (),
}

RECONCILIATION_STATUSES: tuple[str, ...] = ("NONE", "MATCHED", "NOT_FOUND", "AMBIGUOUS")


def _now() -> str:
    return datetime.now().strftime(TS)


def _id() -> str:
    return uuid4().hex[:12]


# ── 数据模型 ────────────────────────────────────────────────────────────


@dataclass
class PublishJob:
    """一次发布任务（幂等单位）。"""

    content_id: str
    platform: str
    scheduled_at: str = ""
    status: str = "QUEUED"
    idempotency_key: str = ""
    id: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not (self.content_id or "").strip():
            raise ValueError("PublishJob 必须有 content_id。")
        if not (self.platform or "").strip():
            raise ValueError("PublishJob 必须有 platform。")
        if self.status not in JOB_STATUSES:
            raise ValueError(f"非法 job 状态：{self.status}；只能是 {'/'.join(JOB_STATUSES)}")
        now = _now()
        if not self.id:
            self.id = _id()
        if not self.scheduled_at:
            self.scheduled_at = now
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def transition(self, target: str) -> None:
        if target not in JOB_STATUSES:
            raise ValueError(f"非法 job 状态：{target}；只能是 {'/'.join(JOB_STATUSES)}")
        if target not in JOB_TRANSITIONS[self.status]:
            raise ValueError(
                f"非法迁移：{self.status} → {target}；允许 {self.status} → "
                f"{'/'.join(JOB_TRANSITIONS[self.status]) or '（终态）'}"
            )
        self.status = target


@dataclass
class PublishJobAttempt:
    """一次具体尝试；重试 = 新增 attempt，永不覆盖。"""

    job_id: str
    attempt_no: int
    status: str = "STARTED"
    id: str = ""
    started_at: str = ""
    finished_at: str = ""
    request_fingerprint: str = ""
    provider_request_id: str = ""
    error_code: str = ""
    error_message: str = ""
    reconciliation_status: str = "NONE"
    reconciled_at: str = ""
    published_post_id: str = ""

    def __post_init__(self) -> None:
        if not (self.job_id or "").strip():
            raise ValueError("PublishJobAttempt 必须有 job_id。")
        if self.attempt_no < 1:
            raise ValueError("attempt_no 必须 ≥ 1。")
        if self.status not in ATTEMPT_STATUSES:
            raise ValueError(f"非法 attempt 状态：{self.status}；只能是 {'/'.join(ATTEMPT_STATUSES)}")
        if self.reconciliation_status not in RECONCILIATION_STATUSES:
            raise ValueError(f"非法 reconciliation_status：{self.reconciliation_status}")
        if not self.id:
            self.id = _id()
        if not self.started_at:
            self.started_at = _now()

    def transition(self, target: str) -> None:
        if target not in ATTEMPT_STATUSES:
            raise ValueError(f"非法 attempt 状态：{target}；只能是 {'/'.join(ATTEMPT_STATUSES)}")
        if target not in ATTEMPT_TRANSITIONS[self.status]:
            raise ValueError(
                f"非法迁移：{self.status} → {target}；允许 {self.status} → "
                f"{'/'.join(ATTEMPT_TRANSITIONS[self.status]) or '（终态）'}"
            )
        self.status = target

    def finish(self, status: str, *, error_code: str = "", error_message: str = "",
               provider_request_id: str = "") -> None:
        """收尾一次尝试：置终态/超时态并记录错误与 provider id。"""
        self.transition(status)
        self.finished_at = _now()
        self.error_code = error_code or ""
        self.error_message = error_message or ""
        if provider_request_id:
            self.provider_request_id = provider_request_id


# ── SQLite 存储 ─────────────────────────────────────────────────────────


def idempotency_key_for(content_id: str, platform: str, fingerprint: str) -> str:
    return hashlib.sha256(f"{content_id}|{platform}|{fingerprint}".encode()).hexdigest()


class PublishJobStore:
    """PublishJob + Attempt 的持久化（SQLite）；重启不丢、幂等键唯一。"""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS publish_jobs (
                id TEXT PRIMARY KEY,
                content_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                scheduled_at TEXT NOT NULL,
                status TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS publish_job_attempts (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL REFERENCES publish_jobs(id),
                attempt_no INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL DEFAULT '',
                request_fingerprint TEXT NOT NULL DEFAULT '',
                provider_request_id TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                error_code TEXT NOT NULL DEFAULT '',
                error_message TEXT NOT NULL DEFAULT '',
                reconciliation_status TEXT NOT NULL DEFAULT 'NONE',
                reconciled_at TEXT NOT NULL DEFAULT '',
                published_post_id TEXT NOT NULL DEFAULT '',
                UNIQUE (job_id, attempt_no)
            );
            CREATE INDEX IF NOT EXISTS idx_jobs_due
                ON publish_jobs (status, scheduled_at);
            """
        )
        self._conn.commit()

    # ── 入队（幂等） ──────────────────────────────────────────────────────

    def enqueue(
        self,
        content_id: str,
        platform: str,
        *,
        scheduled_at: str = "",
        fingerprint: str = "",
        idempotency_key: str = "",
    ) -> tuple[PublishJob, bool]:
        """入队；相同 (content_id, platform, fingerprint) 永远只产生一个 job。

        返回 (job, created)；created=False 表示已有相同幂等键的 job（重启/重复调用）。
        """
        key = idempotency_key or idempotency_key_for(content_id, platform, fingerprint)
        existing = self._get_by_key(key)
        if existing is not None:
            return existing, False
        job = PublishJob(
            content_id=content_id,
            platform=platform,
            scheduled_at=scheduled_at,
            idempotency_key=key,
        )
        self._conn.execute(
            "INSERT INTO publish_jobs (id, content_id, platform, scheduled_at, status,"
            " idempotency_key, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (job.id, job.content_id, job.platform, job.scheduled_at, job.status,
             job.idempotency_key, job.created_at, job.updated_at),
        )
        self._conn.commit()
        return job, True

    def _get_by_key(self, key: str) -> PublishJob | None:
        row = self._conn.execute(
            "SELECT * FROM publish_jobs WHERE idempotency_key = ?", (key,)
        ).fetchone()
        return self._to_job(row) if row else None

    # ── 查询与状态 ────────────────────────────────────────────────────────

    @staticmethod
    def _to_job(row: sqlite3.Row) -> PublishJob:
        return PublishJob(
            id=row["id"],
            content_id=row["content_id"],
            platform=row["platform"],
            scheduled_at=row["scheduled_at"],
            status=row["status"],
            idempotency_key=row["idempotency_key"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _to_attempt(row: sqlite3.Row) -> PublishJobAttempt:
        return PublishJobAttempt(
            id=row["id"],
            job_id=row["job_id"],
            attempt_no=row["attempt_no"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            request_fingerprint=row["request_fingerprint"],
            provider_request_id=row["provider_request_id"],
            status=row["status"],
            error_code=row["error_code"],
            error_message=row["error_message"],
            reconciliation_status=row["reconciliation_status"],
            reconciled_at=row["reconciled_at"],
            published_post_id=row["published_post_id"],
        )

    def get(self, job_id: str) -> PublishJob | None:
        row = self._conn.execute(
            "SELECT * FROM publish_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return self._to_job(row) if row else None

    def list_jobs(self, content_id: str = "", platform: str = "") -> list[PublishJob]:
        sql = "SELECT * FROM publish_jobs WHERE 1=1"
        params: list[Any] = []
        if content_id:
            sql += " AND content_id = ?"
            params.append(content_id)
        if platform:
            sql += " AND platform = ?"
            params.append(platform)
        sql += " ORDER BY created_at, id"
        return [self._to_job(row) for row in self._conn.execute(sql, params)]

    def claim_next(self, now: str | None = None) -> PublishJob | None:
        """取一个到期的 QUEUED/RETRYING job 并置 RUNNING；没有到期的返回 None。"""
        now = now or _now()
        row = self._conn.execute(
            "SELECT * FROM publish_jobs"
            " WHERE status IN ('QUEUED', 'RETRYING') AND scheduled_at <= ?"
            " ORDER BY scheduled_at, created_at LIMIT 1",
            (now,),
        ).fetchone()
        if row is None:
            return None
        job = self._to_job(row)
        job.transition("RUNNING")
        self._persist_job(job)
        return job

    def transition(self, job: PublishJob, target: str) -> PublishJob:
        job.transition(target)
        job.updated_at = _now()
        self._persist_job(job)
        return job

    def _persist_job(self, job: PublishJob) -> None:
        self._conn.execute(
            "UPDATE publish_jobs SET scheduled_at = ?, status = ?, updated_at = ? WHERE id = ?",
            (job.scheduled_at, job.status, job.updated_at, job.id),
        )
        self._conn.commit()

    # ── Attempt ──────────────────────────────────────────────────────────

    def attempts(self, job_id: str) -> list[PublishJobAttempt]:
        rows = self._conn.execute(
            "SELECT * FROM publish_job_attempts WHERE job_id = ? ORDER BY attempt_no",
            (job_id,),
        ).fetchall()
        return [self._to_attempt(row) for row in rows]

    def latest_attempt(self, job_id: str) -> PublishJobAttempt | None:
        rows = self.attempts(job_id)
        return rows[-1] if rows else None

    def start_attempt(self, job_id: str, request_fingerprint: str = "") -> PublishJobAttempt:
        """新开一次尝试：attempt_no = 现有最大值 + 1（UNIQUE 约束兜底防覆盖）。"""
        row = self._conn.execute(
            "SELECT COALESCE(MAX(attempt_no), 0) AS top FROM publish_job_attempts WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        attempt = PublishJobAttempt(
            job_id=job_id,
            attempt_no=int(row["top"]) + 1,
            request_fingerprint=request_fingerprint,
        )
        self._conn.execute(
            "INSERT INTO publish_job_attempts (id, job_id, attempt_no, started_at, finished_at,"
            " request_fingerprint, provider_request_id, status, error_code, error_message,"
            " reconciliation_status, reconciled_at, published_post_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (attempt.id, attempt.job_id, attempt.attempt_no, attempt.started_at,
             attempt.finished_at, attempt.request_fingerprint, attempt.provider_request_id,
             attempt.status, attempt.error_code, attempt.error_message,
             attempt.reconciliation_status, attempt.reconciled_at, attempt.published_post_id),
        )
        self._conn.commit()
        return attempt

    def save_attempt(self, attempt: PublishJobAttempt) -> None:
        columns = [f.name for f in fields(attempt) if f.name != "id"]
        values = [getattr(attempt, name) for name in columns] + [attempt.id]
        assignments = ", ".join(f"{name} = ?" for name in columns)
        self._conn.execute(
            f"UPDATE publish_job_attempts SET {assignments} WHERE id = ?",
            values,
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
