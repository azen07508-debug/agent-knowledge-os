"""Phase 9：内容生产规则（大纲 / 起草 / 三道检查）。"""

from runtime.content_draft import (
    ai_flavor_check,
    all_checks_passed,
    build_outline,
    draft_thread,
    fact_check,
    style_check,
)

CANDIDATE = {
    "topic": "Obsidian 记忆分层",
    "angle": "冷暖热三层实测",
    "audience": "开发者",
    "facts": ["热层 3 条规则", "冷层放原始收藏"],
    "opinions": ["建议先做检索"],
    "sources": ["https://a.com/1", "https://a.com/2"],
}


# ── 大纲与起草 ──────────────────────────────────────────────────────────


def test_outline_covers_problem_facts_angle_conclusion():
    outline = build_outline(CANDIDATE)

    assert outline[0].startswith("问题：")
    assert "事实：热层 3 条规则" in outline
    assert "观点：建议先做检索" in outline
    assert any(line.startswith("角度：") for line in outline)
    assert outline[-1].startswith("结论：")
    assert sum(line.startswith("事实：") for line in outline) <= 3  # 事实最多 3 条


def test_draft_thread_starts_with_hook_and_stays_under_limit():
    outline = build_outline(CANDIDATE)

    posts = draft_thread(CANDIDATE, outline)

    assert posts[0] == "冷暖热三层实测"
    assert all(len(post) <= 280 for post in posts)
    assert any(post.startswith("来源：") for post in posts)


def test_draft_truncates_overlong_lines():
    long_candidate = {**CANDIDATE, "angle": "长" * 400}

    posts = draft_thread(long_candidate, build_outline(long_candidate))

    assert len(posts[0]) == 280 and posts[0].endswith("…")


def test_injected_drafter_overrides_template():
    posts = draft_thread(CANDIDATE, build_outline(CANDIDATE), drafter=lambda **kw: ["定制首条", "定制第二条"])

    assert posts == ["定制首条", "定制第二条"]


# ── 事实核查 ────────────────────────────────────────────────────────────


def test_fact_check_finds_traceable_claims():
    result = fact_check(
        ["热层 3 条规则"],
        [{"url": "https://a.com/1", "quote": "冷暖热三层，热层 3 条规则"}],
    )

    assert result["ok"] is True and result["supported"] == 1
    assert result["items"][0]["status"] == "supported"


def test_fact_check_marks_untraceable_claims():
    result = fact_check(
        ["来源里没有的断言"],
        [{"url": "https://a.com/1", "quote": "完全无关的摘录"}],
    )

    assert result["ok"] is False
    assert result["items"][0]["status"] == "unverifiable"  # 找不到出处，不冒充「证伪」


def test_fact_check_with_no_claims_passes():
    assert fact_check([], [])["ok"] is True


# ── 风格检查 ────────────────────────────────────────────────────────────


def test_style_check_passes_clean_thread():
    assert style_check(["钩子", "正文", "来源：https://a.com/1"], banned_words=["收益承诺"])["ok"] is True


def test_style_check_flags_crowded_colon_layout():
    text = "核心方法：" + "这是一段被挤在冒号后面的长说明。" * 20
    result = style_check([text])
    assert result["ok"] is False
    assert any("排版过密" in issue for issue in result["issues"])


def test_style_check_handles_empty_first_post_without_index_error():
    result = style_check(["", "正文"])
    assert result["ok"] is False
    assert any("Hook" in issue or "标题" in issue for issue in result["issues"])


def test_draft_thread_uses_title_candidate_as_human_hook():
    posts = draft_thread({
        "topic": "工具",
        "title_candidates": ["别再收藏工具了，先解决一个真实麻烦"],
        "angle": "从资料整理开始",
        "audience": "开发者",
    }, [])
    assert posts[0].startswith("别再收藏工具了")
    assert "资料整理" in posts[0]


def test_style_check_flags_overlong_post():
    result = style_check(["钩子", "x" * 281])

    assert result["ok"] is False
    assert any("超长" in issue for issue in result["issues"])


def test_style_check_flags_banned_words():
    result = style_check(["跟着我做就能收益承诺翻倍"], banned_words=["收益承诺"])

    assert result["ok"] is False
    assert any("禁用词" in issue for issue in result["issues"])


def test_style_check_flags_empty_thread():
    assert style_check([])["ok"] is False
    assert style_check(["   "])["ok"] is False


# ── AI 味检查 ───────────────────────────────────────────────────────────


def test_ai_flavor_check_flags_boilerplate():
    result = ai_flavor_check("首先，我们要深入探讨；总之，希望本文对你有帮助。")

    assert result["ok"] is False
    assert "首先" in result["hits"] and "总之" in result["hits"]


def test_ai_flavor_check_passes_plain_text():
    assert ai_flavor_check("冷层放收藏，热层放规则，3 条就够。")["ok"] is True


def test_all_checks_passed_aggregates():
    checks = {"a": {"ok": True}, "b": {"ok": False}}

    assert all_checks_passed(checks) is False
    assert all_checks_passed({"a": {"ok": True}, "b": {"ok": True}}) is True
