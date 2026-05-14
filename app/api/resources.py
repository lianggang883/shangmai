# -*- coding: utf-8 -*-
"""客户资源 API — 做任务得积分体系"""
from uuid import uuid4
from datetime import datetime, date

from fastapi import APIRouter, Depends
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_member
from app.models.member import Member
from app.models.resource import Resource
from app.models.game import GameProfile
from app.schemas.common import success, fail

router = APIRouter()

# 积分奖励规则（做任务得积分）
POINT_REWARDS = {
    "resource_add": 10,      # 添加客户资源 +10分
    "daily_checkin": 10,     # 每日签到 +10分（已在game.py实现）
    "profile_complete": 30,  # 完善资料 +30分
    "activity_join": 15,     # 参加活动 +15分
    "invite_member": 20,     # 邀请新会员 +20分（已在referral.py实现）
}


async def _award_points(db: AsyncSession, member_id: str, points: int, reason: str):
    """给会员加积分，同时更新 GameProfile"""
    result = await db.execute(
        select(Member).where(Member.id == member_id)
    )
    member = result.scalar_one_or_none()
    if member:
        member.action_power_balance += points
        member.exp_points += points

    result2 = await db.execute(
        select(GameProfile).where(GameProfile.member_id == member_id)
    )
    profile = result2.scalar_one_or_none()
    if profile:
        profile.total_points = (profile.total_points or 0) + points
        profile.exp = (profile.exp or 0) + points
    await db.flush()
    return points


@router.post("/", response_model=None)
async def add_resource(
    req: dict,
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """
    录入客户资源（做任务得积分）
    POST /api/v1/resources/
    成功后奖励 10 行动力
    """
    company = req.get("company") or req.get("name")
    if not company:
        return fail(code=400, message="请填写公司名称")

    contact_name = req.get("contact_name") or req.get("name")
    if not contact_name:
        return fail(code=400, message="请填写联系人")

    # 保存资源
    resource = Resource(
        id=str(uuid4()),
        member_id=member.id,
        company=company,
        contact_name=contact_name,
        contact_phone=req.get("contact_phone") or req.get("phone"),
        position=req.get("position"),
        industry=req.get("industry"),
        region=req.get("region"),
        intro=req.get("intro"),
        needs=req.get("needs"),
        analysis_tags=req.get("analysis_tags", []),
        estimated_value=req.get("estimated_value", 0),
    )
    db.add(resource)

    # 做任务得积分：添加客户 +10分
    points = POINT_REWARDS["resource_add"]
    await _award_points(db, member.id, points, "录入客户资源")

    await db.commit()

    return success(data={
        "id": str(resource.id),
        "company": resource.company,
        "contact_name": resource.contact_name,
        "industry": resource.industry,
        "region": resource.region,
        "created_at": str(resource.created_at),
        "points_earned": points,
        "message": f"录入成功！+{points}行动力",
    })


@router.get("/", response_model=None)
async def list_resources(
    page: int = 1,
    page_size: int = 20,
    industry: str = None,
    region: str = None,
    starred: bool = None,
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """我的资源列表"""
    query = select(Resource).where(Resource.member_id == member.id)
    count_query = select(func.count(Resource.id)).where(Resource.member_id == member.id)

    if industry:
        query = query.where(Resource.industry == industry)
        count_query = count_query.where(Resource.industry == industry)
    if region:
        query = query.where(Resource.region == region)
        count_query = count_query.where(Resource.region == region)
    if starred is not None:
        query = query.where(Resource.is_starred == starred)
        count_query = count_query.where(Resource.is_starred == starred)

    total = (await db.execute(count_query)).scalar() or 0
    offset = (page - 1) * page_size
    query = query.order_by(desc(Resource.created_at)).offset(offset).limit(page_size)
    result = await db.execute(query)
    resources = result.scalars().all()

    return success(data={
        "total": total,
        "page": page,
        "page_size": page_size,
        "resources": [{
            "id": str(r.id),
            "company": r.company,
            "contact_name": r.contact_name,
            "contact_phone": r.contact_phone,
            "position": r.position,
            "industry": r.industry,
            "region": r.region,
            "intro": r.intro,
            "needs": r.needs,
            "analysis_tags": r.analysis_tags or [],
            "estimated_value": r.estimated_value,
            "is_starred": r.is_starred,
            "created_at": str(r.created_at),
        } for r in resources]
    })


@router.get("/my-count", response_model=None)
async def my_resource_count(
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """我的资源数量统计"""
    total = (await db.execute(
        select(func.count(Resource.id)).where(Resource.member_id == member.id)
    )).scalar() or 0

    return success(data={
        "total": total,
        "reward_points_per": POINT_REWARDS["resource_add"],
        "message": f"已录入 {total} 个客户，继续录入更多获得更多积分！"
    })


@router.patch("/{resource_id}/star", response_model=None)
async def toggle_star(
    resource_id: str,
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """收藏/取消收藏资源"""
    result = await db.execute(
        select(Resource).where(Resource.id == resource_id, Resource.member_id == member.id)
    )
    resource = result.scalar_one_or_none()
    if not resource:
        return fail(code=404, message="资源不存在")

    resource.is_starred = not resource.is_starred
    await db.commit()

    return success(data={
        "id": str(resource.id),
        "is_starred": resource.is_starred,
        "message": "已收藏" if resource.is_starred else "已取消收藏"
    })


@router.get("/point-rules", response_model=None)
async def get_point_rules():
    """积分规则说明"""
    return success(data={
        "rules": [
            {"action": "添加客户资源", "points": POINT_REWARDS["resource_add"], "desc": "录入客户企业名片"},
            {"action": "每日签到", "points": POINT_REWARDS["daily_checkin"], "desc": "每日签到获得积分，连续签到额外奖励"},
            {"action": "完善个人资料", "points": POINT_REWARDS["profile_complete"], "desc": "填写公司、职位等信息"},
            {"action": "参加活动", "points": POINT_REWARDS["activity_join"], "desc": "报名并参与任意活动"},
            {"action": "邀请新会员", "points": POINT_REWARDS["invite_member"], "desc": "成功邀请好友注册，双方各获得积分"},
        ],
        "levels": [
            {"level": 1, "min_exp": 0, "name": "新手"},
            {"level": 2, "min_exp": 100, "name": "达人"},
            {"level": 3, "min_exp": 500, "name": "精英"},
            {"level": 4, "min_exp": 1500, "name": "大师"},
            {"level": 5, "min_exp": 4000, "name": "传奇"},
            {"level": 6, "min_exp": 10000, "name": "宗师"},
        ]
    })
