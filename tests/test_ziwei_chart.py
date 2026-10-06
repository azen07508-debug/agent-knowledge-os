"""紫微斗数排盘测试。

公式向量取自《紫微斗数全书》起紫微星诀算例与已刊行的五行局表；整盘对照向量
由参考实现 iztro v2.6.1 生成并固化在 tests/fixtures/ziwei_reference.json。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.server import app
from engines.ziwei import (
    MAJOR_STAR_NAMES,
    ZiweiCalculator,
    five_element_class,
    tianfu_index,
    ziwei_index,
)

client = TestClient(app)

REFERENCE = json.loads(
    (Path(__file__).parent / "fixtures" / "ziwei_reference.json").read_text(encoding="utf-8")
)
CASE = {case["id"]: case for case in REFERENCE}

# 本版本实现的副星；参考盘里其余杂曜（红鸾天喜、三台八座等）暂不排。
IMPLEMENTED_MINOR = {
    "左辅", "右弼", "文昌", "文曲", "天魁", "天钺",
    "禄存", "擎羊", "陀罗", "火星", "铃星", "地空", "地劫", "天马",
}

ZIWEI_VECTORS = [
    (3, 27, "戌"),  # 木三局廿七日，商九，自寅进九格
    (6, 13, "亥"),  # 火六局十三日，加五方整除，奇数逆行
    (5, 6, "未"),  # 土五局六日，加四方整除，偶数顺行
    (2, 1, "丑"),
    (2, 2, "寅"),
    (4, 17, "卯"),
    (6, 1, "酉"),
    (5, 25, "午"),
]

TIANFU_VECTORS = [
    ("寅", "寅"), ("卯", "丑"), ("辰", "子"), ("巳", "亥"),
    ("午", "戌"), ("未", "酉"), ("申", "申"), ("酉", "未"),
    ("戌", "午"), ("亥", "巳"), ("子", "辰"), ("丑", "卯"),
]

JU_VECTORS = [
    ("丙", "子", "水二局"),
    ("辛", "未", "土五局"),
    ("庚", "申", "木三局"),
    ("甲", "子", "金四局"),
]


def _birth(case: dict) -> dict:
    index = case["time_index"]
    hour = 0 if index == 0 else 23 if index == 12 else index * 2 - 1
    year, month, day = case["solar"]
    return {"year": year, "month": month, "day": day, "hour": hour, "gender": case["gender"]}


def _chart(case: dict, **kwargs):
    return ZiweiCalculator().calculate(_birth(case), **kwargs)


@pytest.mark.parametrize("number,day,expected", ZIWEI_VECTORS)
def test_ziwei_index_matches_published_wuxing_ju_tables(number, day, expected):
    assert ziwei_index(number, day) == expected


@pytest.mark.parametrize("ziwei,expected", TIANFU_VECTORS)
def test_tianfu_is_the_mirror_of_ziwei(ziwei, expected):
    assert tianfu_index(ziwei) == expected


@pytest.mark.parametrize("stem,branch,expected", JU_VECTORS)
def test_five_element_class_comes_from_soul_palace_naying(stem, branch, expected):
    assert five_element_class(stem, branch) == expected


@pytest.mark.parametrize("case", REFERENCE, ids=lambda case: case["id"])
def test_chart_matches_reference_implementation(case):
    chart = _chart(case)

    assert chart.five_element_class == case["five_element_class"]
    assert chart.palaces[chart.soul_index].earthly_branch == case["soul_branch"]
    assert chart.palaces[chart.body_index].earthly_branch == case["body_branch"]
    assert chart.mutagens == {star: f"化{value}" for star, value in case["mutagens"].items()}

    for palace, reference in zip(chart.palaces, case["palaces"], strict=True):
        assert palace.index == reference["index"]
        assert palace.name == reference["name"]
        assert palace.heavenly_stem == reference["stem"]
        assert palace.earthly_branch == reference["branch"]

        major = {star for star in palace.stars if star in MAJOR_STAR_NAMES}
        minor = set(palace.stars) - major
        assert major == set(reference["major"]), (case["id"], palace)
        assert minor == set(reference["minor"]) & IMPLEMENTED_MINOR, (case["id"], palace)


def test_twelve_palaces_are_named_counterclockwise_from_soul():
    chart = _chart(CASE["musk"])
    names = [palace.name for palace in chart.palaces]

    assert names[chart.soul_index] == "命宫"
    assert names[chart.soul_index - 1] == "兄弟"
    assert names[chart.soul_index - 2] == "夫妻"
    assert names[(chart.soul_index + 1) % 12] == "父母"


def test_leap_month_after_fifteenth_counts_as_next_month():
    chart = _chart(CASE["leap-after-15"])

    assert chart.lunar == (1998, 5, 17, True)
    assert chart.palaces[chart.soul_index].earthly_branch == "酉"
    assert chart.palaces[chart.body_index].earthly_branch == "巳"


def test_leap_month_policy_is_selectable_and_recorded():
    case = CASE["leap-after-15"]
    split = _chart(case)
    preceding = _chart(case, leap_month="preceding")

    # 后半月：split 归下月（六月），preceding 仍按本月（五月），命宫随之不同
    assert split.lunar == (1998, 5, 17, True)
    assert split.palaces[split.soul_index].earthly_branch == "酉"
    assert preceding.palaces[preceding.soul_index].earthly_branch == "申"
    assert "leap-preceding" in preceding.context.policy
    assert "闰月" in preceding.context.assumptions[0]
    with pytest.raises(ValueError):
        _chart(case, leap_month="sideways")


def test_chart_carries_provenance_evidence_and_scope_limits():
    chart = _chart(CASE["musk"])

    assert chart.context.school
    assert chart.context.version
    assert any("闰月" in note for note in chart.context.assumptions)
    assert any("不含大限" in note for note in chart.context.assumptions)
    assert any(note.startswith("紫微在") for note in chart.evidence)
    assert "palaces" in chart.to_dict()


def test_api_exposes_ziwei_chart():
    case = CASE["musk"]
    response = client.post("/api/ziwei", json=_birth(case))

    assert response.status_code == 200
    body = response.json()["chart"]
    assert body["five_element_class"] == case["five_element_class"]
    assert body["palaces"][body["soul_index"]]["earthly_branch"] == case["soul_branch"]


def test_api_rejects_invalid_birth_and_leap_policy():
    invalid = {"year": 1990, "month": 2, "day": 30, "hour": 1}
    unsupported = {**invalid, "day": 1, "leap_month": "sideways"}

    assert client.post("/api/ziwei", json=invalid).status_code == 422
    assert client.post("/api/ziwei", json=unsupported).status_code == 422
