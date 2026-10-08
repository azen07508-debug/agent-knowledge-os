"""新增 HTTP/MCP 操作与共享输入校验的一致性。"""

import json

import pytest
from fastapi.testclient import TestClient

from api.server import app
from runtime.mcp_server import McpServer

client = TestClient(app)
BIRTH = {"year": 1990, "month": 2, "day": 1, "hour": 12}


def mcp_call(name, args):
    return McpServer().handle({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": args},
    })["result"]


def test_western_http_and_mcp_return_identical_charts():
    response = client.post("/api/western/chart", json=BIRTH)
    result = mcp_call("western_chart", BIRTH)
    assert response.status_code == 200
    assert not result.get("isError")
    assert response.json() == json.loads(result["content"][0]["text"])


def test_date_only_request_accepts_missing_hour():
    response = client.post("/api/western/chart", json={"year": 2024, "month": 3, "day": 20})
    assert response.status_code == 200
    assert response.json()["chart"]["time_precision"] == "day"
    assert response.json()["chart"]["birth"]["hour"] is None


def test_western_endpoint_obeys_existing_api_key_auth(monkeypatch):
    monkeypatch.setenv("MINGLI_API_KEY", "test-only")
    assert client.post("/api/western/chart", json=BIRTH).status_code == 401
    assert client.post("/api/western/chart", json=BIRTH,
                       headers={"X-API-Key": "test-only"}).status_code == 200


@pytest.mark.parametrize("path,tool,extra", [
    ("/api/chart", "pa_chart", {}),
    ("/api/analyze", "analyze", {"question": "事业"}),
    ("/api/ziwei", "ziwei_chart", {}),
    ("/api/windows", "event_windows", {"target_year": 2024}),
    ("/api/western/chart", "western_chart", {}),
])
@pytest.mark.parametrize("invalid", [
    {"minute": 10**30}, {"month": 10**30}, {"day": 30},
    {"hour": True}, {"year": 1990.0}, {"timezone": "No/Such_Zone"},
    {"latitude": 91}, {"longitude": "NaN"}, {"typo": "unexpected"},
    {"year": 2024, "month": 3, "day": 10, "hour": 2, "minute": 30,
     "timezone": "America/New_York"},
    {"year": 2024, "month": 11, "day": 3, "hour": 1, "minute": 30,
     "timezone": "America/New_York"},
])
def test_http_and_mcp_reject_the_same_invalid_inputs(path, tool, extra, invalid):
    body = {**BIRTH, **extra, **invalid}
    assert client.post(path, json=body).status_code == 422
    assert mcp_call(tool, body)["isError"] is True


@pytest.mark.parametrize("year", [-10**30, 0, 9998, 10**30, True])
def test_window_query_year_is_bounded_in_http_and_mcp(year):
    body = {**BIRTH, "target_year": year}
    assert client.post("/api/windows", json=body).status_code == 422
    assert mcp_call("event_windows", body)["isError"] is True


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize("path,extra", [
    ("/api/chart", ""),
    ("/api/analyze", ',"question":"事业"'),
    ("/api/ziwei", ""),
    ("/api/windows", ',"target_year":2024'),
    ("/api/western/chart", ""),
])
def test_nonfinite_json_input_returns_422_instead_of_error_response_failure(value, path, extra):
    body = '{"year":1990,"month":2,"day":1,"hour":12,"longitude":' + value + extra + '}'
    response = client.post(path, content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "longitude"]


def test_mcp_schema_declares_optional_hour_and_rejects_extra_fields():
    tools = McpServer().handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]
    schema = next(tool["inputSchema"] for tool in tools if tool["name"] == "western_chart")
    assert "hour" not in schema["required"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["year"]["minimum"] == 1900


def test_web_console_exposes_birth_precision_and_western_results():
    page = client.get("/").text
    for field in ("minute", "timezone", "longitude", "latitude", "fold", "time_precision"):
        assert f'id="{field}"' in page
    assert '/api/western/chart' in page
    assert 'id="sun-sign"' in page and 'id="moon-sign"' in page
