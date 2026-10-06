"""MingLi Agent 的本地 FastAPI 入口。"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
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


service = MingLiService()
app = FastAPI(title="MingLi Agent API", version="0.1.0")


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
