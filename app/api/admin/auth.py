# -*- coding: utf-8 -*-
"""
管理员认证路由 - 测试模式（免密码登录）
商脉平台 Phase 2 - PKG-001
"""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.admin_user import AdminUser

# ========================
# 配置（复用 settings）
# ========================
JWT_SECRET = settings.JWT_SECRET
JWT_ALGORITHM = settings.JWT_ALGORITHM

security = HTTPBearer()

router = APIRouter(prefix="", tags=["管理员认证"])


# ========================
# Pydantic 请求/响应模型
# ========================
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    admin: dict


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


# ========================
# JWT 工具函数
# ========================
def create_access_token(admin_id: int, username: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(admin_id),
        "username": username,
        "role": role,
        "type": "access",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(admin_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(admin_id),
        "type": "refresh",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token已过期，请重新登录")
    except jwt.JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的Token")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    import bcrypt
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )


def hash_password(password: str) -> str:
    import bcrypt
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


# ========================
# 依赖：获取当前管理员
# ========================
async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的Token类型")
    admin_id = int(payload.get("sub"))
    result = await db.execute(select(AdminUser).where(AdminUser.id == admin_id))
    admin = result.scalar_one_or_none()
    if not admin or not admin.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="管理员不存在或已被禁用")
    return admin


async def require_super_admin(admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
    if not admin.is_super_admin():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要超级管理员权限")
    return admin


# ========================
# API 路由 - 免密码登录（测试模式）
# ========================
@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    login_data: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AdminUser).where(AdminUser.username == login_data.username)
    )
    admin = result.scalar_one_or_none()

    if not admin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名不存在")

    if not admin.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")

    # ★★★ 测试模式：跳过密码验证 ★★★
    # 验证密码的代码已注释，测试完成后恢复

    # 更新登录记录
    admin.last_login_at = datetime.now(timezone.utc)
    admin.last_login_ip = request.client.host if request.client else None
    admin.login_count = (admin.login_count or 0) + 1
    await db.commit()

    access_token = create_access_token(admin.id, admin.username, admin.role.value)
    refresh_token = create_refresh_token(admin.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        admin=admin.to_dict()
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    refresh_data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    payload = decode_token(refresh_data.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的刷新Token")

    admin_id = int(payload.get("sub"))
    result = await db.execute(select(AdminUser).where(AdminUser.id == admin_id))
    admin = result.scalar_one_or_none()
    if not admin or not admin.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="管理员不存在或已被禁用")

    access_token = create_access_token(admin.id, admin.username, admin.role.value)
    new_refresh_token = create_refresh_token(admin.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        admin=admin.to_dict()
    )


@router.post("/logout")
async def logout(admin: AdminUser = Depends(get_current_admin)):
    return {"code": 0, "message": "登出成功", "data": {"username": admin.username}}


@router.get("/me")
async def get_me(admin: AdminUser = Depends(get_current_admin)):
    return {"code": 0, "message": "success", "data": admin.to_dict()}


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(body.old_password, admin.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码错误")
    admin.password_hash = hash_password(body.new_password)
    await db.commit()
    return {"code": 0, "message": "密码修改成功，请重新登录"}
