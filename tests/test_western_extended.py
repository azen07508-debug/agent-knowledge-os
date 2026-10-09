"""上升/宫位/相位边界及 HTTP/MCP 与跨体系证据的一致性。"""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.server import app
from engines.western import WesternBirthInput, WesternCalculator
from engines.western.geometry import aspects, houses
from runtime.mcp_server import McpServer

client = TestClient(app)
BIRTH = dict(year=1990, month=2, day=1, hour=12, longitude=121.4737, latitude=31.2304)


def test_full_chart_assigns_each_body_to_one_house():
    chart = WesternCalculator().calculate(WesternBirthInput(**BIRTH))
    assert chart.ascendant.sign == "金牛座"
    assert len(chart.houses) == 12 and len(chart.planets) == 8
    assigned = [body for house in chart.houses for body in house["bodies"]]
    assert len(assigned) == len(set(assigned)) == 10
    assert {"sun", "moon", "pluto"} <= set(assigned)
    assert chart.houses[0]["sign"] == chart.ascendant.sign


def test_house_system_changes_cusps_but_not_ascendant_or_planets():
    b = WesternBirthInput(**BIRTH)
    whole = WesternCalculator().calculate(b)
    equal = WesternCalculator().calculate(b, house_system="equal")
    assert whole.ascendant == equal.ascendant
    assert whole.planets == equal.planets and whole.aspects == equal.aspects
    assert equal.houses[0]["cusp_longitude_deg"] == equal.ascendant.longitude_deg
    assert whole.houses[0]["cusp_longitude_deg"] == 30


def test_date_only_never_fabricates_angles_planets_houses_or_aspects():
    b = WesternBirthInput(**{**BIRTH, "hour": None})
    chart = WesternCalculator().calculate(b)
    assert chart.ascendant is None
    assert chart.houses == chart.planets == chart.aspects == ()
    assert chart.sun.longitude_deg is None and chart.unavailable


def test_missing_one_coordinate_preserves_planets_but_omits_houses():
    b = WesternBirthInput(**{**BIRTH, "latitude": None})
    chart = WesternCalculator().calculate(b)
    assert chart.ascendant is None and not chart.houses
    assert len(chart.planets) == 8 and chart.aspects


def test_same_instant_location_changes_angles_but_not_geocentric_positions():
    b = WesternBirthInput(**BIRTH)
    a = WesternCalculator().calculate(b)
    other = WesternCalculator().calculate(replace(b, longitude=-74, latitude=40.7))
    assert a.ascendant != other.ascendant
    assert a.sun == other.sun and a.moon == other.moon and a.planets == other.planets


@pytest.mark.parametrize("latitude", [-90, 89, 90])
def test_polar_location_is_partial_result_with_reason(latitude):
    chart = WesternCalculator().calculate(WesternBirthInput(**{**BIRTH, "latitude": latitude}))
    assert chart.ascendant is None and not chart.houses
    assert any("89" in message for message in chart.unavailable)
    assert chart.sun.sign == "水瓶座" and chart.planets


def test_house_boundary_and_zero_wrap_do_not_duplicate_bodies():
    result = houses(359, "equal", {"sun": 359, "moon": 29, "mars": 358.999})
    assert result[0]["bodies"] == ["sun"]
    assert result[1]["bodies"] == ["moon"]
    assert result[-1]["bodies"] == ["mars"]


@pytest.mark.parametrize(
    "angle,name", [(0, "合相"), (60, "六合"), (90, "刑相"), (120, "拱相"), (180, "冲相")]
)
def test_aspect_names_angles_and_orb(angle, name):
    result = aspects({"sun": 350, "mars": (350 + angle) % 360})
    assert len(result) == 1 and result[0]["name"] == name
    assert result[0]["orb_deg"] == 0


def test_aspect_orb_threshold_is_explicit_and_inclusive():
    assert aspects({"sun": 0, "mars": 8})[0]["orb_limit_deg"] == 8
    assert not aspects({"sun": 0, "mars": 8.001})
    assert aspects({"venus": 0, "mars": 6})[0]["orb_limit_deg"] == 6
    assert not aspects({"venus": 0, "mars": 6.001})


