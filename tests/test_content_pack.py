from runtime.content_draft import style_check
from runtime.content_pack import (
    as_recommendation,
    content_object_from_pack,
    goose_public_research_pack,
)


def test_goose_pack_is_explicitly_public_research_not_fake_experience():
    pack = goose_public_research_pack()
    assert pack["evidence_status"] == "PUBLIC_SOURCES"
    assert "未完成本地实测" in pack["content_source"]
    assert len(pack["title_candidates"]) >= 3
    assert len(pack["sources"]) >= 2


def test_goose_pack_thread_is_publishable_shape():
    pack = goose_public_research_pack()
    result = style_check(pack["posts"])
    assert result["ok"] is True, result
    assert len(pack["posts"]) <= 20


def test_pack_can_feed_content_pipeline():
    pack = goose_public_research_pack()
    recommendation = as_recommendation(pack)
    assert recommendation["topic"] == pack["topic"]
    assert recommendation["evidence"] == pack["evidence"]
    assert recommendation["title_candidates"] == pack["title_candidates"]


def test_pack_creates_review_only_draft():
    obj = content_object_from_pack(goose_public_research_pack())
    assert obj.status == "REVIEW"
    assert obj.evidence_status == "PUBLIC_SOURCES"
    assert obj.platform_versions["X"]
    assert obj.review_notes[-1]["action"] == "content_pack_created"
    assert obj.platform_posts["X"] == goose_public_research_pack()["posts"]
