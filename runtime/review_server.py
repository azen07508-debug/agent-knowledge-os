"""本地 Review API：只绑定 loopback，所有审核动作复用 Human Review。"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar
from urllib.parse import urlparse

from runtime.content_store import ContentStore
from runtime.human_review import approve, build_packet, request_changes
from runtime.research_store import ResearchStore


class ReviewHandler(BaseHTTPRequestHandler):
    store: ClassVar[ContentStore]
    research: ClassVar[ResearchStore]

    @staticmethod
    def cors_headers() -> dict[str, str]:
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        }

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, value in self.cors_headers().items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        for name, value in self.cors_headers().items():
            self.send_header(name, value)
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/review":
                self._send(200, {"ok": True, "items": self.store.list(status="REVIEW")})
                return
            prefix = "/api/review/"
            if path.startswith(prefix):
                content_id = path[len(prefix):]
                self._send(200, build_packet(self.store, content_id, self.research))
                return
            self._send(404, {"ok": False, "message": "not found"})
        except FileNotFoundError as exc:
            self._send(404, {"ok": False, "message": str(exc)})
        except Exception as exc:
            self._send(500, {"ok": False, "message": str(exc)})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        prefix = "/api/review/"
        if not path.startswith(prefix):
            self._send(404, {"ok": False, "message": "not found"})
            return
        parts = path[len(prefix):].split("/")
        if len(parts) != 2 or parts[1] not in ("approve", "changes"):
            self._send(404, {"ok": False, "message": "not found"})
            return
        try:
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            body = json.loads(raw or b"{}")
            reviewer = str(body.get("reviewer") or "local-user")
            if parts[1] == "approve":
                result = approve(self.store, parts[0], reviewer, str(body.get("note") or ""))
            else:
                result = request_changes(self.store, parts[0], reviewer, str(body.get("note") or ""))
            self._send(200, result)
        except (ValueError, FileNotFoundError) as exc:
            self._send(400, {"ok": False, "message": str(exc)})
        except Exception as exc:
            self._send(500, {"ok": False, "message": str(exc)})

    def log_message(self, _format: str, *_args: object) -> None:
        return


def serve(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    """启动本地 Review API；调用方负责 server.serve_forever()。"""
    ReviewHandler.store = ContentStore()
    ReviewHandler.research = ResearchStore()
    server = ThreadingHTTPServer((host, port), ReviewHandler)
    return server
