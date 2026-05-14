"""
商脉系统 — 认证依赖（修复版）
JWT 签发、验证、用户身份提取
"""
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.member import Member
from app.models.admin_user import AdminUser

security = HTTPBearer()


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """签发 access_token"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """签发 refresh_token"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


async def get_current_member(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Member:
    """从 JWT 提取当前登录用户"""
    try:
        payload = jwt.decode(credentials.credentials, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        member_id = payload.get("sub")
        if member_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效Token")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token已失效")

    result = await db.execute(select(Member).where(Member.id == member_id))
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return member


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    """从 JWT 提取当前登录管理员"""
    try:
        payload = jwt.decode(credentials.credentials, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        # 优先用 username，fallback 到 sub (admin_id)
        username = payload.get("username")
        admin_id = payload.get("sub")
        if username is None and admin_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效Token")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token已失效")

    admin = None
    # 优先用 username 查询
    if username:
        result = await db.execute(select(AdminUser).where(AdminUser.username == username))
        admin = result.scalar_one_or_none()
    elif admin_id:
        # admin_id 可能是整数或字符串（历史兼容），尝试整数转换
        try:
            int_id = int(admin_id)
            result = await db.execute(select(AdminUser).where(AdminUser.id == int_id))
            admin = result.scalar_one_or_none()
        except (ValueError, TypeError):
            # 如果无法转换为整数，返回认证失败
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的管理员Token")

    if admin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="管理员不存在")
    if not admin.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已禁用")
    return admin
