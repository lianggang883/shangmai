# -*- coding: utf-8 -*-
"""
管理员 SKILL 监控路由
商脉平台 Phase 2 - Sprint 1
GET /admin/skills/stats
"""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.admin_user import AdminUser
from app.api.admin.auth import get_current_admin
from app.models.agent import SkillInvocation, SkillInvocationStatus

router = APIRouter(prefix="/skills", tags=["管理员-SKILL监控"])


class SkillUsageStat(BaseModel):
    skill_type: str
    total_invocations: int
    success_count: int
    failure_count: int
    success_rate: float


class SkillTrendPoint(BaseModel):
    date: str
    mece: int
    seven_steps: int
    role: int
    coach: int
    other: int


class SkillStatsResponse(BaseModel):
    total_invocations: int
    total_members_using: int
    usage_by_type: list[SkillUsageStat]
    daily_trend: list[SkillTrendPoint]


def _skill_type_key(skill_type: str) -> str:
    """归一化SKILL类型名称"""
    s = (skill_type or "").lower()
    if "mece" in s:
        return "mece"
    if "seven" in s or "七步" in s:
        return "seven_steps"
    if "role" in s or "角色" in s:
        return "role"
    if "coach" in s or "教练" in s:
        return "coach"
    if "industry" in s or "chain" in s or "产业" in s:
        return "industry"
    if "secretary" in s or "秘书" in s:
        return "secretary"
    return "other"


@router.get("/stats", response_model=SkillStatsResponse)
async def get_skill_stats(
    days: int = Query(7, ge=1, le=30),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # 总调用数
    total_invocations = await db.scalar(
        select(func.count(SkillInvocation.id))
        .where(SkillInvocation.created_at >= since)
    ) or 0

    # 使用SKILL的独立会员数
    total_members_using = await db.scalar(
        select(func.count(func.distinct(SkillInvocation.member_id)))
        .where(SkillInvocation.created_at >= since)
    ) or 0

    # 按类型统计
    type_stats: dict[str, dict] = {}
    result = await db.execute(
        select(SkillInvocation).where(SkillInvocation.created_at >= since)
    )
    all_invocations = result.scalars().all()

    for inv in all_invocations:
        key = _skill_type_key(getattr(inv, 'skill_type', '') or '')
        if key not in type_stats:
            type_stats[key] = {"total": 0, "success": 0, "failed": 0}
        type_stats[key]["total"] += 1
        status = getattr(inv, 'status', '') or ''
        if status == SkillInvocationStatus.COMPLETED:
            type_stats[key]["success"] += 1
        else:
            type_stats[key]["failed"] += 1

    usage_by_type = [
        SkillUsageStat(
            skill_type=k,
            total_invocations=v["total"],
            success_count=v["success"],
            failure_count=v["failed"],
            success_rate=round(v["success"] / v["total"] * 100, 1) if v["total"] > 0 else 0,
        )
        for k, v in sorted(type_stats.items(), key=lambda x: -x[1]["total"])
    ]

    # 每日趋势
    today = datetime.now(timezone.utc).date()
    daily_trend = []
    for i in range(days):
        day = today - timedelta(days=days - 1 - i)
        day_start = datetime.combine(day, datetime.min.time()).replace(tzinfo=timezone.utc)
        day_end = datetime.combine(day, datetime.max.time()).replace(tzinfo=timezone.utc)

        day_q = select(SkillInvocation).where(
            SkillInvocation.created_at >= day_start,
            SkillInvocation.created_at <= day_end,
        )
        day_result = await db.execute(day_q)
        day_invs = day_result.scalars().all()

        counts = {"mece": 0, "seven_steps": 0, "role": 0, "coach": 0, "industry": 0, "secretary": 0, "other": 0}
        for inv in day_invs:
            k = _skill_type_key(getattr(inv, 'skill_type', '') or '')
            counts[k] = counts.get(k, 0) + 1

        daily_trend.append(SkillTrendPoint(
            date=day.isoformat(),
            mece=counts["mece"],
            seven_steps=counts["seven_steps"],
            role=counts["role"],
            coach=counts["coach"],
            other=counts.get("other", 0) + counts.get("industry", 0) + counts.get("secretary", 0),
        ))

    return SkillStatsResponse(
        total_invocations=total_invocations,
        total_members_using=total_members_using,
        usage_by_type=usage_by_type,
        daily_trend=daily_trend,
    )
