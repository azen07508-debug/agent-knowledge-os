"""MingLi Agent 的本地 FastAPI 入口。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from runtime.mingli_service import MingLiService


class BirthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year: int
    month: int
    day: int
    hour: int
    minute: int = 0
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    timezone: str = "Asia/Shanghai"
    gender: str | None = None


class AnalyzeRequest(BirthRequest):
    question: str = Field(min_length=1)
    school: str | None = None
    policy: str | None = None
    version: str | None = None
    target_date: str | None = None


class WindowsRequest(BirthRequest):
    target_year: int
    relation: str = "六冲"


class ZiweiRequest(BirthRequest):
    leap_month: str = "split"


class MemoryProfileRequest(BirthRequest):
    school: str | None = None
    policy: str | None = None
    version: str | None = None


class MemoryAnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    target_date: str | None = None


service = MingLiService()
app = FastAPI(title="MingLi Agent API", version="0.1.0")

WEB_INDEX = Path(__file__).resolve().parent.parent / "web" / "index.html"


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
