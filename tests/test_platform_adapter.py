"""Phase 13：国内平台统一适配层（六平台契约 / 校验规则 / backend 诚实降级）。"""

import pytest

from runtime.platform_adapter import (
    SPECS,
    BilibiliAdapter,
    ChannelsAdapter,
    DouyinAdapter,
    WechatMpAdapter,
    WeiboAdapter,
    XiaohongshuAdapter,
    get_adapter,
)

ALL_KEYS = ["xiaohongshu", "douyin", "bilibili", "wechat_mp", "weibo", "channels"]


class StubBackend:
    """同名方法返回 {"ok": ...} 的 backend 契约桩。"""

    def __init__(self, ok=True, fail_method=None, boom_method=None, bad_contract_method=None):
        self.ok = ok
        self.fail_method = fail_method
        self.boom_method = boom_method
        self.bad_contract_method = bad_contract_method
        self.calls = []

    def _respond(self, method, payload, extra=None):
        self.calls.append((method, payload))
        if method == self.boom_method:
            raise RuntimeError("网络断了")
        if method == self.bad_contract_method:
            return {"result": "不合规"}
        if method == self.fail_method:
            return {"ok": False, "message": f"{method} 被平台拒绝"}
        return {"ok": self.ok, "id": "p1", "url": "https://e/p1", **(extra or {})}

    def publish(self, draft):
        return self._respond("publish", {"title": draft.title, "body": draft.body})

    def schedule(self, draft, at):
        return self._respond("schedule", {"at": at})

    def get_status(self, draft_id):
        return self._respond("get_status", {"draft_id": draft_id}, extra={"status": "PUBLISHED"})

    def get_analytics(self, draft_id):
        return self._respond("get_analytics", {"draft_id": draft_id}, extra={"metrics": {"likes": 1}})


def xhs_draft(**overrides):
    base = {"title": "知识库方案", "body": "正文内容", "tags": ["obsidian"], "media": []}
    base.update(overrides)
    adapter = XiaohongshuAdapter()
    return adapter.create_draft(base)


# ── 注册表 ──────────────────────────────────────────────────────────────


def test_registry_covers_six_platforms():
    for key in ALL_KEYS:
        assert get_adapter(key).platform == key
    assert isinstance(get_adapter("Xiaohongshu"), XiaohongshuAdapter)  # 大小写不敏感


def test_registry_unknown_platform_lists_options():
    with pytest.raises(ValueError) as exc:
        get_adapter("kuaishou")

    assert "kuaishou" in str(exc.value) and "xiaohongshu" in str(exc.value)


def test_six_specs_exist_and_labels_are_chinese():
    assert set(SPECS) == set(ALL_KEYS)
    for spec in SPECS.values():
        assert spec.label and any("一" <= ch <= "鿿" for ch in spec.label)


# ── create_draft ────────────────────────────────────────────────────────


def test_create_draft_falls_back_to_topic_and_core_content():
    adapter = WeiboAdapter()

    draft = adapter.create_draft({"topic": "X 渠道跑通", "core_content": "第一行\n第二行", "tags": ["#AI"]})

    assert draft.title == "X 渠道跑通" and draft.body == "第一行\n第二行"
    assert draft.tags == ["AI"] and draft.platform == "weibo"
    assert draft.id and draft.created_at and draft.status == "DRAFT"


def test_create_draft_requires_body():
    with pytest.raises(ValueError):
        XiaohongshuAdapter().create_draft({"title": "只有标题"})


def test_create_draft_carries_content_id_and_media():
    draft = BilibiliAdapter().create_draft(
        {"body": "简介", "title": "标题", "content_id": "abc123", "media": ["/tmp/a.mp4"]}
    )

    assert draft.content_id == "abc123" and draft.media == ["/tmp/a.mp4"]


# ── validate ────────────────────────────────────────────────────────────


def test_validate_passes_a_good_draft():
    result = XiaohongshuAdapter().validate(xhs_draft())

    assert result == {"ok": True, "platform": "xiaohongshu", "errors": []}


def test_validate_title_limit_is_enforced_in_characters():
    ok = xhs_draft(title="一" * 20)
    over = xhs_draft(title="一" * 21)

    assert XiaohongshuAdapter().validate(ok)["ok"] is True
    result = XiaohongshuAdapter().validate(over)
    assert result["ok"] is False and "上限 20 字" in result["errors"][0]


def test_validate_requires_title_only_where_platform_needs_it():
    xhs = xhs_draft(title="")
    weibo = WeiboAdapter().create_draft({"body": "微博不需要标题", "title": ""})

    assert XiaohongshuAdapter().validate(xhs)["ok"] is False
    assert WeiboAdapter().validate(weibo)["ok"] is True


def test_validate_body_and_tag_limits():
    over_body = WeiboAdapter().create_draft({"body": "字" * 2001})
    over_tags = xhs_draft(tags=[f"t{i}" for i in range(11)])

    assert "上限 2000 字" in WeiboAdapter().validate(over_body)["errors"][0]
    assert "上限 10 个" in XiaohongshuAdapter().validate(over_tags)["errors"][0]


