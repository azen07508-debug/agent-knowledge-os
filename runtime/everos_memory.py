"""EverOS 长期记忆客户端。

对接 EverMind-AI/EverOS（https://github.com/EverMind-AI/EverOS）的 HTTP API：

    GET  /health
    POST /api/v2/memory/add    {session_id, app_id, project_id, messages[]}
    POST /api/v2/memory/flush  {session_id, app_id, project_id}
    POST /api/v2/memory/search {user_id, app_id, project_id, query, method, top_k}

everos 1.x 只暴露 /api/v1，更新版本以 /api/v2 为准，因此 404 时回退一次。
服务未启动时保持友好降级，不让调用方崩掉。
"""

from __future__ import annotations

import re
import time
from typing import Any

import requests

DEFAULT_APP_ID = "creator-os"
DEFAULT_PROJECT_ID = "creator-os"
DEFAULT_OWNER_ID = "creator-os"

# everos 用 sender_id / app_id / project_id 生成目录，只接受白名单字符。
_ID_SAFE = re.compile(r"[^a-zA-Z0-9_.@+-]+")


def safe_id(value: str) -> str:
    """把任意名称压成 EverOS 允许的标识符。"""
    cleaned = _ID_SAFE.sub("-", value.strip()).strip("-")
    return cleaned or "unknown"


class EverOSMemory:
    """封装 EverOS HTTP API，并对服务不可用做友好降级。"""

    _PREFIXES = ("/api/v2", "/api/v1")

    def __init__(
        self,
        server_url: str = "http://127.0.0.1:8000",
        app_id: str = DEFAULT_APP_ID,
        project_id: str = DEFAULT_PROJECT_ID,
        timeout: float = 3.0,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.app_id = app_id
        self.project_id = project_id
        self.timeout = timeout
        self._prefix: str | None = None

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = requests.request(method, f"{self.server_url}{path}", timeout=self.timeout, **kwargs)
        except requests.RequestException:
            return {"ok": False, "message": "EverOS 服务未启动，本次跳过长期记忆写入。"}

        result: dict[str, Any] = {"ok": response.ok, "status": response.status_code}
        if response.text:
            try:
                result["data"] = response.json()
            except ValueError:
                result["data"] = response.text[:500]
        if not response.ok:
            result["message"] = f"EverOS 返回 HTTP {response.status_code}：{result.get('data')}"
        return result

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        prefixes = (self._prefix,) if self._prefix else self._PREFIXES
        last: dict[str, Any] = {}
        for prefix in prefixes:
            last = self._request("POST", f"{prefix}{path}", json=payload)
            if last.get("ok"):
                self._prefix = prefix
                return last
            if last.get("status") != 404:
                return last
        return {**last, "message": f"EverOS 未提供 {path}（HTTP 404），请确认 everos 服务版本。"}

    def health_check(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def append(
        self,
        text: str,
        session_id: str,
        sender_id: str = DEFAULT_OWNER_ID,
        role: str = "assistant",
    ) -> dict[str, Any]:
        """写入一条记忆消息，等待 flush 时切分成长期记忆。"""
        payload = {
            "session_id": session_id,
            "app_id": self.app_id,
            "project_id": self.project_id,
            "messages": [
                {
                    "sender_id": safe_id(sender_id),
                    "role": role,
                    "timestamp": int(time.time() * 1000),
                    "content": text,
                }
            ],
        }
        return self._post("/memory/add", payload)

    def add_memory(self, agent_name: str, task: str, result: dict[str, Any]) -> dict[str, Any]:
        """按 Agent 执行结果写入一条记忆。"""
        lines = [f"任务：{task}", f"执行者：{agent_name}", f"摘要：{result.get('summary', '')}"]
        lines.extend(f"- {point}" for point in result.get("knowledge_points", [])[:5])
        return self.append("\n".join(lines), session_id=safe_id(agent_name), sender_id=agent_name)

    def flush_memory(self, session_id: str, app_id: str | None = None, project_id: str | None = None) -> dict[str, Any]:
        payload = {
            "session_id": session_id,
            "app_id": app_id or self.app_id,
            "project_id": project_id or self.project_id,
        }
        return self._post("/memory/flush", payload)

    def search_memory(
        self,
        query: str,
        top_k: int = 5,
        owner_id: str = DEFAULT_OWNER_ID,
        method: str = "keyword",
    ) -> dict[str, Any]:
        """按关键词检索长期记忆；method 默认 keyword，避免依赖 embedding 配置。"""
        payload = {
            "user_id": owner_id,
            "app_id": self.app_id,
            "project_id": self.project_id,
            "query": query,
            "method": method,
            "top_k": top_k,
        }
        return self._post("/memory/search", payload)
