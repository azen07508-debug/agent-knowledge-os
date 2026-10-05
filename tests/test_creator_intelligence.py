from runtime.creator_intelligence import extract_creator_profile


def test_extract_creator_profile_keeps_structure_not_original_text():
    profile = extract_creator_profile([{
        "author": "creator-a",
        "url": "https://example.com/archive",
        "title": "别再收藏工具了，这 3 个真正解决麻烦",
        "text": "我本来以为只是一个小工具。\n\n结果它解决了每天重复的问题。\n\n传送门：https://example.com/tool",
        "likes": 20,
        "replies": 3,
        "views": 1000,
    }])
    assert profile.author == "creator-a"
    assert profile.source_urls == ("https://example.com/archive",)
    assert profile.samples == 1
    assert profile.hook_pattern
    assert profile.cta_pattern
    assert "每天重复的问题" not in str(profile)


def test_small_sample_is_observed_not_confirmed():
    profile = extract_creator_profile([{"author": "a", "title": "标题", "text": "正文"}])
    assert profile.status in ("HYPOTHESIS", "OBSERVED")
    assert profile.status != "CONFIRMED"


def test_missing_engagement_is_unknown():
    profile = extract_creator_profile([{"author": "a", "title": "标题", "text": "正文"}])
    assert profile.engagement == "UNKNOWN"