def test_validate_video_platforms_require_media():
    no_media = DouyinAdapter().create_draft({"body": "口播文案", "title": ""})
    with_media = DouyinAdapter().create_draft({"body": "口播文案", "media": ["/tmp/v.mp4"]})

    assert DouyinAdapter().validate(no_media)["ok"] is False
    assert DouyinAdapter().validate(with_media)["ok"] is True  # 抖音不要求标题
    assert BilibiliAdapter().validate(
        BilibiliAdapter().create_draft({"title": "t", "body": "b", "media": ["/tmp/v.mp4"]})
    )["ok"] is True


def test_validate_platform_mismatch_is_an_error():
    draft = xhs_draft()

    result = DouyinAdapter().validate(draft)

    assert result["ok"] is False and "平台不符" in result["errors"][0]


def test_validate_limits_can_be_overridden():
    adapter = XiaohongshuAdapter(limits={"title_max": 5})

    result = adapter.validate(xhs_draft(title="一二三四五六"))

    assert result["ok"] is False and "上限 5 字" in result["errors"][0]


def test_validate_unlimited_body_when_limit_is_zero():
    draft = WechatMpAdapter().create_draft({"title": "标题", "body": "长" * 5000})

    assert WechatMpAdapter().validate(draft)["ok"] is True  # 公众号正文不设本地上限


# ── publish ─────────────────────────────────────────────────────────────


def test_publish_rejects_invalid_draft_before_touching_backend():
    backend = StubBackend()
    adapter = XiaohongshuAdapter(backend=backend)

    result = adapter.publish(xhs_draft(title=""), dry_run=False)

    assert result["ok"] is False and result["errors"] and backend.calls == []


def test_publish_dry_run_needs_no_backend_and_keeps_status():
    adapter = XiaohongshuAdapter()
    draft = xhs_draft()

    result = adapter.publish(draft)

    assert result["ok"] is True and result["dry_run"] is True
    assert result["preview"]["title"] == draft.title
    assert draft.status == "DRAFT"  # 演练不改状态


def test_publish_without_backend_is_anhonest_failure():
    adapter = XiaohongshuAdapter()
    draft = xhs_draft()

    result = adapter.publish(draft, dry_run=False)

    assert result["ok"] is False and "后端未配置" in result["message"]
    assert draft.status == "DRAFT"


def test_publish_with_backend_sends_and_marks_published():
    backend = StubBackend()
    adapter = XiaohongshuAdapter(backend=backend)
    draft = xhs_draft()

    result = adapter.publish(draft, dry_run=False)

    assert result["ok"] is True and result["id"] == "p1" and draft.status == "PUBLISHED"
    method, payload = backend.calls[0]
    assert method == "publish" and payload["title"] == draft.title


def test_publish_backend_rejection_keeps_status():
    backend = StubBackend(fail_method="publish")
    adapter = WeiboAdapter(backend=backend)
    draft = WeiboAdapter().create_draft({"body": "内容"})

    result = adapter.publish(draft, dry_run=False)

    assert result["ok"] is False and "被平台拒绝" in result["message"]
    assert draft.status == "DRAFT"


# ── schedule / getStatus / getAnalytics ─────────────────────────────────


def test_schedule_dry_run_and_real():
    adapter = BilibiliAdapter()
    draft = adapter.create_draft({"title": "t", "body": "b", "media": ["/tmp/v.mp4"]})

    dry = adapter.schedule(draft, "2026-10-01 09:00")
    assert dry["ok"] is True and dry["dry_run"] is True and dry["at"] == "2026-10-01 09:00"

    real = adapter.schedule(draft, "2026-10-01 09:00", dry_run=False)
    assert real["ok"] is False and "后端未配置" in real["message"]


def test_status_and_analytics_need_backend_but_work_when_given():
    adapter = WeiboAdapter()
    draft = WeiboAdapter().create_draft({"body": "内容"})

    no_backend = adapter.get_status(draft.id)
    assert no_backend["ok"] is False and "后端未配置" in no_backend["message"]
    assert adapter.get_analytics(draft.id)["ok"] is False

    with_backend = WeiboAdapter(backend=StubBackend())
    assert with_backend.get_status(draft.id)["ok"] is True
    assert with_backend.get_analytics(draft.id)["metrics"] == {"likes": 1}


def test_backend_without_method_says_so():
    class OnlyStatus:
        def get_status(self, draft_id):
            return {"ok": True, "status": "PUBLISHED"}

    adapter = ChannelsAdapter(backend=OnlyStatus())
    draft = ChannelsAdapter().create_draft({"title": "t", "body": "b", "media": ["/tmp/v.mp4"]})

    result = adapter.publish(draft, dry_run=False)

    assert result["ok"] is False and "没有 publish 方法" in result["message"]
    assert adapter.get_status(draft.id)["ok"] is True


def test_backend_exception_and_bad_contract_become_failures():
    boom = DouyinAdapter(backend=StubBackend(boom_method="schedule"))
    bad = DouyinAdapter(backend=StubBackend(bad_contract_method="publish"))
    draft = DouyinAdapter().create_draft({"body": "口播", "media": ["/tmp/v.mp4"]})

    raised = boom.schedule(draft, "2026-10-01", dry_run=False)
    assert raised["ok"] is False and "调用失败" in raised["message"]

    malformed = bad.publish(draft, dry_run=False)
    assert malformed["ok"] is False and "契约" in malformed["message"]
