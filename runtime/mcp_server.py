"""MCP（Model Context Protocol）stdio 入口：把排盘能力作为工具暴露给 Agent 客户端。

ponytail: 只实现本仓库四个工具所需的最小子集（initialize / ping / tools/list /
tools/call），不引入 MCP SDK；需要会话、资源订阅或采样时再换官方实现。
"""

from __future__ import annotations

import json
import sys
from typing import Any

from runtime.mingli_service import MingLiService

PROTOCOL_VERSION = "2025-06-18"

# BirthInput 的合法入参；各工具在此之上追加自己的字段，其余键一律丢弃。
BIRTH_KEYS = (
    "year",
    "month",
    "day",
    "hour",
    "minute",
    "longitude",
    "latitude",
    "timezone",
    "gender",
)

_BIRTH_PROPERTIES: dict[str, Any] = {
    "year": {"type": "integer"},
    "month": {"type": "integer"},
    "day": {"type": "integer"},
    "hour": {"type": "integer", "description": "出生地当地民用时间，24 小时制"},
    "minute": {"type": "integer"},
    "longitude": {"type": ["number", "null"]},
    "latitude": {"type": ["number", "null"]},
    "timezone": {"type": "string"},
    "gender": {"type": ["string", "null"], "description": "男、女、male、female 或 null"},
}


def _schema(extra: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {**_BIRTH_PROPERTIES, **extra},
        "required": ["year", "month", "day", "hour"],
    }


TOOLS: tuple[dict[str, Any], ...] = (
    {
        "name": "pa_chart",
        "description": "按公历出生时间排八字命盘，返回四柱、十神、纳音、藏干与结构关系等确定性事实，不作吉凶判断。",
        "inputSchema": _schema({}),
    },
    {
        "name": "analyze",
        "description": "在指定策略下分析命盘并给出带 provenance 的结论；school、policy、version 必须同时填写或同时留空。",
        "inputSchema": _schema(
            {
                "question": {"type": "string", "description": "要回答的问题"},
                "school": {"type": ["string", "null"]},
                "policy": {"type": ["string", "null"]},
                "version": {"type": ["string", "null"]},
                "target_date": {"type": ["string", "null"], "description": "YYYY-MM-DD，用于定位流月"},
            }
        ),
    },
    {
        "name": "ziwei_chart",
        "description": "排紫微斗数本命盘：十二宫干支、五行局、十四主星、六吉六煞、禄存天马与生年四化。",
        "inputSchema": _schema(
            {
                "leap_month": {
                    "type": "string",
                    "enum": ["split", "preceding", "following"],
                    "description": "闰月出生时的生月归属策略，默认 split",
                }
            }
        ),
    },
    {
        "name": "event_windows",
        "description": "列出指定年份内命中某结构关系的流月窗口；只返回结构事实，不判吉凶。",
        "inputSchema": _schema(
            {
                "target_year": {"type": "integer"},
                "relation": {"type": "string", "description": "六冲、六合、三合等结构关系"},
            }
        ),
    },
)


def _result(message: dict[str, Any], result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message.get("id"), "result": result}


def _error(message: dict[str, Any], code: int, text: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message.get("id"), "error": {"code": code, "message": text}}


class McpServer:
    """无状态 MCP 服务端：逐条消息独立处理，不维护会话。"""

    def __init__(self, service: MingLiService | None = None) -> None:
        self.service = service or MingLiService()

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """处理一条 JSON-RPC 消息；通知按协议不回包，返回 None。"""
        if "id" not in message:
            return None

        method = message.get("method")
        if method == "initialize":
            return _result(
                message,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "mingli-agent", "version": "0.1.0"},
                },
            )
        if method == "ping":
            return _result(message, {})
        if method == "tools/list":
            return _result(message, {"tools": list(TOOLS)})
        if method == "tools/call":
            return _result(message, self._call(message.get("params") or {}))
        return _error(message, -32601, f"未知方法：{method}")

    def _call(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            payload = self._dispatch(params.get("name"), dict(params.get("arguments") or {}))
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        return {"content": [{"type": "text", "text": text}]}

    def _dispatch(self, name: str | None, args: dict[str, Any]) -> Any:
        birth = {key: value for key, value in args.items() if key in BIRTH_KEYS}
        if name == "pa_chart":
            return self.service.analyze(birth, "命盘结构").chart
        if name == "analyze":
            return self.service.analyze(
                birth,
                args.get("question", ""),
                school=args.get("school"),
                policy=args.get("policy"),
                version=args.get("version"),
                target_date=args.get("target_date"),
            ).to_dict()
        if name == "ziwei_chart":
            return self.service.ziwei(birth, leap_month=args.get("leap_month", "split"))
        if name == "event_windows":
            return self.service.windows(
                birth, args.get("target_year"), relation=args.get("relation", "六冲")
            )
        raise ValueError(f"未知工具：{name}")


def main() -> int:
    """标准输入输出上的换行分隔 JSON-RPC 传输。"""
    server = McpServer()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            response = _error({"id": None}, -32700, f"解析错误：{exc}")
        else:
            response = server.handle(message)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
