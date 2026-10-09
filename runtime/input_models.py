"""HTTP 与 MCP 共用输入契约，业务层仍执行领域校验。"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from engines.bazi.models import BirthInput
from engines.western.models import WesternBirthInput

Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class BirthFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year: int = Field(strict=True, ge=1, le=9999)
    month: int = Field(strict=True, ge=1, le=12)
    day: int = Field(strict=True, ge=1, le=31)
    minute: int = Field(default=0, strict=True, ge=0, le=59)
    longitude: float | None = Field(default=None, strict=True, ge=-180, le=180, allow_inf_nan=False)
    latitude: float | None = Field(default=None, strict=True, ge=-90, le=90, allow_inf_nan=False)
    timezone: str = "Asia/Shanghai"
    gender: str | None = None
    fold: int | None = Field(default=None, strict=True, ge=0, le=1)

    def birth_data(self) -> dict[str, Any]:
        return self.model_dump(include=set(BirthInput.__dataclass_fields__))


class BirthRequest(BirthFields):
    hour: int = Field(strict=True, ge=0, le=23)

    @model_validator(mode="after")
    def validate_birth(self) -> Self:
        BirthInput(**self.birth_data())
        return self


class WesternRequest(BirthFields):
    house_system: Literal["whole_sign", "equal"] = "whole_sign"
    year: int = Field(strict=True, ge=1900, le=2100)
    hour: int | None = Field(default=None, strict=True, ge=0, le=23)

    @model_validator(mode="after")
    def validate_birth(self) -> Self:
        WesternBirthInput(**self.birth_data())
        return self


class AnalyzeRequest(BirthRequest):
    question: Question
    school: str | None = None
    policy: str | None = None
    version: str | None = None
    target_date: str | None = None


class WindowsRequest(BirthRequest):
    target_year: int = Field(strict=True, ge=1, le=9997)
    relation: str = "六冲"


class ZiweiRequest(BirthRequest):
    leap_month: str = "split"


class MemoryProfileRequest(BirthRequest):
    school: str | None = None
    policy: str | None = None
    version: str | None = None


class MemoryAnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: Question
    target_date: str | None = None


class SynthesisRequest(WesternRequest):
    question: Question = "我想了解自己的表达、行动与生活节奏"
    leap_month: Literal["split", "preceding", "following"] = "split"
