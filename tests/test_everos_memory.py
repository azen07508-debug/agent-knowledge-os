from runtime.everos_memory import EverOSMemory, safe_id


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or ("" if payload is None else "json")
        self.ok = status_code < 400

    def json(self):
        return self._payload


def test_safe_id_strips_disallowed_characters():
    assert safe_id("Planner Agent") == "Planner-Agent"
    assert safe_id("内容研究/Agent") == "Agent"
    assert safe_id("  ") == "unknown"


def test_add_payload_uses_official_endpoint(monkeypatch):
    calls = []

    def fake_request(method, url, timeout=None, **kwargs):
        calls.append((method, url, kwargs.get("json")))
        return FakeResponse(200, {"request_id": "r1", "data": {"message_count": 1, "status": "accumulated"}})

    monkeypatch.setattr("runtime.everos_memory.requests.request", fake_request)
    memory = EverOSMemory(app_id="creator-os", project_id="creator-os")
    result = memory.append("测试记忆", session_id="creator-memory-identity", sender_id="creator-os")

    assert result["ok"] is True
    method, url, payload = calls[0]
    assert method == "POST"
    assert url.endswith("/api/v2/memory/add")
    assert payload["session_id"] == "creator-memory-identity"
    assert payload["app_id"] == "creator-os"
    assert payload["messages"][0]["sender_id"] == "creator-os"
    assert payload["messages"][0]["content"] == "测试记忆"
    assert payload["messages"][0]["timestamp"] > 0


def test_v1_fallback_when_v2_missing(monkeypatch):
    urls = []

    def fake_request(method, url, timeout=None, **kwargs):
        urls.append(url)
        if url.endswith("/api/v2/memory/add"):
            return FakeResponse(404, {"detail": "Not Found"}, text="Not Found")
        return FakeResponse(200, {"request_id": "r1", "data": {"message_count": 1, "status": "extracted"}})

    monkeypatch.setattr("runtime.everos_memory.requests.request", fake_request)
    memory = EverOSMemory()
    result = memory.append("测试记忆", session_id="s1")

    assert result["ok"] is True
    assert urls[1].endswith("/api/v1/memory/add")


def test_server_down_degrades_gracefully(monkeypatch):
    import requests

    def raise_error(method, url, timeout=None, **kwargs):
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr("runtime.everos_memory.requests.request", raise_error)
    memory = EverOSMemory()
    result = memory.add_memory("Planner Agent", "任务", {"summary": "摘要", "knowledge_points": ["知识点"]})

    assert result["ok"] is False
    assert "服务未启动" in result["message"]


def test_http_error_reports_status(monkeypatch):
    def fake_request(method, url, timeout=None, **kwargs):
        return FakeResponse(422, {"detail": "embedding not configured"}, text="{}")

    monkeypatch.setattr("runtime.everos_memory.requests.request", fake_request)
    memory = EverOSMemory()
    result = memory.search_memory("查询", method="hybrid")

    assert result["ok"] is False
    assert result["status"] == 422
    assert "HTTP 422" in result["message"]


def test_add_memory_builds_text_from_agent_result(monkeypatch):
    payloads = []

    def fake_request(method, url, timeout=None, **kwargs):
        payloads.append(kwargs.get("json"))
        return FakeResponse(200, {"request_id": "r1", "data": {"message_count": 1, "status": "accumulated"}})

    monkeypatch.setattr("runtime.everos_memory.requests.request", fake_request)
    memory = EverOSMemory()
    memory.add_memory("Coder Agent", "写代码", {"summary": "完成了", "knowledge_points": ["要点一"]})

    message = payloads[0]["messages"][0]
    assert message["sender_id"] == "Coder-Agent"
    assert "任务：写代码" in message["content"]
    assert "- 要点一" in message["content"]
