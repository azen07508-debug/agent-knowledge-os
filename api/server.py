"""MingLi Agent 的本地 FastAPI 入口。"""

from __future__ import annotations

import hmac
import math
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from runtime.input_models import (
    AnalyzeRequest,
    BirthRequest,
    MemoryAnalyzeRequest,
    MemoryProfileRequest,
    SynthesisRequest,
    WesternRequest,
    WindowsRequest,
    ZiweiRequest,
)
from runtime.mingli_service import MingLiService

service = MingLiService()
app = FastAPI(title="MingLi Agent API", version="0.1.0")

WEB_INDEX = Path(__file__).resolve().parent.parent / "web" / "index.html"
app.mount("/assets", StaticFiles(directory=WEB_INDEX.parent / "assets"), name="assets")


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # 标准库 JSON parser 接受 NaN/Infinity，但错误响应的 JSON encoder 不接受；
    # 将错误中的非有限输入转成文本，确保非法数值仍返回 422 而非 500。
    errors = jsonable_encoder(
        exc.errors(), custom_encoder={float: lambda value: value if math.isfinite(value) else str(value)}
    )
    return JSONResponse(status_code=422, content={"detail": errors})


@app.middleware("http")
async def require_api_key(request: Request, call_next):
    """配置 MINGLI_API_KEY 后 /api/* 必须携带 X-API-Key；健康检查与静态页保持可探活。"""
    key = os.environ.get("MINGLI_API_KEY")
    path = request.url.path
    if key and path.startswith("/api/") and path != "/api/health":
        provided = request.headers.get("X-API-Key", "")
        if not hmac.compare_digest(provided.encode("utf-8"), key.encode("utf-8")):
            return JSONResponse({"detail": "缺少或错误的 X-API-Key"}, status_code=401)
    return await call_next(request)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """本地 Web 控制台；纯静态单页，不引入前端构建链。"""
    return FileResponse(WEB_INDEX, media_type="text/html; charset=utf-8")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "provider": "sxtwl"}


@app.post("/api/chart")
def chart(request: BirthRequest) -> dict[str, Any]:
    try:
        response = service.analyze(request.model_dump(), "命盘结构")
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return response.chart


@app.post("/api/windows")
def windows(request: WindowsRequest) -> dict[str, Any]:
    try:
        data = request.model_dump()
        return service.windows(
            {key: value for key, value in data.items() if key not in {"target_year", "relation"}},
            request.target_year,
            request.relation,
        )
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/ziwei")
def ziwei(request: ZiweiRequest) -> dict[str, Any]:
    data = request.model_dump()
    try:
        return service.ziwei(
            {key: value for key, value in data.items() if key != "leap_month"},
            leap_month=request.leap_month,
        )
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/synthesis")
def synthesis(request: SynthesisRequest) -> dict[str, Any]:
    try:
        return service.synthesis(
            request.birth_data(), question=request.question,
            house_system=request.house_system, leap_month=request.leap_month,
        )
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/western/chart")
def western_chart(request: WesternRequest) -> dict[str, Any]:
    try:
        return service.western(request.birth_data(), house_system=request.house_system)
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put("/api/memory/{user_id}")
def save_memory_profile(user_id: str, request: MemoryProfileRequest) -> dict[str, Any]:
    data = request.model_dump()
    selector = {key: data.pop(key) for key in ("school", "policy", "version")}
    try:
        return {"profile": service.save_profile(user_id, data, **selector)}
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/memory/{user_id}")
def get_memory(user_id: str) -> dict[str, Any]:
    recalled = service.recall(user_id)
    if recalled is None:
        raise HTTPException(status_code=404, detail=f"没有 {user_id} 的用户记忆")
    return recalled


@app.post("/api/memory/{user_id}/analyze")
def analyze_from_memory(user_id: str, request: MemoryAnalyzeRequest) -> dict[str, Any]:
    if service.memory.profile(user_id) is None:
        raise HTTPException(status_code=404, detail=f"没有 {user_id} 的用户记忆")
    try:
        response = service.analyze_from_memory(
            user_id, request.question, target_date=request.target_date
        )
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return response.to_dict()


@app.post("/api/analyze")
def analyze(request: AnalyzeRequest) -> dict[str, Any]:
    try:
        data = request.model_dump()
        response = service.analyze(
            {
                key: value
                for key, value in data.items()
                if key not in {"question", "school", "policy", "version", "target_date"}
            },
            request.question,
            school=request.school,
            policy=request.policy,
            version=request.version,
            target_date=request.target_date,
        )
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return response.to_dict()
