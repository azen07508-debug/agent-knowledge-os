"""Phase 15：发布执行器与 TIMEOUT 对账。

- PublishWorker：claim job → 开新 attempt → build/validate/publish → 按 retry
  矩阵归档；TIMEOUT 只置 TIMEOUT_UNVERIFIED，**不重试、不自动对账**；
- Reconciler：独立对账流程，用 fingerprint / provider_request_id / 时间窗 /
  内容摘要匹配平台记录；found → SUCCEEDED，not_found → FAILED，
  ambiguous → NEEDS_REVIEW（禁止自动 retry）；
- 全程不触碰 ContentObject（Workflow 恒保持 APPROVED，状态严格分离）。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Any

from runtime.platform_formatter import FormattedPayload
from runtime.publish_adapters import PublishAdapter
from runtime.publish_queue import TS, PublishJob, PublishJobStore
from runtime.retry_policy import TIMEOUT, classify, decide_retry


class PublishWorker:
    """单 worker：每次 run_once 执行一个到期 job。"""

    def __init__(
        self,
        store: PublishJobStore,
        adapters: Mapping[str, PublishAdapter],
        builder: Callable[[PublishJob], FormattedPayload],
        *,
        max_attempts: int = 3,
        default_delay: int = 60,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.adapters = dict(adapters)
        self.builder = builder
        self.max_attempts = max_attempts
        self.default_delay = default_delay
        self._clock = clock or datetime.now

    def _now(self) -> datetime:
        return self._clock()

    def run_once(self) -> dict[str, Any] | None:
        """取一个到期 job 执行；没有到期 job 返回 None。"""
        job = self.store.claim_next(self._now().strftime(TS))
        if job is None:
            return None
        return self._execute(job)

    # ── 执行 ──────────────────────────────────────────────────────────────

    def _execute(self, job: PublishJob) -> dict[str, Any]:
        attempt = self.store.start_attempt(job.id)  # 重试 = 新 attempt，不覆盖旧的

        try:
            formatted = self.builder(job)
        except Exception as exc:
            return self._fail(job, attempt, "BUILDER_ERROR", f"构建内容失败：{exc}")
        attempt.request_fingerprint = formatted.fingerprint
        self.store.save_attempt(attempt)

        adapter = self.adapters.get(job.platform)
        if adapter is None:
            return self._fail(job, attempt, "NO_ADAPTER",
                              f"{job.platform} 未配置发布适配器。")

        check = adapter.validate(formatted)
        if not check.get("ok"):
            errors = "; ".join(str(item) for item in check.get("errors") or [])
            return self._fail(job, attempt, "INVALID_PARAM", f"契约校验未通过：{errors}")

        try:
            result = adapter.publish(formatted)
        except Exception as exc:
            return self._fail(job, attempt, "UNKNOWN", f"适配器异常：{exc}")
        if not isinstance(result, Mapping) or "ok" not in result:
            return self._fail(job, attempt, "UNKNOWN", "适配器返回不符合契约（缺 ok 字段）。")

        provider_id = str(result.get("provider_request_id") or "")
        if result.get("ok"):
            post_id = str(result.get("id") or "")
            attempt.finish("SUCCEEDED", provider_request_id=provider_id or post_id)
            attempt.published_post_id = post_id
            self.store.save_attempt(attempt)
            self.store.transition(job, "SUCCEEDED")
            return {"ok": True, "job_id": job.id, "platform": job.platform,
                    "status": job.status, "attempt_no": attempt.attempt_no,
                    "post_id": post_id}

        code = str(result.get("error_code") or "UNKNOWN")
        message = str(result.get("error_message") or "")

        if classify(code, message) == TIMEOUT:
            # 超时 ≠ 失败：不重试，等对账
            attempt.finish("TIMEOUT_UNVERIFIED", error_code=code, error_message=message,
                           provider_request_id=provider_id)
            self.store.save_attempt(attempt)
            self.store.transition(job, "TIMEOUT_UNVERIFIED")
            return {"ok": False, "job_id": job.id, "platform": job.platform,
                    "status": job.status, "attempt_no": attempt.attempt_no,
                    "error_class": TIMEOUT,
                    "message": "超时未确认：禁止直接重试，必须先 reconcile（对账）。"}

        retry_after = result.get("retry_after")
        decision = decide_retry(
            code,
            message,
            retry_after=int(retry_after) if isinstance(retry_after, (int, float)) else None,
            attempt_no=attempt.attempt_no,
            max_attempts=self.max_attempts,
            default_delay=self.default_delay,
        )
        attempt.finish("FAILED", error_code=code, error_message=message,
                       provider_request_id=provider_id)
        self.store.save_attempt(attempt)
        if decision.retryable:
            job.scheduled_at = (self._now() + timedelta(seconds=decision.delay_seconds)).strftime(TS)
            self.store.transition(job, "RETRYING")
        else:
            self.store.transition(job, "FAILED")
        return {"ok": False, "job_id": job.id, "platform": job.platform,
                "status": job.status, "attempt_no": attempt.attempt_no,
                "error_class": decision.error_class, "reason": decision.reason}

    def _fail(self, job: PublishJob, attempt: Any, code: str, message: str) -> dict[str, Any]:
        """配置/构建/校验类失败：按矩阵一律不重试，直接 FAILED。"""
        attempt.finish("FAILED", error_code=code, error_message=message)
        self.store.save_attempt(attempt)
        self.store.transition(job, "FAILED")
        return {"ok": False, "job_id": job.id, "platform": job.platform,
                "status": job.status, "attempt_no": attempt.attempt_no,
                "error_class": code, "reason": message}


class Reconciler:
    """TIMEOUT 对账：独立流程，找不到/不确定都不会触发 retry。"""

    def __init__(
        self,
        store: PublishJobStore,
        adapters: Mapping[str, PublishAdapter],
        builder: Callable[[PublishJob], FormattedPayload],
        *,
        window_minutes: int = 2,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.adapters = dict(adapters)
        self.builder = builder
        self.window = timedelta(minutes=window_minutes)
        self._clock = clock or datetime.now

    def reconcile(self, job_id: str) -> dict[str, Any]:
        job = self.store.get(job_id)
        if job is None:
            return {"ok": False, "message": f"job 不存在：{job_id}"}
        if job.status not in ("TIMEOUT_UNVERIFIED", "NEEDS_REVIEW"):
            return {"ok": False, "status": job.status,
                    "message": f"只有 TIMEOUT_UNVERIFIED/NEEDS_REVIEW 可对账，当前 {job.status}。"}

        attempt = self.store.latest_attempt(job_id)
        if attempt is None or attempt.status not in ("TIMEOUT_UNVERIFIED", "NEEDS_REVIEW"):
            return {"ok": False, "status": job.status, "message": "最新 attempt 不是待对账状态。"}
        adapter = self.adapters.get(job.platform)
        if adapter is None:
            return {"ok": False, "status": job.status,
                    "message": f"{job.platform} 未配置发布适配器，无法对账（保持待对账）。"}

        # 查询条件齐了才进 RECONCILING（避免中途缺信息把状态卡死）
        now = self._now()
        query = {
            "fingerprint": attempt.request_fingerprint,
            "provider_request_id": attempt.provider_request_id,
            "window_start": self._window_start(attempt.started_at),
            "window_end": now.strftime(TS),
            "digest": self._digest(job),
        }

        self.store.transition(job, "RECONCILING")
        try:
            result = adapter.reconcile(query)
        except Exception as exc:
            return self._park(job, attempt, f"对账查询异常：{exc}")
        if not isinstance(result, Mapping) or not result.get("ok"):
            detail = str((result or {}).get("message") or (result or {}).get("error_message")
                         or "对账查询失败") if isinstance(result, Mapping) else "对账查询失败"
            return self._park(job, attempt, detail)

        status = str(result.get("status") or "")
        if status == "found":
            attempt.transition("RECONCILED_SUCCESS")
            attempt.reconciliation_status = "MATCHED"
            attempt.reconciled_at = now.strftime(TS)
            attempt.published_post_id = str(result.get("post_id") or "")
            self.store.save_attempt(attempt)
            self.store.transition(job, "SUCCEEDED")
            return {"ok": True, "job_id": job_id, "status": job.status,
                    "attempt_status": attempt.status, "post_id": attempt.published_post_id,
                    "message": "平台侧确认已发布。"}
        if status == "not_found":
            attempt.transition("RECONCILED_FAILED")
            attempt.reconciliation_status = "NOT_FOUND"
            attempt.reconciled_at = now.strftime(TS)
            self.store.save_attempt(attempt)
            self.store.transition(job, "FAILED")
            return {"ok": True, "job_id": job_id, "status": job.status,
                    "attempt_status": attempt.status,
                    "message": "平台侧确认未发布。"}
        return self._park(job, attempt, f"对账无法判定（status={status or '未知'}），保持待人工复核。")

    # ── 辅助 ──────────────────────────────────────────────────────────────

    def _now(self) -> datetime:
        return self._clock()

    def _park(self, job: PublishJob, attempt: Any, message: str) -> dict[str, Any]:
        """无法确定 → NEEDS_REVIEW，禁止自动 retry。"""
        attempt.transition("NEEDS_REVIEW")
        attempt.reconciliation_status = "AMBIGUOUS"
        self.store.save_attempt(attempt)
        self.store.transition(job, "NEEDS_REVIEW")
        return {"ok": False, "job_id": job.id, "status": job.status,
                "attempt_status": attempt.status, "message": message}

    def _window_start(self, started_at: str) -> str:
        try:
            base = datetime.strptime(started_at, TS)
        except ValueError:
            base = self._now()
        return (base - self.window).strftime(TS)

    def _digest(self, job: PublishJob) -> str:
        try:
            formatted = self.builder(job)
        except Exception:
            return ""
        from runtime.publish_adapters import payload_digest

        return payload_digest(formatted)
