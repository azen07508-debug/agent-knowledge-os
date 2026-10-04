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


service = MingLiService()
app = FastAPI(title="MingLi Agent API", version="0.1.0")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "provider": "sxtwl"}


@app.post("/api/chart")
def chart(request: BirthRequest) -> dict[str, Any]:
    try:
        response = service.analyze(request.model_dump(), "命盘结构")
    except (TypeError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return response.chart


@app.post("/api/analyze")
def analyze(request: AnalyzeRequest) -> dict[str, Any]:
    try:
        response = service.analyze(request.model_dump(exclude={"question"}), request.question)
    except (TypeError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return response.to_dict()
