# -*- coding: utf-8 -*-
"""
管理员通知系统路由
商脉平台 Phase 2 - Sprint 1
POST /admin/notifications  (群发通知)
GET  /admin/notifications   (通知历史)
"""
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.admin_user import AdminUser
from app.api.admin.auth import get_current_admin
from app.models.member import Member

router = APIRouter(prefix="/notifications", tags=["管理员-通知"])


class NotificationRecord(BaseModel):
    id: str
    title: str
    content: str
    sent_at: str
    recipient_count: int


class NotificationListResponse(BaseModel):
    notifications: list[NotificationRecord]
    total: int


class SendNotificationRequest(BaseModel):
    title: str
    content: str
    target: str = "all"  # "all" | "active" | "inactive"


class NotificationStore:
    """简单内存存储，正式环境应存数据库"""
    _notifications: list[dict] = []


@router.post("")
async def send_notification(
    body: SendNotificationRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    # 统计目标会员数
    query = select(func.count(Member.id))
    if body.target == "active":
        from app.models.member import MemberStatus
        query = query.where(Member.status == MemberStatus.ACTIVE)
    elif body.target == "inactive":
        from app.models.member import MemberStatus
        query = query.where(Member.status == MemberStatus.INACTIVE)

    count = await db.scalar(query) or 0

    record = {
        "id": str(uuid4()),
        "title": body.title,
        "content": body.content,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "recipient_count": count,
    }
    NotificationStore._notifications.insert(0, record)

    # 实际推送逻辑（目前仅记录）
    return {
        "code": 0,
        "message": f"通知已发送",
        "data": {
            "id": record["id"],
            "recipient_count": count,
        }
    }


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    admin: AdminUser = Depends(get_current_admin),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    all_notes = NotificationStore._notifications
    total = len(all_notes)
    start = (page - 1) * page_size
    end = start + page_size
    page_notes = all_notes[start:end]

    return NotificationListResponse(
        notifications=[NotificationRecord(**n) for n in page_notes],
        total=total,
    )
