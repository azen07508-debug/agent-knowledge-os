"""四支关系事实的确定性测试。"""

from engines.bazi.sxtwl_provider import _relations


def test_pair_relations_are_labeled_without_interpretation():
    result = _relations(("子", "午", "卯", "酉"))

    assert "六冲" in {item["type"] for item in result}
    assert "相破" in {item["type"] for item in result}
    assert all("pillars" in item and "branches" in item for item in result)


def test_self_punishment_requires_repeated_branch():
    assert any(item["type"] == "自刑" for item in _relations(("午", "午", "子", "卯")))
    assert not any(item["type"] == "自刑" for item in _relations(("午", "子", "辰", "卯")))


def test_mutual_punishment_is_reported_as_fact():
    result = _relations(("寅", "巳", "申", "子"))

    assert any(item["type"] == "三刑" for item in result)
