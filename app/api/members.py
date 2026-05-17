"""会员模块"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, delete, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_member
from app.database import get_db
from app.models.member import Member, MemberRole, MemberInterest, MemberDiagnosis
from app.schemas.members import (
    MemberProfile, NameCardData, CoachDiagnosisData,
)
from app.schemas.common import ApiResponse, success, fail

router = APIRouter()

# ============ 2026-05-10 新增端点 ============

@router.get("/", response_model=ApiResponse)
async def list_members(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_member: Member = Depends(get_current_member),
):
    """会员列表"""
    offset = (page - 1) * page_size
    result = await db.execute(
        select(Member)
        .where(Member.id != current_member.id)
        .order_by(Member.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    members = result.scalars().all()
    return success({
        "items": [
            {
                "id": m.id,
                "name": m.name,
                "company": m.company,
                "title": m.title,
                "level": m.level,
                "action_power_balance": m.action_power_balance,
            }
            for m in members
        ],
        "page": page,
        "page_size": page_size,
    })


@router.get("/recommend", response_model=ApiResponse)
async def recommend_members(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_member: Member = Depends(get_current_member),
):
    """推荐会员（按行动力排序）"""
    result = await db.execute(
        select(Member)
        .where(Member.id != current_member.id)
        .order_by(Member.action_power_balance.desc())
        .limit(limit)
    )
    members = result.scalars().all()
    return success([
        {
            "id": m.id,
            "name": m.name,
            "company": m.company,
            "title": m.title,
            "level": m.level,
        }
        for m in members
    ])


@router.get("/search", response_model=ApiResponse)
async def search_members(
    q: str = Query(..., min_length=1, max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_member: Member = Depends(get_current_member),
):
    """搜索会员"""
    offset = (page - 1) * page_size
    search = f"%{q}%"
    result = await db.execute(
        select(Member)
        .where(
            Member.id != current_member.id,
            or_(
                Member.name.like(search),
                Member.company.like(search),
                Member.title.like(search),
            )
        )
        .offset(offset)
        .limit(page_size)
    )
    members = result.scalars().all()
    return success({
        "items": [
            {
                "id": m.id,
                "name": m.name,
                "company": m.company,
                "title": m.title,
                "level": m.level,
            }
            for m in members
        ],
        "page": page,
        "page_size": page_size,
    })


@router.get("/me", response_model=ApiResponse)
async def get_my_profile(
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户资料"""
    roles_result = await db.execute(
        select(MemberRole).where(MemberRole.member_id == member.id)
    )
    roles = roles_result.scalars().all()

    interests_result = await db.execute(
        select(MemberInterest).where(MemberInterest.member_id == member.id)
    )
    interests = interests_result.scalars().all()

    profile = MemberProfile(
        id=member.id,
        phone=member.phone,
        nickname=member.name,
        name=member.name,
        avatar=None,
        bio=None,
        company=member.company,
        title=member.title,
        city=None,
        wechat=None,
        industries=[],
        resources_have=[],
        resources_need=[],
        roles=[r.role_code for r in roles],
        interests=[i.tag_name for i in interests],
        action_power=member.action_power_balance,
        action_power_balance=member.action_power_balance,
        total_action_power=member.action_power_balance + member.action_power_frozen,
        level=member.level,
        referral_code=generate_referral_code(member.id),
        created_at=member.created_at.isoformat() if member.created_at else None,
        updated_at=member.updated_at.isoformat() if member.updated_at else None,
    )
    return success(data=profile.model_dump())


@router.get("/{member_id}", response_model=ApiResponse)
async def get_member_detail(
    member_id: str,
    db: AsyncSession = Depends(get_db),
    current_member: Member = Depends(get_current_member),
):
    """会员详情"""
    result = await db.execute(
        select(Member).where(Member.id == member_id)
    )
    member = result.scalar_one_or_none()
    if not member:
        return fail(message="会员不存在")
    return success({
        "id": member.id,
        "name": member.name,
        "company": member.company,
        "title": member.title,
        "phone": member.phone,
        "avatar": member.avatar,
        "level": member.level,
        "action_power_balance": member.action_power_balance,
        "action_power_frozen": member.action_power_frozen,
    })





def generate_referral_code(member_id: str) -> str:
    """从 member_id 生成 8 位引荐码"""
    import base64
    b = base64.urlsafe_b64encode(member_id.replace("-", "").encode())[:6]
    return b.decode().upper() + "SH"



