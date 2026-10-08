"""MCP（Model Context Protocol）stdio 入口：把排盘能力作为工具暴露给 Agent 客户端。

只实现本仓库工具所需的最小子集（initialize / ping / tools/list /
tools/call），不引入 MCP SDK；需要会话、资源订阅或采样时再换官方实现。
"""

from __future__ import annotations

import json
import sys
from typing import Any

from runtime.input_models import (
    AnalyzeRequest,
    BirthRequest,
    WesternRequest,
    WindowsRequest,
    ZiweiRequest,
)
from runtime.mingli_service import MingLiService

PROTOCOL_VERSION = "2025-06-18"

INPUT_MODELS = {
    "pa_chart": BirthRequest,
    "analyze": AnalyzeRequest,
    "ziwei_chart": ZiweiRequest,
    "event_windows": WindowsRequest,
    "western_chart": WesternRequest,
}


TOOLS: tuple[dict[str, Any], ...] = (
    {
        "name": "pa_chart",
        "description": "按公历出生时间排八字命盘，返回四柱、十神、纳音、藏干与结构关系等确定性事实，不作吉凶判断。",
        "inputSchema": INPUT_MODELS["pa_chart"].model_json_schema(),
    },
    {
        "name": "analyze",
        "description": "在指定策略下分析命盘并给出带 provenance 的结论；school、policy、version 必须同时填写或同时留空。",
        "inputSchema": INPUT_MODELS["analyze"].model_json_schema(),
    },
    {
        "name": "ziwei_chart",
        "description": "排紫微斗数本命盘：十二宫干支、五行局、十四主星、六吉六煞、禄存天马与生年四化。",
        "inputSchema": INPUT_MODELS["ziwei_chart"].model_json_schema(),
    },
    {
        "name": "event_windows",
        "description": "列出指定年份内命中六冲、六合、六害或相破的流月窗口；只返回结构事实，不判吉凶。",
        "inputSchema": INPUT_MODELS["event_windows"].model_json_schema(),
    },
    {
        "name": "western_chart",
        "description": "离线计算回归黄道太阳/月亮星座。时间为出生地民用时间；省略 hour 时返回当天候选，不计算上升或宫位。",
        "inputSchema": INPUT_MODELS["western_chart"].model_json_schema(),
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
        if name not in INPUT_MODELS:
            raise ValueError(f"未知工具：{name}")
        request = INPUT_MODELS[name].model_validate(args)
        birth = request.birth_data()
        args = request.model_dump()
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
        if name == "western_chart":
            return self.service.western(birth)
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
