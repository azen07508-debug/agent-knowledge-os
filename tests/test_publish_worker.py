"""Phase 15：PublishWorker / Reconciler（16 项必测的执行侧覆盖）。"""


from runtime.canonical_post import CanonicalPost
from runtime.content_object import ContentObject
from runtime.content_store import ContentStore
from runtime.human_review import approve
from runtime.platform_formatter import get_formatter
from runtime.publish_adapters import (
    MockPublishAdapter,
    get_publish_adapter,
)
from runtime.publish_queue import PublishJobStore
from runtime.publish_worker import PublishWorker, Reconciler

PLATFORM = "xiaohongshu"


def make_post() -> CanonicalPost:
    return CanonicalPost(
        title="知识库方案",
        body="这是正文内容，讲清楚一个具体做法。",
        tags=["AI"],
        content_id="c1",
    )


def make_env(tmp_path, script=None, reconcile_result="auto", adapters=None, **worker_kwargs):
    store = PublishJobStore(tmp_path / "publish.sqlite3")
    formatted = get_formatter(PLATFORM).format(make_post())
    builder = lambda job: formatted  # noqa: E731 —— 指纹跨尝试恒定
    mock = adapters is None
    adapter_map = adapters or {PLATFORM: MockPublishAdapter(
        platform=PLATFORM, script=script or [], reconcile_result=reconcile_result
    )}
    worker = PublishWorker(store, adapter_map, builder, default_delay=0, **worker_kwargs)
    return store, worker, (adapter_map.get(PLATFORM) if mock else None)


def enqueue(store, content_id="c1", fingerprint="fp-x"):
    job, _ = store.enqueue(content_id, PLATFORM, fingerprint=fingerprint)
    return job


# ── 5/队列→执行→成功 ────────────────────────────────────────────────────


def test_queue_running_success(tmp_path):
    store, worker, mock = make_env(tmp_path)
    job = enqueue(store)

    result = worker.run_once()

    assert result["ok"] is True and result["status"] == "SUCCEEDED"
    assert store.get(job.id).status == "SUCCEEDED"
    attempts = store.attempts(job.id)
    assert len(attempts) == 1 and attempts[0].status == "SUCCEEDED"
    assert attempts[0].published_post_id and attempts[0].request_fingerprint
    assert len(mock.posts) == 1
    assert worker.run_once() is None  # 队列空了


# ── 6/4xx 不重试 ────────────────────────────────────────────────────────


def test_explicit_4xx_fails_without_retry(tmp_path):
    store, worker, _ = make_env(
        tmp_path, script=[{"ok": False, "error_code": "400", "error_message": "bad param"}]
    )
    job = enqueue(store)

    result = worker.run_once()

    assert result["ok"] is False and result["status"] == "FAILED"
    assert result["error_class"] == "INVALID_PARAM"
    attempts = store.attempts(job.id)
    assert len(attempts) == 1 and attempts[0].error_code == "400"
    assert worker.run_once() is None  # 不会再有第二次尝试


# ── 7/5xx 重试（新 attempt） ────────────────────────────────────────────


def test_5xx_retries_with_new_attempt(tmp_path):
    store, worker, _ = make_env(tmp_path, script=[
        {"ok": False, "error_code": "502", "error_message": "bad gateway"},
        {"ok": True},
    ])
    job = enqueue(store)

    first = worker.run_once()
    assert first["ok"] is False and first["status"] == "RETRYING"
    assert store.attempts(job.id)[0].status == "FAILED"

    second = worker.run_once()
    assert second["ok"] is True and second["status"] == "SUCCEEDED"

    attempts = store.attempts(job.id)
    assert [a.attempt_no for a in attempts] == [1, 2]      # 新 attempt，不覆盖
    assert attempts[0].id != attempts[1].id
    assert attempts[0].error_code == "502"                  # 旧 attempt 保留证据


def test_rate_limit_retry_uses_retry_after(tmp_path):
    store, worker, _ = make_env(tmp_path, script=[
        {"ok": False, "error_code": "RATE_LIMIT", "retry_after": 120},
        {"ok": True},
    ])
    job = enqueue(store)

    result = worker.run_once()

    assert result["status"] == "RETRYING"
    assert store.get(job.id).scheduled_at > store.get(job.id).created_at  # 延后 120s
    assert store.attempts(job.id)[0].error_code == "RATE_LIMIT"
    assert worker.run_once() is None  # 未到期，不会提前跑


def test_network_error_is_retryable(tmp_path):
    store, worker, _ = make_env(tmp_path, script=[
        {"ok": False, "error_code": "NETWORK", "error_message": "connection refused"},
        {"ok": True},
    ])
    enqueue(store)

    assert worker.run_once()["status"] == "RETRYING"
    assert worker.run_once()["status"] == "SUCCEEDED"


