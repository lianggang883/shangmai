"""认证模块 Schema"""
from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=11, description="手机号")
    nickname: str | None = Field(default=None, max_length=32, description="昵称")
    name: str | None = Field(default=None, max_length=32, description="姓名")
    referral_code: str | None = Field(default=None, max_length=32, description="推荐码")


class LoginRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=11, description="手机号")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 7200


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., description="刷新令牌")


class MemberBrief(BaseModel):
    id: str
    phone: str
    nickname: str | None = None
    name: str | None = None
    avatar: str | None = None
    action_power: int = 0
    level: int = 1
    created_at: str | None = None
