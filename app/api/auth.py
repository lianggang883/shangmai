"""认证模块 - 免验证码版（手机号即唯一标识）"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from app.config import settings
from app.database import get_db
from app.dependencies.auth import create_access_token, create_refresh_token
from app.models.member import Member
from app.schemas.auth import RegisterRequest, LoginRequest, RefreshRequest
from app.schemas.common import success, fail

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@router.post("/register", response_model=None)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """注册：手机号为唯一标识，免验证码"""
    result = await db.execute(select(Member).where(Member.phone == req.phone))
    existing = result.scalar_one_or_none()
    if existing:
        return fail(code=400, message="该手机号已注册，请直接登录")
    member = Member(
        id=str(uuid4()), phone=req.phone,
        name=req.nickname or req.name or f"用户{req.phone[-4:]}",
        level=1, exp_points=0,
        action_power_balance=settings.ACTION_POWER_MONTHLY_FREE_LV1,
        action_power_frozen=0, status="ACTIVE",
    )
    db.add(member)
    await db.flush()
    access_token = create_access_token(data={"sub": member.id})
    refresh_token = create_refresh_token(data={"sub": member.id})
    return success(data={
        "member_id": member.id, "phone": member.phone, "name": member.name,
        "level": member.level, "action_power_balance": member.action_power_balance,
        "access_token": access_token, "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "is_new": True,
        "message": f"注册成功！初始{settings.ACTION_POWER_MONTHLY_FREE_LV1}点行动力",
    })


@router.post("/login", response_model=None)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """登录：免验证码，手机号不存在则自动注册（One-tap login）"""
    result = await db.execute(select(Member).where(Member.phone == req.phone))
    member = result.scalar_one_or_none()
    is_new = False
    if not member:
        # 不存在 → 自动注册
        member = Member(
            id=str(uuid4()), phone=req.phone, name=f"用户{req.phone[-4:]}",
            level=1, exp_points=0,
            action_power_balance=settings.ACTION_POWER_MONTHLY_FREE_LV1,
            action_power_frozen=0, status="ACTIVE",
        )
        db.add(member)
        await db.flush()
        is_new = True
    access_token = create_access_token(data={"sub": member.id})
    refresh_token = create_refresh_token(data={"sub": member.id})
    return success(data={
        "access_token": access_token, "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "member_id": member.id, "name": member.name,
        "phone": member.phone,
        "action_power_balance": member.action_power_balance,
        "is_new": is_new,
        "message": f"注册成功，赠送{settings.ACTION_POWER_MONTHLY_FREE_LV1}点行动力" if is_new else "登录成功",
    })


@router.post("/refresh", response_model=None)
async def refresh_token(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    from jose import JWTError, jwt
    try:
        payload = jwt.decode(req.refresh_token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        member_id = payload.get("sub")
        if not member_id or payload.get("type") != "refresh":
            return fail(code=401, message="无效的刷新令牌")
    except JWTError:
        return fail(code=401, message="刷新令牌过期或失效")
    result = await db.execute(select(Member).where(Member.id == member_id))
    member = result.scalar_one_or_none()
    if not member:
        return fail(code=404, message="用户不存在")
    access_token = create_access_token(data={"sub": member.id})
    return success(data={
        "access_token": access_token, "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    })