def test_extended_http_and_mcp_agree_on_house_system():
    import json

    args = {**BIRTH, "house_system": "equal"}
    http = client.post("/api/western/chart", json=args)
    mcp = McpServer().handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "western_chart", "arguments": args},
        }
    )["result"]
    assert http.status_code == 200
    assert http.json() == json.loads(mcp["content"][0]["text"])
    assert http.json()["chart"]["house_system"] == "equal"


@pytest.mark.parametrize("system", ["placidus", "", None])
def test_unsupported_house_system_is_rejected(system):
    assert (
        client.post("/api/western/chart", json={**BIRTH, "house_system": system}).status_code == 422
    )


def test_synthesis_references_actual_charts_and_no_dangling_evidence():
    data = client.post("/api/synthesis", json={**BIRTH, "question": "如何表达自己"}).json()
    i = data["interpretation"]
    ids = {e["id"] for e in i["evidence"]}
    assert data["charts"]["bazi"]["day_master"] == "丁"
    assert "bazi.day_master" in ids and "ziwei.soul" in ids and "western.ascendant" in ids
    assert i["question"] == "如何表达自己"
    for theme in i["themes"]:
        for reading in theme["readings"]:
            assert set(reading["evidence_ids"]) <= ids
            assert reading["rule_id"] == i["version"]


def test_synthesis_date_only_reports_missing_systems_without_filling_noon():
    response = client.post("/api/synthesis", json={**BIRTH, "hour": None})
    assert response.status_code == 200
    data = response.json()
    assert data["charts"]["bazi"] is data["charts"]["ziwei"] is None
    assert data["charts"]["western"]["birth"]["hour"] is None
    assert all(e["system"] == "西方星盘" for e in data["interpretation"]["evidence"])


def test_synthesis_auth_and_blank_question(monkeypatch):
    monkeypatch.setenv("MINGLI_API_KEY", "test")
    assert client.post("/api/synthesis", json=BIRTH).status_code == 401
    assert (
        client.post(
            "/api/synthesis", json={**BIRTH, "question": "  "}, headers={"X-API-Key": "test"}
        ).status_code
        == 422
    )


def test_synthesis_mcp_matches_http():
    import json

    args = {**BIRTH, "question": "关系", "house_system": "equal"}
    mcp = McpServer().handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "synthesis", "arguments": args},
        }
    )["result"]
    assert not mcp.get("isError")
    assert client.post("/api/synthesis", json=args).json() == json.loads(mcp["content"][0]["text"])


REFERENCE = json.loads(
    (Path(__file__).parent / "fixtures" / "western_extended_reference.json").read_text()
)


@pytest.mark.parametrize("sample", REFERENCE["samples"], ids=lambda row: row["utc"])
@pytest.mark.parametrize("system", ["whole_sign", "equal"])
def test_angles_houses_and_planets_match_independent_swiss_reference(sample, system):
    from datetime import datetime

    t = datetime.fromisoformat(sample["utc"])
    b = WesternBirthInput(
        t.year,
        t.month,
        t.day,
        t.hour,
        t.minute,
        longitude=sample["longitude"],
        latitude=sample["latitude"],
        timezone="UTC",
    )
    c = WesternCalculator().calculate(b, house_system=system)

    def difference(a, b):
        return abs((a - b + 180) % 360 - 180)

    assert (
        difference(c.ascendant.longitude_deg, sample["ascendant_deg"])
        <= REFERENCE["angle_tolerance_degrees"]
    )
    expected = sample[system + "_cusps"] if system == "whole_sign" else sample["equal_cusps"]
    for house, cusp in zip(c.houses, expected, strict=True):
        assert difference(house["cusp_longitude_deg"], cusp) <= REFERENCE["angle_tolerance_degrees"]
    for p in (c.sun, c.moon, *c.planets):
        assert (
            difference(p.longitude_deg, sample["longitudes"][p.body])
            <= REFERENCE["planet_tolerance_degrees"]
        )


def test_synthesis_question_focus_changes_exploration_prompt():
    career = client.post("/api/synthesis", json={**BIRTH, "question": "事业"}).json()[
        "interpretation"
    ]
    relationship = client.post("/api/synthesis", json={**BIRTH, "question": "感情"}).json()[
        "interpretation"
    ]
    assert career["focus"] != relationship["focus"]
    assert career["themes"][0]["prompt"] != relationship["themes"][0]["prompt"]
