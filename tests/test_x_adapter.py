"""Phase 10：XAdapter（全部 X API 逻辑的唯一入口）。"""

from runtime.x_adapter import NOT_CONFIGURED, XAdapter

TWEET = "冷暖热三层结构，热层 3 条规则 https://example.com/pic"


class StubBackend:
    """可编排的假后端：记录调用、可指定第几条 post 失败。"""

    def __init__(self, fail_at_post: int | None = None, boom: bool = False) -> None:
        self.calls: list[tuple] = []
        self.fail_at_post = fail_at_post
        self.boom = boom
        self.posted = 0

    def search(self, query: str, limit: int):
        self.calls.append(("search", query, limit))
        if self.boom:
            raise RuntimeError("x-mcp 连接被拒")
        return {
            "ok": True,
            "items": [
                {
                    "id_str": "123",
                    "screen_name": "dev",
                    "full_text": TWEET,
                    "created_at": "2026-09-29 10:00:00",
                },
                {"id_str": "", "screen_name": "", "full_text": ""},  # 空项应被丢掉
            ],
        }

    def timeline(self, limit: int):
        self.calls.append(("timeline", limit))
        return {"ok": True, "items": [{"url": "https://x.com/i/1", "text": "t"}]}

    def mentions(self, limit: int):
        self.calls.append(("mentions", limit))
        return {"ok": True, "items": []}

    def post(self, text: str):
        self.calls.append(("post", text))
        self.posted += 1
        if self.fail_at_post is not None and self.posted >= self.fail_at_post:
            return {"ok": False, "message": "X API 拒绝：重复内容"}
        return {"ok": True, "id": f"p{self.posted}"}

    def schedule(self, text: str, at: str):
        self.calls.append(("schedule", text, at))
        return {"ok": True, "job": "job-1"}

    def analytics(self, post_id: str):
        self.calls.append(("analytics", post_id))
        return {"ok": True, "metrics": {"likes": 3}}


# ── 未配置：如实失败 ────────────────────────────────────────────────────


def test_unconfigured_adapter_fails_every_call_with_clear_message():
    adapter = XAdapter()

    assert adapter.configured is False
    for result in (
        adapter.search("q"),
        adapter.timeline(),
        adapter.mentions(),
        adapter.post("内容"),
        adapter.thread(["内容"]),
        adapter.schedule("内容", "2026-09-30 09:00"),
        adapter.analytics("p1"),
    ):
        assert result["ok"] is False
        assert "未配置" in result["message"]


def test_read_calls_do_not_need_dry_run():
    adapter = XAdapter(backend=StubBackend())

    result = adapter.search("obsidian", limit=5)

    assert result["ok"] is True and result["count"] == 1
    item = result["items"][0]
    assert item["url"] == "123" and item["author"] == "dev"  # 字段归一化
    assert item["text"] == TWEET and item["time"] == "2026-09-29 10:00:00"


def test_timeline_and_mentions_pass_through():
    adapter = XAdapter(backend=StubBackend())

    assert adapter.timeline()["ok"] is True
    assert adapter.mentions()["items"] == []


# ── 写：默认演练，显式才真发 ───────────────────────────────────────────


def test_post_defaults_to_dry_run_and_does_not_touch_backend():
    backend = StubBackend()
    adapter = XAdapter(backend=backend)

    result = adapter.post("要发的内容")

    assert result["ok"] is True and result["dry_run"] is True
    assert "未真实发送" in result["message"]
    assert backend.posted == 0


def test_post_real_send_requires_explicit_dry_run_false():
    backend = StubBackend()
    adapter = XAdapter(backend=backend, dry_run=False)

    result = adapter.post("要发的内容")

    assert result["ok"] is True and result.get("id") == "p1"
    assert backend.posted == 1


def test_dry_run_override_works_both_ways():
    backend = StubBackend()

    assert XAdapter(backend=backend).post("x", dry_run=False)["ok"] is True
    assert backend.posted == 1
    assert XAdapter(backend=backend, dry_run=False).post("x", dry_run=True)["dry_run"] is True
    assert backend.posted == 1  # 第二次没真发


def test_post_rejects_empty_and_overlong_text():
    backend = StubBackend()
    adapter = XAdapter(backend=backend, dry_run=False)

    assert "内容为空" in adapter.post("   ")["message"]
    assert "超长" in adapter.post("x" * 281)["message"]
    assert backend.posted == 0


# ── Thread ─────────────────────────────────────────────────────────────


def test_thread_dry_run_echoes_posts_without_sending():
    backend = StubBackend()
    adapter = XAdapter(backend=backend)

    result = adapter.thread(["钩子", "正文", "来源"])

    assert result["ok"] is True and result["dry_run"] is True
    assert result["ids"] == [] and backend.posted == 0


def test_thread_sends_in_order_and_collects_ids():
    backend = StubBackend()
    adapter = XAdapter(backend=backend, dry_run=False)

    result = adapter.thread(["钩子", "正文", "来源"])

    assert result["ok"] is True and result["ids"] == ["p1", "p2", "p3"]
    assert [call[1] for call in backend.calls if call[0] == "post"] == ["钩子", "正文", "来源"]


def test_thread_partial_failure_stops_and_reports_progress():
    backend = StubBackend(fail_at_post=2)
    adapter = XAdapter(backend=backend, dry_run=False)

    result = adapter.thread(["钩子", "正文", "第三条"])

    assert result["ok"] is False
    assert result["posted"] == 1 and result["ids"] == ["p1"]
    assert "第 2/3 条发送失败" in result["message"]
    assert backend.posted == 2  # 第三条没有继续发


def test_thread_input_validation():
    adapter = XAdapter(backend=StubBackend(), dry_run=False)

    assert "没有内容" in adapter.thread([])["message"]
    assert "为空" in adapter.thread(["钩子", "  "])["message"]
    assert "超长" in adapter.thread(["钩子", "x" * 281])["message"]
    assert "过长" in adapter.thread(["x"] * 21)["message"]


# ── Schedule / Analytics ──────────────────────────────────────────────


def test_schedule_dry_run_then_real():
    backend = StubBackend()
    adapter = XAdapter(backend=backend)

    dry = adapter.schedule("内容", "2026-09-30 09:00")
    assert dry["ok"] is True and dry["dry_run"] is True and backend.calls == []

    real = adapter.schedule("内容", "2026-09-30 09:00", dry_run=False)
    assert real["ok"] is True and real["job"] == "job-1"
    assert adapter.schedule("", "2026-09-30")["ok"] is False


def test_analytics_returns_metrics():
    adapter = XAdapter(backend=StubBackend())

    result = adapter.analytics("p1")

    assert result["ok"] is True and result["metrics"] == {"likes": 3}
    assert adapter.analytics("")["ok"] is False


# ── 后端异常：不假装成功 ───────────────────────────────────────────────


def test_backend_exception_becomes_failure_result():
    adapter = XAdapter(backend=StubBackend(boom=True))

    result = adapter.search("q")

    assert result["ok"] is False and "调用失败" in result["message"]


def test_backend_missing_method_reported():
    adapter = XAdapter(backend=object())

    result = adapter.post("内容", dry_run=False)

    assert result["ok"] is False and "未实现 post" in result["message"]


def test_backend_wrong_return_type_reported():
    class BadBackend:
        def post(self, text: str):
            return "done"

    result = XAdapter(backend=BadBackend()).post("内容", dry_run=False)

    assert result["ok"] is False and "应为 dict" in result["message"]
