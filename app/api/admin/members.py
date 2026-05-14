"""管理后台 - 会员管理"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_admin
from app.database import get_db
from app.models.member import Member, MemberRole, MemberInterest
from app.schemas.common import ApiResponse, success

router = APIRouter()


async def _get_members_list(
    page: int,
    page_size: int,
    keyword: str,
    status: str,
    db: AsyncSession,
) -> dict:
    """获取会员列表的通用逻辑"""
    # 构建查询
    query = select(Member)
    
    # 关键词筛选
    if keyword:
        query = query.where(
            (Member.name.contains(keyword)) |
            (Member.phone.contains(keyword)) |
            (Member.company.contains(keyword))
        )
    
    # 状态筛选
    if status:
        query = query.where(Member.status == status)
    
    # 获取总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # 分页
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Member.created_at.desc())
    
    result = await db.execute(query)
    members = result.scalars().all()
    
    items = []
    for m in members:
        # 获取角色
        roles_result = await db.execute(
            select(MemberRole).where(MemberRole.member_id == m.id)
        )
        roles = roles_result.scalars().all()
        role_codes = [r.role_code for r in roles] if roles else []
        
        items.append({
            "id": str(m.id),
            "name": m.name or "-",
            "company": m.company or "-",
            "title": m.title or "-",
            "phone": m.phone or "-",
            "role": role_codes[0] if role_codes else "-",
            "status": m.status or "active",
            "level": m.level or 1,
            "action_power": m.action_power_balance or 0,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("", response_model=ApiResponse)
async def list_members(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    keyword: str = Query("", description="搜索关键词"),
    status: str = Query("", description="状态筛选"),
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """会员列表"""
    data = await _get_members_list(page, page_size, keyword, status, db)
    return success(data=data)


@router.get("/list", response_model=ApiResponse)
async def list_members_alias(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    keyword: str = Query("", description="搜索关键词"),
    status: str = Query("", description="状态筛选"),
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """会员列表（/list 别名）"""
    data = await _get_members_list(page, page_size, keyword, status, db)
    return success(data=data)


@router.get("/{member_id}", response_model=ApiResponse)
async def get_member_detail(
    member_id: str,
    admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """会员详情"""
    result = await db.execute(
        select(Member).where(Member.id == member_id)
    )
    member = result.scalar_one_or_none()
    if not member:
        return success(data={"error": "会员不存在"}, message="会员不存在")

    # 获取角色
    roles_result = await db.execute(
        select(MemberRole).where(MemberRole.member_id == member.id)
    )
    roles = roles_result.scalars().all()

    # 获取兴趣
    interests_result = await db.execute(
        select(MemberInterest).where(MemberInterest.member_id == member.id)
    )
    interests = interests_result.scalars().all()

    return success(data={
        "id": str(member.id),
        "name": member.name,
        "phone": member.phone,
        "company": member.company,
        "title": member.title,
        "status": member.status,
        "level": member.level,
        "action_power_balance": member.action_power_balance,
        "action_power_frozen": member.action_power_frozen,
        "roles": [{"role_type": r.role_type, "role_code": r.role_code} for r in roles],
        "interests": [i.tag_name for i in interests],
        "created_at": member.created_at.isoformat() if member.created_at else None,
        "updated_at": member.updated_at.isoformat() if member.updated_at else None,
    })