@router.put("/me", response_model=ApiResponse)
async def update_profile(
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """更新资料（占位，后续接入表单）"""
    return success(data={"updated": True})


@router.get("/{member_id}/namecard", response_model=ApiResponse)
async def get_namecard(
    member_id: str,
    current_member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """查看名片"""
    if member_id == "me":
        member_id = current_member.id

    result = await db.execute(
        select(Member).where(Member.id == member_id)
    )
    target = result.scalar_one_or_none()
    if not target:
        return success(data={"error": "会员不存在", "member_id": member_id})

    # Get interests separately
    cur_interests_result = await db.execute(
        select(MemberInterest).where(MemberInterest.member_id == current_member.id)
    )
    cur_interests = set(i.tag_name for i in cur_interests_result.scalars().all())

    tgt_interests_result = await db.execute(
        select(MemberInterest).where(MemberInterest.member_id == member_id)
    )
    tgt_interests = set(i.tag_name for i in tgt_interests_result.scalars().all())

    overlap = len(cur_interests & tgt_interests)
    match_score = min(100, overlap * 20 + 30)

    # Get target roles
    tgt_roles_result = await db.execute(
        select(MemberRole).where(MemberRole.member_id == member_id)
    )
    tgt_roles = [r.role_code for r in tgt_roles_result.scalars().all()]

    action_power_after = max(0, current_member.action_power_balance - 2)

    namecard = NameCardData(
        member_id=target.id,
        nickname=target.name,
        avatar=None,
        company=target.company,
        title=target.title,
        city=None,
        industries=[],
        resources_have=[],
        resources_need=[],
        bio=None,
        wechat=None,
        match_score=match_score,
        action_power_after=action_power_after,
    )
    # Add extra fields not in NameCardData
    result_data = namecard.model_dump()
    result_data["roles"] = tgt_roles
    result_data["interests"] = list(tgt_interests)
    return success(data=result_data, ap=2)


# ========== Interests ==========

class InterestItem(BaseModel):
    tag_name: str


class InterestsUpdateRequest(BaseModel):
    interests: List[InterestItem]


@router.get("/me/interests", response_model=ApiResponse)
async def get_my_interests(
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户兴趣标签列表"""
    interests_result = await db.execute(
        select(MemberInterest).where(MemberInterest.member_id == member.id)
    )
    interests = interests_result.scalars().all()
    return success(data=[
        {"tag_name": i.tag_name, "weight": float(i.weight) if i.weight else 0.5}
        for i in interests
    ])


@router.put("/me/interests", response_model=ApiResponse)
async def update_interests(
    req: InterestsUpdateRequest,
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """更新兴趣标签"""
    await db.execute(
        delete(MemberInterest).where(MemberInterest.member_id == member.id)
    )
    for item in req.interests:
        new_interest = MemberInterest(
            member_id=member.id,
            tag_name=item.tag_name,
        )
        db.add(new_interest)
    await db.commit()
    return success(data={"updated": True, "count": len(req.interests)}, ap=2)


# ========== Roles ==========

class RoleItem(BaseModel):
    role_type: str
    role_code: str
    weight: Optional[float] = None
    is_primary: Optional[bool] = False


class RolesUpdateRequest(BaseModel):
    roles: List[RoleItem]


@router.get("/me/roles", response_model=ApiResponse)
async def get_my_roles(
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户角色标签列表"""
    roles_result = await db.execute(
        select(MemberRole).where(MemberRole.member_id == member.id)
    )
    roles = roles_result.scalars().all()
    return success(data=[{
        "role_type": r.role_type,
        "role_code": r.role_code,
        "weight": float(r.weight) if r.weight else None,
        "is_primary": r.is_primary,
    } for r in roles])


@router.put("/me/roles", response_model=ApiResponse)
async def update_roles(
    req: RolesUpdateRequest,
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """更新角色标签"""
    await db.execute(
        delete(MemberRole).where(MemberRole.member_id == member.id)
    )
    for item in req.roles:
        new_role = MemberRole(
            member_id=member.id,
            role_type=item.role_type,
            role_code=item.role_code,
            weight=item.weight,
            is_primary=item.is_primary or False
        )
        db.add(new_role)
    await db.commit()
    return success(data={"updated": True, "count": len(req.roles)}, ap=3)


# ========== Diagnosis ==========

@router.get("/me/diagnosis", response_model=ApiResponse)
async def get_diagnosis(
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """获取教练诊断"""
    result = await db.execute(
        select(MemberDiagnosis).where(MemberDiagnosis.member_id == member.id)
    )
    diagnoses = result.scalars().all()

    layers = {}
    bottleneck_score = 10
    bottleneck = "spirit"

    for d in diagnoses:
        layer_name = d.layer
        layers[layer_name] = {"score": d.score, "confidence": float(d.confidence)}
        if d.score < bottleneck_score:
            bottleneck_score = d.score
            bottleneck = layer_name

    for layer in ("environment", "behavior", "capability", "belief", "identity", "spirit"):
        if layer not in layers:
            layers[layer] = {"score": 5, "confidence": 0.5}

    strategy_map = {
        "environment": "环境优化",
        "behavior": "行为调整",
        "capability": "能力提升",
        "belief": "信念重塑",
        "identity": "身份认同",
        "spirit": "精神觉醒",
    }

    diagnosis_data = CoachDiagnosisData(
        diagnosis_id=member.id[:8],
        status="completed" if diagnoses else "pending",
        summary=f"您在{len(diagnoses)}个维度完成诊断，主要瓶颈：{bottleneck}",
        strengths=["善于整合资源", "行动力强"],
        weaknesses=["时间管理待提升", "精力分配不均"],
        suggestions=["建议提升能力层", "加强信念层建设"],
        created_at=diagnoses[0].diagnosed_at.isoformat() if diagnoses else None,
    )
    return success(data=diagnosis_data.model_dump())
