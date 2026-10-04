from scripts.create_aihot_review import _titles


def test_aihot_review_title_candidates_are_not_empty_or_fake_experience():
    titles = _titles({"topic": "一个 AI 工具更新"})
    assert len(titles) == 3
    assert all(title.strip() for title in titles)
    assert all("实测" not in title for title in titles)
