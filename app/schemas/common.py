"""统一响应模型 & 通用类型"""

from __future__ import annotations

import time
import uuid
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


# ── Meta ──────────────────────────────────────────────
class ResponseMeta(BaseModel):
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: float = Field(default_factory=time.time)
    action_power_consumed: int = Field(default=0, ge=0)


# ── 统一响应 ──────────────────────────────────────────
class ApiResponse(BaseModel, Generic[T]):
    code: int = Field(default=0, description="0=成功, 非0=业务错误")
    message: str = Field(default="ok")
    data: T | None = Field(default=None)
    meta: ResponseMeta = Field(default_factory=ResponseMeta)


def success(data: Any = None, message: str = "ok", ap: int = 0) -> ApiResponse:
    """快速构建成功响应"""
    return ApiResponse(code=0, message=message, data=data, meta=ResponseMeta(action_power_consumed=ap))


def fail(code: int = -1, message: str = "fail", data: Any = None, ap: int = 0) -> ApiResponse:
    """快速构建失败响应"""
    return ApiResponse(code=code, message=message, data=data, meta=ResponseMeta(action_power_consumed=ap))


# ── 分页 ──────────────────────────────────────────────
class Pagination(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class PaginatedData(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


# ── Token ─────────────────────────────────────────────
class TokenPayload(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 7200
