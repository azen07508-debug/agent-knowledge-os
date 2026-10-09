"""MCP stdio 服务测试：协议握手、工具列表、工具调用与错误路径。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from runtime.mcp_server import McpServer

BIRTH = {"year": 1990, "month": 2, "day": 1, "hour": 12, "gender": "男"}


def request(server, method, params=None, request_id=1):
    message = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return server.handle(message)


def test_initialize_reports_protocol_and_tool_capability():
    server = McpServer()
    response = request(server, "initialize", {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    })

    assert response["jsonrpc"] == "2.0"
    assert response["result"]["protocolVersion"]
    assert response["result"]["capabilities"] == {"tools": {}}
    assert response["result"]["serverInfo"]["name"] == "mingli-agent"


def test_initialized_notification_gets_no_response():
    server = McpServer()
    message = {"jsonrpc": "2.0", "method": "notifications/initialized"}

    assert server.handle(message) is None


def test_tools_list_exposes_the_six_public_operations():
    server = McpServer()
    tools = request(server, "tools/list")["result"]["tools"]
    by_name = {tool["name"]: tool for tool in tools}

    assert set(by_name) == {"pa_chart", "analyze", "ziwei_chart", "event_windows", "western_chart", "synthesis"}
    for tool in tools:
        assert tool["description"]
        assert tool["inputSchema"]["type"] == "object"
        assert "year" in tool["inputSchema"]["properties"]
    assert "question" in by_name["analyze"]["inputSchema"]["properties"]
    assert "target_year" in by_name["event_windows"]["inputSchema"]["properties"]
    assert "leap_month" in by_name["ziwei_chart"]["inputSchema"]["properties"]


def test_tools_call_returns_json_text_content():
    server = McpServer()
    response = request(server, "tools/call", {"name": "pa_chart", "arguments": BIRTH})

    assert response["result"].get("isError") is None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert len(payload["pillars"]) == 4
    assert payload["provider"] == "sxtwl"


def test_tools_call_ziwei_chart_returns_twelve_palaces():
    server = McpServer()
    response = request(
        server, "tools/call", {"name": "ziwei_chart", "arguments": {**BIRTH, "leap_month": "split"}}
    )

    payload = json.loads(response["result"]["content"][0]["text"])
    assert len(payload["chart"]["palaces"]) == 12
    assert payload["chart"]["context"]["policy"].startswith("leap-split")


def test_tools_call_reports_business_errors_as_is_error():
    server = McpServer()
    response = request(
        server, "tools/call", {"name": "pa_chart", "arguments": {**BIRTH, "month": 13}}
    )

    assert response["result"]["isError"] is True
    assert response["result"]["content"][0]["type"] == "text"


def test_unknown_method_returns_method_not_found():
    server = McpServer()
    response = request(server, "resources/list")

    assert response["error"]["code"] == -32601


def test_stdio_transport_round_trip():
    lines = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "pa_chart", "arguments": BIRTH}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": "western_chart", "arguments": BIRTH}},
    ]
    env = {**os.environ, "PYTHONPATH": str(Path.cwd())}
    process = subprocess.run(
        [sys.executable, "-m", "runtime.mcp_server"],
        input="\n".join(json.dumps(line) for line in lines) + "\n",
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        check=True,
    )

    responses = [json.loads(line) for line in process.stdout.splitlines() if line.strip()]
    assert [message["id"] for message in responses] == [1, 2, 3, 4]
    assert "tools" in responses[1]["result"]
    assert json.loads(responses[2]["result"]["content"][0]["text"])["pillars"]
    western = json.loads(responses[3]["result"]["content"][0]["text"])["chart"]
    assert western["sun"]["sign"] == "水瓶座"
    assert western["moon"]["sign"] == "白羊座"
