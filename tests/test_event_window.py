"""事件窗口查询测试。"""

from datetime import date
from itertools import pairwise

import pytest
from fastapi.testclient import TestClient

from api.server import app
from engines.bazi import BirthInput, SxtwlBaziProvider
from engines.bazi.event_window import event_windows

client = TestClient(app)


def chart():
    return SxtwlBaziProvider().calculate(BirthInput(1990, 2, 1, 12, gender="男"))


def payload():
    return {
        "year": 1990,
        "month": 2,
        "day": 1,
        "hour": 12,
        "gender": "男",
    }


def test_event_windows_list_clash_periods_for_a_year():
    windows = event_windows(chart(), 2024, "六冲")

    assert [window.earthly_branch for window in windows] == ["卯", "未", "亥", "子"]
    assert [window.solar_term for window in windows] == ["惊蛰", "小暑", "立冬", "大雪"]
    assert [window.matched for window in windows] == [
        (("六冲", "酉"),),
        (("六冲", "丑"),),
        (("六冲", "巳"),),
        (("六冲", "午"),),
    ]


def test_event_windows_filter_by_relation():
    windows = event_windows(chart(), 2024, "六合")

    assert [window.earthly_branch for window in windows] == ["辰", "未", "申", "子"]


def test_event_windows_have_ordered_boundaries_and_source():
    windows = event_windows(chart(), 2024, "六冲")

    assert all(isinstance(window.start, date) and window.start < window.end for window in windows)
    assert all(left.end <= right.start for left, right in pairwise(windows))
    assert all(window.provider == "sxtwl" for window in windows)
    assert all(window.relation_source for window in windows)


def test_event_windows_reject_unknown_relation_and_year():
    with pytest.raises(ValueError, match="关系"):
        event_windows(chart(), 2024, "三刑")

    with pytest.raises(ValueError, match="year"):
        event_windows(chart(), 0, "六冲")


def test_api_returns_event_windows():
    response = client.post(
        "/api/windows", json={**payload(), "target_year": 2024, "relation": "六冲"}
    )

    assert response.status_code == 200
    body = response.json()
    assert [window["earthly_branch"] for window in body["windows"]] == ["卯", "未", "亥", "子"]
    assert all({"start", "end", "matched"} <= set(window) for window in body["windows"])


@pytest.mark.parametrize("natal,flow", [("亥", "寅"), ("巳", "申")])
def test_overlapping_relations_each_produce_a_window(natal, flow):
    from dataclasses import replace

    base = chart()
    synthetic = replace(base, pillars=tuple(
        replace(pillar, earthly_branch=natal) for pillar in base.pillars
    ))
    for relation in ("六合", "相破"):
        found = [w for w in event_windows(synthetic, 2024, relation)
                 if w.earthly_branch == flow]
        assert len(found) == 1
        assert found[0].matched == ((relation, natal),)
