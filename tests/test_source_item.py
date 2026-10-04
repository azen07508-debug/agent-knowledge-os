from runtime.source_item import SourceItem


def test_source_item_normalizes_common_source_fields():
    item = SourceItem.from_aihot({
        "title": "工具更新",
        "summary": "一个工具发布新能力。",
        "source": {"name": "Example"},
        "publishedAt": "2026-10-04T08:00:00Z",
        "links": {"original": "https://example.com/item"},
    })
    assert item.source == "Example"
    assert item.title == "工具更新"
    assert item.url == "https://example.com/item"
    assert item.published_at == "2026-10-04T08:00:00Z"
    assert item.source_type == "aihot"


def test_source_item_requires_a_url():
    try:
        SourceItem.from_aihot({"title": "无链接"})
    except ValueError as exc:
        assert "URL" in str(exc)
    else:
        raise AssertionError("expected missing URL rejection")