# ── 8/TIMEOUT 不重试 ────────────────────────────────────────────────────


def test_timeout_never_retries(tmp_path):
    store, worker, _ = make_env(tmp_path, script=[
        {"ok": False, "error_code": "TIMEOUT", "error_message": "timed out after 15s"},
    ])
    job = enqueue(store)

    result = worker.run_once()

    assert result["ok"] is False and result["status"] == "TIMEOUT_UNVERIFIED"
    assert "reconcile" in result["message"]
    attempts = store.attempts(job.id)
    assert len(attempts) == 1 and attempts[0].status == "TIMEOUT_UNVERIFIED"
    assert worker.run_once() is None          # 禁止自动重试
    assert store.get(job.id).status == "TIMEOUT_UNVERIFIED"


# ── 9/10/11/TIMEOUT → 对账 ─────────────────────────────────────────────


def run_to_timeout(tmp_path, script):
    store, worker, mock = make_env(tmp_path, script=script)
    job = enqueue(store)
    worker.run_once()
    reconciler = Reconciler(store, {PLATFORM: mock},
                            lambda j: get_formatter(PLATFORM).format(make_post()))
    return store, job, mock, reconciler


def test_timeout_reconcile_found_becomes_success(tmp_path):
    # 超时但平台侧其实已发出（opencli 真实事故的复刻）
    store, job, mock, reconciler = run_to_timeout(tmp_path, [
        {"ok": False, "error_code": "TIMEOUT", "_actually_posted": True},
    ])

    result = reconciler.reconcile(job.id)

    assert result["ok"] is True and result["status"] == "SUCCEEDED"
    attempt = store.attempts(job.id)[0]
    assert attempt.status == "RECONCILED_SUCCESS"
    assert attempt.reconciliation_status == "MATCHED"
    assert attempt.published_post_id and attempt.reconciled_at
    query = mock.reconcile_calls[0]
    assert query["fingerprint"] and query["window_start"] < query["window_end"]


def test_timeout_reconcile_not_found_becomes_failed(tmp_path):
    store, job, _, reconciler = run_to_timeout(tmp_path, [
        {"ok": False, "error_code": "TIMEOUT", "error_message": "no response"},
    ])

    result = reconciler.reconcile(job.id)

    assert result["status"] == "FAILED"
    attempt = store.attempts(job.id)[0]
    assert attempt.status == "RECONCILED_FAILED"
    assert attempt.reconciliation_status == "NOT_FOUND"


def test_timeout_reconcile_ambiguous_parks_for_review(tmp_path):
    store, job, _, reconciler = run_to_timeout(
        tmp_path, [{"ok": False, "error_code": "TIMEOUT", "_actually_posted": True}]
    )
    # 让自动匹配返回「无法判定」
    reconciler.adapters[PLATFORM].reconcile_result = "ambiguous"

    result = reconciler.reconcile(job.id)

    assert result["ok"] is False and result["status"] == "NEEDS_REVIEW"
    attempt = store.attempts(job.id)[0]
    assert attempt.status == "NEEDS_REVIEW"
    assert attempt.reconciliation_status == "AMBIGUOUS"
    assert store.claim_next() is None        # 禁止自动 retry（不再是 QUEUED/RETRYING）


def test_reconciler_requires_pending_timeout_status(tmp_path):
    store, worker, mock = make_env(tmp_path)
    job = enqueue(store)
    worker.run_once()                          # 直接成功的 job
    reconciler = Reconciler(store, {PLATFORM: mock},
                            lambda j: get_formatter(PLATFORM).format(make_post()))

    result = reconciler.reconcile(job.id)

    assert result["ok"] is False and "可对账" in result["message"]
    assert store.get(job.id).status == "SUCCEEDED"  # 状态不被误改


def test_needs_review_can_be_reconciled_again(tmp_path):
    store, job, _mock, reconciler = run_to_timeout(tmp_path, [
        {"ok": False, "error_code": "TIMEOUT", "_actually_posted": True},
    ])
    reconciler.adapters[PLATFORM].reconcile_result = "ambiguous"
    reconciler.reconcile(job.id)
    reconciler.adapters[PLATFORM].reconcile_result = "found"  # 人工复核后重跑

    result = reconciler.reconcile(job.id)

    assert result["ok"] is True and result["status"] == "SUCCEEDED"
    assert store.attempts(job.id)[0].status == "RECONCILED_SUCCESS"


# ── 12/Workflow 与 Job 状态分离 ─────────────────────────────────────────


def make_approved_content(store: ContentStore) -> ContentObject:
    obj = ContentObject(
        topic="发布失败也不动审核状态",
        sources=["https://s"],
        evidence=[{"claim": "c", "quote": "q", "url": "u"}],
        hook="h",
        core_content="正文内容足够长了。",
        status="IDEA",
    )
    store.save(obj)
    for target in ("RESEARCHED", "DRAFT", "REVIEW"):
        store.transition(obj.id, target)
    approve(store, obj.id, reviewer="admin", note="测试审核通过")
    return obj


