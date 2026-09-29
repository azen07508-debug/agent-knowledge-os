"""Phase 14：Platform Formatter（正常输出 / 超限 / invalid / 指纹 / 六平台契约）。"""

import pytest

from runtime.canonical_post import CanonicalPost
from runtime.content_object import ContentObject
from runtime.platform_formatter import (
    FORMATTERS,
    FormattedPayload,
    get_formatter,
    x_weight,
)
from runtime.x_adapter import X_POST_LIMIT, X_THREAD_LIMIT

SIX = ["xiaohongshu", "douyin", "bilibili", "wechat_mp", "weibo", "channels"]


def post_for(platform: str, **overrides) -> CanonicalPost:
    """按平台契约造一条能过校验的 CanonicalPost。"""
    base: dict = {"title": "知识库方案", "body": "这是正文内容，讲清楚一个具体做法。", "content_id": "c1"}
    if platform in ("douyin", "bilibili", "channels"):
        base["media"] = ["/tmp/clip.mp4"]
    if platform == "bilibili":
        base["tags"] = ["知识区", "效率"]
    base.update(overrides)
    return CanonicalPost(**base)


# ── 正常输出 ────────────────────────────────────────────────────────────


def test_six_platforms_format_valid_payloads():
    for key in SIX:
        formatted = get_formatter(key).format(post_for(key))

        assert formatted.valid is True, f"{key}: {formatted.errors}"
        assert formatted.errors == []
        assert isinstance(formatted.payload, dict) and formatted.payload
        assert formatted.platform == key
        assert len(formatted.fingerprint) == 64
        assert formatted.metadata["content_id"] == "c1"
        assert formatted.metadata["dry_run"] is True


def test_payload_shapes_are_platform_specific():
    xhs = get_formatter("xiaohongshu").format(post_for("xiaohongshu", tags=["AI"]))
    douyin = get_formatter("douyin").format(post_for("douyin"))
    weibo = get_formatter("weibo").format(post_for("weibo", tags=["AI"]))

    assert set(xhs.payload) == {"title", "body", "hashtags"}
    assert xhs.payload["hashtags"] == ["#AI"] and "#AI" in xhs.payload["body"]
    assert set(douyin.payload) == {"caption", "video", "hashtags"}
    assert douyin.payload["video"] == "/tmp/clip.mp4"
    assert set(weibo.payload) == {"text", "hashtags"}  # 微博没有标题字段


def test_dry_run_flag_and_preview_output():
    formatted = get_formatter("xiaohongshu").format(post_for("xiaohongshu"))

    preview = formatted.preview()
    assert "小红书" in preview and "知识库方案" in preview

    hot = get_formatter("xiaohongshu").format(post_for("xiaohongshu"), dry_run=False)
    assert hot.metadata["dry_run"] is False  # 只是标记；Formatter 本身仍是纯函数、无写操作
    assert hot.payload == formatted.payload


# ── 超限与 invalid ──────────────────────────────────────────────────────


def test_formatter_over_title_limit():
    result = get_formatter("xiaohongshu").format(post_for("xiaohongshu", title="超" * 21))

    assert result.valid is False
    assert any("上限 20 字" in err for err in result.errors)


def test_formatter_over_body_limit():
    result = get_formatter("weibo").format(post_for("weibo", body="字" * 2001))

    assert result.valid is False
    assert any("上限 2000 字" in err for err in result.errors)


def test_formatter_invalid_payload_missing_video():
    result = get_formatter("douyin").format(post_for("douyin", media=[]))

    assert result.valid is False
    assert any("必须有媒体文件" in err for err in result.errors)


def test_canonical_post_rejects_empty_body():
    with pytest.raises(ValueError):
        CanonicalPost(body="   ")

    with pytest.raises(ValueError):
        CanonicalPost.from_content_object(
            ContentObject(topic="t", sources=["s"], evidence=[{"claim": "c", "quote": "q"}],
                          hook="h", core_content="", status="DRAFT")
        )


def test_unknown_platform_is_rejected():
    with pytest.raises(ValueError) as exc:
        get_formatter("kuaishou")

    assert "kuaishou" in str(exc.value) and "xiaohongshu" in str(exc.value)


# ── 指纹 ────────────────────────────────────────────────────────────────


def test_fingerprint_is_deterministic_and_content_sensitive():
    a = get_formatter("xiaohongshu").format(post_for("xiaohongshu"))
    b = get_formatter("xiaohongshu").format(post_for("xiaohongshu"))
    c = get_formatter("xiaohongshu").format(post_for("xiaohongshu", body="另一段正文"))
    d = get_formatter("weibo").format(post_for("weibo"))

    assert a.fingerprint == b.fingerprint       # 同内容 + 同平台 → 同指纹
    assert a.fingerprint != c.fingerprint       # 内容变 → 指纹变
    assert a.fingerprint != d.fingerprint       # 平台变 → 指纹变


def test_limits_come_from_contract_and_can_be_overridden():
    strict = get_formatter("xiaohongshu", limits={"title_max": 5})
    result = strict.format(post_for("xiaohongshu", title="一二三四五六"))

    assert result.valid is False and any("上限 5 字" in err for err in result.errors)


# ── X Thread ────────────────────────────────────────────────────────────


def test_x_formatter_splits_thread_within_contract():
    long_body = ("中文内容" * 100)  # 400+ 权重
    formatted = get_formatter("x").format(CanonicalPost(body=long_body))

    assert formatted.valid is True
    posts = formatted.payload["posts"]
    assert len(posts) >= 2
    assert all(x_weight(chunk) <= X_POST_LIMIT for chunk in posts)
    assert "X Thread" in formatted.preview()


def test_x_formatter_rejects_thread_over_20():
    huge = "\n".join(f"第{i}行" + "x" * 260 for i in range(30))  # 每行独立成条
    formatted = get_formatter("x").format(CanonicalPost(body=huge))

    assert formatted.valid is False
    assert any(f"> {X_THREAD_LIMIT}" in err for err in formatted.errors)


# ── 平台特有格式规则 ────────────────────────────────────────────────────


def test_platform_specific_warnings_are_advisory():
    bare = post_for("xiaohongshu", media=[])
    result = get_formatter("xiaohongshu").format(bare)
    assert result.valid is True and result.warnings  # 只提示，不拦截

    weibo = get_formatter("weibo").format(post_for("weibo", body="长" * 141))
    assert any("折叠" in w for w in weibo.warnings)


def test_from_content_object_bridge():
    obj = ContentObject(topic="X 跑通", core_content="第一行正文", sources=["https://s"],
                        evidence=[{"claim": "c", "quote": "q", "url": "u"}],
                        hook="h", media=["/tmp/a.png"], status="DRAFT")

    post = CanonicalPost.from_content_object(obj)

    assert post.title == "X 跑通" and post.body == "第一行正文"
    assert post.links == ["https://s"] and post.media == ["/tmp/a.png"] and post.content_id == obj.id


def test_registry_covers_x_plus_six():
    assert set(FORMATTERS) == {"x", *SIX}
    for key in FORMATTERS:
        assert isinstance(get_formatter(key).format(post_for(key if key in SIX else "x")),
                          FormattedPayload)
