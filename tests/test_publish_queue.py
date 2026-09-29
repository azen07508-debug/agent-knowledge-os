"""Phase 15：PublishJob / Attempt 数据模型与 SQLite 队列存储。"""

import pytest

from runtime.publish_queue import (
    PublishJob,
    PublishJobAttempt,
    PublishJobStore,
    idempotency_key_for,
)


def make_store(tmp_path, name="publish.sqlite3"):
    return PublishJobStore(tmp_path / name)


# ── 模型与状态机 ────────────────────────────────────────────────────────


def test_job_defaults_and_required_fields():
    job = PublishJob(content_id="c1", platform="xiaohongshu")

    assert job.status == "QUEUED" and job.id and job.created_at
    assert job.scheduled_at == job.created_at  # 默认立即到期
    with pytest.raises(ValueError):
        PublishJob(content_id="", platform="x")
    with pytest.raises(ValueError):
        PublishJob(content_id="c1", platform="x", status="WEIRD")


def test_timeout_can_never_transition_directly_to_retry():
    job = PublishJob(content_id="c1", platform="x", status="RUNNING")
    job.transition("TIMEOUT_UNVERIFIED")

    with pytest.raises(ValueError) as exc:
        job.transition("RETRYING")
    assert "TIMEOUT_UNVERIFIED → RETRYING" in str(exc.value)  # 状态机里没有这条边
    with pytest.raises(ValueError):
        job.transition("RUNNING")          # 也不能直接重跑

    job.transition("RECONCILING")          # 唯一出路：对账
    assert job.status == "RECONCILING"


def test_happy_path_and_terminal_states():
    job = PublishJob(content_id="c1", platform="x")
    for target in ("RUNNING", "SUCCEEDED"):
        job.transition(target)
    with pytest.raises(ValueError):
        job.transition("FAILED")  # 终态不可再迁


def test_needs_review_can_go_back_to_reconciling_or_die():
    job = PublishJob(content_id="c1", platform="x", status="NEEDS_REVIEW")

    job.transition("RECONCILING")
    job = PublishJob(content_id="c1", platform="x", status="NEEDS_REVIEW")
    job.transition("FAILED")


def test_attempt_state_machine_and_finish_records():
    attempt = PublishJobAttempt(job_id="j1", attempt_no=1)

    assert attempt.status == "STARTED" and attempt.reconciliation_status == "NONE"
    attempt.finish("TIMEOUT_UNVERIFIED", error_code="TIMEOUT", error_message="超时",
                   provider_request_id="req-7")
    assert attempt.provider_request_id == "req-7" and attempt.finished_at

    attempt.transition("NEEDS_REVIEW")
    attempt.transition("RECONCILED_SUCCESS")
    assert attempt.status == "RECONCILED_SUCCESS"
    with pytest.raises(ValueError):
        attempt.transition("SUCCEEDED")

    with pytest.raises(ValueError):
        PublishJobAttempt(job_id="j1", attempt_no=0)  # attempt_no 必须 ≥ 1


# ── 存储与幂等 ──────────────────────────────────────────────────────────


def test_enqueue_is_idempotent_for_same_content_platform_fingerprint(tmp_path):
    store = make_store(tmp_path)

    job1, created1 = store.enqueue("c1", "xiaohongshu", fingerprint="fp-a")
    job2, created2 = store.enqueue("c1", "xiaohongshu", fingerprint="fp-a")
    job3, created3 = store.enqueue("c1", "xiaohongshu", fingerprint="fp-b")

    assert created1 is True and created2 is False and job1.id == job2.id
    assert created3 is True and job3.id != job1.id
    assert job1.idempotency_key == idempotency_key_for("c1", "xiaohongshu", "fp-a")
    store.close()


def test_worker_restart_does_not_duplicate_job(tmp_path):
    path = tmp_path / "q.sqlite3"
    first = PublishJobStore(path)
    job, created = first.enqueue("c1", "weibo", fingerprint="fp")
    first.close()

    second = PublishJobStore(path)          # 模拟 worker 重启
    again, created_again = second.enqueue("c1", "weibo", fingerprint="fp")

    assert created is True and created_again is False and again.id == job.id
    assert len(second.list_jobs(content_id="c1")) == 1

    claimed = second.claim_next()
    assert claimed is not None and claimed.status == "RUNNING"
    assert second.claim_next() is None      # RUNNING 不会被重复认领
    second.close()


def test_claim_next_respects_schedule(tmp_path):
    store = make_store(tmp_path)
    store.enqueue("later", "weibo", scheduled_at="2099-01-01 00:00:00")
    store.enqueue("now", "weibo")

    claimed = store.claim_next()

    assert claimed is not None and claimed.content_id == "now"
    assert store.claim_next() is None


def test_attempts_are_numbered_and_never_overwritten(tmp_path):
    store = make_store(tmp_path)
    job, _ = store.enqueue("c1", "xhs")

    a1 = store.start_attempt(job.id, request_fingerprint="fp1")
    a1.finish("FAILED", error_code="500")
    store.save_attempt(a1)
    a2 = store.start_attempt(job.id, request_fingerprint="fp2")

    assert (a1.attempt_no, a2.attempt_no) == (1, 2)
    rows = store.attempts(job.id)
    assert [row.attempt_no for row in rows] == [1, 2]
    assert rows[0].status == "FAILED" and rows[0].error_code == "500"   # 旧 attempt 未被覆盖
    assert rows[1].status == "STARTED"
    assert rows[0].id != rows[1].id
    store.close()


def test_list_jobs_filters(tmp_path):
    store = make_store(tmp_path)
    store.enqueue("c1", "weibo")
    store.enqueue("c2", "weibo")
    store.enqueue("c1", "bilibili")

    assert len(store.list_jobs(content_id="c1")) == 2
    assert len(store.list_jobs(platform="bilibili")) == 1
    assert len(store.list_jobs()) == 3
    store.close()
