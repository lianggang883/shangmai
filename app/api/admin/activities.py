# -*- coding: utf-8 -*-
"""
管理员活动审核路由
商脉平台 Phase 2 - Sprint 1
GET /admin/activities
PUT /admin/activities/{id}/close
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.admin_user import AdminUser
from app.api.admin.auth import get_current_admin
from app.models.activity import Activity, ActivityStatus

router = APIRouter(prefix="/activities", tags=["管理员-活动"])


class ActivityItem(BaseModel):
    id: str
    title: str
    type: str
    status: str
    organizer_id: str
    max_participants: int
    current_participants: int
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class ActivityListResponse(BaseModel):
    activities: list[ActivityItem]
    total: int


class ReviewRequest(BaseModel):
    action: str  # "close" | "open" | "cancel"


@router.get("", response_model=ActivityListResponse)
async def list_activities(
    admin: AdminUser = Depends(get_current_admin),
    status: str = Query(None, description="筛选状态: open/closed/cancelled"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = select(Activity).order_by(Activity.created_at.desc())
    if status:
        query = query.where(Activity.status == status)

    # 总数
    count_q = select(func.count()).select_from(Activity)
    if status:
        count_q = count_q.where(Activity.status == status)
    total = await db.scalar(count_q)

    # 分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    rows = result.scalars().all()

    activities = []
    for a in rows:
        activities.append(ActivityItem(
            id=a.id,
            title=a.title or "(无标题)",
            type=a.activity_type or "other",
            status=a.status or "open",
            organizer_id=a.organizer_id or "",
            max_participants=a.max_participants or 0,
            current_participants=getattr(a, 'current_participants', 0) or 0,
            created_at=str(a.created_at) if a.created_at else "",
        ))

    return ActivityListResponse(activities=activities, total=total or 0)


@router.put("/{activity_id}/review")
async def review_activity(
    activity_id: str,
    body: ReviewRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Activity).where(Activity.id == activity_id))
    activity = result.scalar_one_or_none()
    if not activity:
        return {"code": 404, "message": "活动不存在"}

    if body.action == "close":
        activity.status = ActivityStatus.closed
    elif body.action == "open":
        activity.status = ActivityStatus.open
    elif body.action == "cancel":
        activity.status = ActivityStatus.cancelled
    else:
        return {"code": 400, "message": "无效操作"}

    await db.commit()
    return {"code": 0, "message": "操作成功"}


from sqlalchemy import func
