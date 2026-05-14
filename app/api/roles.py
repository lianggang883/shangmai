"""Roles API - 会员角色管理"""
from datetime import datetime
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..models import MemberRole
from ..schemas.common import ApiResponse, success, fail

router = APIRouter(prefix="/api/v1/members", tags=["roles"])

VALID_ROLE_CODES = ['partner', 'customer', 'inventor', 'supplier', 'mentor', 'expert', 'investor', 'cross_industry', 'team', 'media', 'ai_advisor']
VALID_ROLE_TYPES = ['PROVIDE', 'SEEK']

ROLE_TYPES = [
    {"code": "partner", "name": "同行/合作伙伴", "desc": "协同共赢者", "weight_range": "1.0-2.0"},
    {"code": "customer", "name": "客户/用户", "desc": "价值验证者", "weight_range": "1.0-2.0"},
    {"code": "mentor", "name": "导师/贵人", "desc": "战略引领者", "weight_range": "1.5-3.0"},
    {"code": "investor", "name": "投资人/资本方", "desc": "增长加速器", "weight_range": "2.0-5.0"},
    {"code": "supplier", "name": "供应商/服务商", "desc": "基础支撑者", "weight_range": "1.0-2.0"},
    {"code": "expert", "name": "行业专家/智库", "desc": "专业智囊团", "weight_range": "1.5-3.0"},
    {"code": "cross_industry", "name": "跨界朋友", "desc": "创新催化剂", "weight_range": "1.0-2.5"},
    {"code": "team", "name": "团队/下属", "desc": "执行落地者", "weight_range": "1.0-2.0"},
    {"code": "media", "name": "媒体/KOL", "desc": "影响力放大器", "weight_range": "1.5-3.0"},
    {"code": "ai_advisor", "name": "AI顾问", "desc": "垂直智能体", "weight_range": "1.0-2.0"},
]


class RoleInput(BaseModel):
    role_type: str
    role_code: str
    weight: float = 0.50
    is_primary: bool = False


class RoleBatchInput(BaseModel):
    roles: list[RoleInput]


@router.get("/types")
async def get_role_types():
    """获取角色类型列表（十维角色标识）"""
    return success(ROLE_TYPES)


@router.get("/{member_id}/roles")
async def get_member_roles(member_id: str, db: AsyncSession = Depends(get_db)):
    roles_result = await db.execute(select(MemberRole).where(MemberRole.member_id == member_id))
    roles = roles_result.scalars().all()
    return success(data=[
        {
            "id": r.id,
            "member_id": r.member_id,
            "role_type": r.role_type,
            "role_code": r.role_code,
            "weight": float(r.weight) if r.weight else 0.5,
            "is_primary": r.is_primary,
            "created_at": r.created_at.isoformat() if r.created_at else None
        }
        for r in roles
    ])


@router.put("/{member_id}/roles")
async def put_member_roles(member_id: str, data: RoleBatchInput, db: AsyncSession = Depends(get_db)):
    # Validate role_type and role_code
    for role in data.roles:
        if role.role_type not in VALID_ROLE_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid role_type: {role.role_type}. Must be one of {VALID_ROLE_TYPES}")
        if role.role_code not in VALID_ROLE_CODES:
            raise HTTPException(status_code=400, detail=f"Invalid role_code: {role.role_code}. Must be one of {VALID_ROLE_CODES}")

    # Delete existing roles
    await db.execute(delete(MemberRole).where(MemberRole.member_id == member_id))

    # Add new roles
    for role in data.roles:
        new_role = MemberRole(
            id=str(uuid4()),
            member_id=member_id,
            role_type=role.role_type,
            role_code=role.role_code,
            weight=role.weight,
            is_primary=role.is_primary,
            created_at=datetime.utcnow()
        )
        db.add(new_role)

    await db.commit()

    # Return updated roles
    roles_result = await db.execute(select(MemberRole).where(MemberRole.member_id == member_id))
    roles = roles_result.scalars().all()
    return success(data=[
        {
            "id": r.id,
            "member_id": r.member_id,
            "role_type": r.role_type,
            "role_code": r.role_code,
            "weight": float(r.weight) if r.weight else 0.5,
            "is_primary": r.is_primary,
            "created_at": r.created_at.isoformat() if r.created_at else None
        }
        for r in roles
    ])
