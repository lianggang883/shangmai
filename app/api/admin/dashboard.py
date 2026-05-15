# -*- coding: utf-8 -*-
"""
管理员仪表盘路由
商脉平台 Phase 2 - Sprint 1
GET /admin/dashboard/stats
"""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.admin_user import AdminUser
from app.api.admin.auth import get_current_admin
from app.models.member import Member, MemberStatus
from app.models.activity import Activity, ActivityStatus
from app.models.billing import ActionPowerTransaction, TxType
from app.models.cooperation import CooperationProject

router = APIRouter(prefix="/dashboard", tags=["管理员-仪表盘"])


class TrendPoint(BaseModel):
    date: str
    new_members: int
    new_activities: int


class DashboardStatsResponse(BaseModel):
    total_members: int
    active_members: int
    new_members_today: int
    total_activities: int
    active_activities: int
    total_recharges: int
    total_cooperations: int
    daily_trend: list[TrendPoint]


@router.get("/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    today = datetime.now(timezone.utc).date()
    today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)

    total_members = await db.scalar(select(func.count(Member.id)))
    active_members = await db.scalar(
        select(func.count(Member.id)).where(Member.status == MemberStatus.ACTIVE)
    )
    new_members_today = await db.scalar(
        select(func.count(Member.id)).where(Member.created_at >= today_start)
    )
    total_activities = await db.scalar(select(func.count(Activity.id)))
    active_activities = await db.scalar(
        select(func.count(Activity.id)).where(Activity.status == ActivityStatus.open)
    )
    total_recharges = await db.scalar(
        select(func.coalesce(func.sum(ActionPowerTransaction.amount), 0))
        .where(ActionPowerTransaction.tx_type == TxType.RECHARGE)
    )
    total_cooperations = await db.scalar(select(func.count(CooperationProject.id)))

    daily_trend = []
    for i in range(7):
        day = today - timedelta(days=6 - i)
        day_start = datetime.combine(day, datetime.min.time()).replace(tzinfo=timezone.utc)
        day_end = datetime.combine(day, datetime.max.time()).replace(tzinfo=timezone.utc)
        new_m = await db.scalar(
            select(func.count(Member.id))
            .where(Member.created_at >= day_start, Member.created_at <= day_end)
        )
        new_a = await db.scalar(
            select(func.count(Activity.id))
            .where(Activity.created_at >= day_start, Activity.created_at <= day_end)
        )
        daily_trend.append(TrendPoint(
            date=day.isoformat(),
            new_members=new_m or 0,
            new_activities=new_a or 0,
        ))

    return DashboardStatsResponse(
        total_members=total_members or 0,
        active_members=active_members or 0,
        new_members_today=new_members_today or 0,
        total_activities=total_activities or 0,
        active_activities=active_activities or 0,
        total_recharges=int(total_recharges or 0),
        total_cooperations=total_cooperations or 0,
        daily_trend=daily_trend,
    )