def test_workflow_stays_approved_when_publish_fails(tmp_path):
    content_store = ContentStore(tmp_path / "content.sqlite3")
    obj = make_approved_content(content_store)
    store, worker, _ = make_env(
        tmp_path, script=[{"ok": False, "error_code": "400", "error_message": "bad"}]
    )
    store.enqueue(obj.id, PLATFORM, fingerprint="fp-x")

    result = worker.run_once()

    assert result is not None and result["ok"] is False and result["status"] == "FAILED"
    stored = content_store.get(obj.id)
    assert stored is not None and stored.status == "APPROVED"   # 发布失败绝不改 Workflow


# ── 13/15/幂等 ─────────────────────────────────────────────────────────


def test_same_fingerprint_enqueue_is_idempotent_across_workers(tmp_path):
    from runtime.publish_queue import PublishJobStore

    path = tmp_path / "q.sqlite3"
    first = PublishJobStore(path)
    job, created = first.enqueue("c1", PLATFORM, fingerprint="fp-same")
    first.close()

    restarted = PublishJobStore(path)
    again, created_again = restarted.enqueue("c1", PLATFORM, fingerprint="fp-same")

    assert created and not created_again and again.id == job.id
    assert len(restarted.list_jobs()) == 1
    restarted.close()


def test_worker_restart_does_not_rerun_claimed_job(tmp_path):
    store, _worker, _ = make_env(tmp_path)
    enqueue(store)
    store.claim_next()                          # 第一个 worker 认领后崩溃

    store2 = PublishJobStore(tmp_path / "publish.sqlite3")   # 重启：重新打开存储
    assert store2.claim_next() is None          # RUNNING 不会被第二个 worker 抢走
    store2.close()


# ── 16/Mock 端到端 ──────────────────────────────────────────────────────


def test_mock_end_to_end_flow(tmp_path):
    content_store = ContentStore(tmp_path / "content.sqlite3")
    obj = make_approved_content(content_store)

    store = PublishJobStore(tmp_path / "publish.sqlite3")
    mock = MockPublishAdapter(platform=PLATFORM)
    post = CanonicalPost.from_content_object(obj)
    formatted = get_formatter(PLATFORM).format(post)
    worker = PublishWorker(store, {PLATFORM: mock}, lambda job: formatted, default_delay=0)

    job, created = store.enqueue(obj.id, PLATFORM, fingerprint=formatted.fingerprint)
    assert created is True

    result = worker.run_once()

    assert result is not None and result["ok"] is True and result["status"] == "SUCCEEDED"
    assert mock.publish_calls[0]["fingerprint"] == formatted.fingerprint
    assert store.attempts(job.id)[0].provider_request_id == result["post_id"]
    # Workflow 独立：内容状态不被队列触碰
    stored = content_store.get(obj.id)
    assert stored is not None and stored.status == "APPROVED"


# ── contract-only 平台诚实失败 ──────────────────────────────────────────


def test_contract_only_adapter_refuses_to_fake_success():
    adapter = get_publish_adapter("weibo")
    formatted = get_formatter("weibo").format(
        CanonicalPost(body="微博正文", content_id="c1")
    )

    assert adapter.validate(formatted)["ok"] is True
    published = adapter.publish(formatted)
    assert published["ok"] is False and published["error_code"] == "NOT_IMPLEMENTED"
    assert adapter.reconcile({"fingerprint": "fp"})["ok"] is False


def test_contract_only_publish_fails_job_honestly(tmp_path):
    contract = get_publish_adapter(PLATFORM)
    store, worker, _ = make_env(tmp_path, adapters={PLATFORM: contract})
    job = enqueue(store)

    result = worker.run_once()

    assert result["ok"] is False and result["status"] == "FAILED"
    assert result["error_class"] == "NOT_IMPLEMENTED"
    assert store.attempts(job.id)[0].error_code == "NOT_IMPLEMENTED"
    assert worker.run_once() is None            # contract-only 不重试


def test_builder_error_fails_without_retry(tmp_path):
    def broken_builder(job):
        raise RuntimeError("内容缺失")

    store = PublishJobStore(tmp_path / "publish.sqlite3")
    worker = PublishWorker(store, {PLATFORM: MockPublishAdapter(platform=PLATFORM)},
                           broken_builder, default_delay=0)
    job = enqueue(store)

    result = worker.run_once()

    assert result is not None and result["status"] == "FAILED" and result["error_class"] == "BUILDER_ERROR"
    assert len(store.attempts(job.id)) == 1
    assert worker.run_once() is None
