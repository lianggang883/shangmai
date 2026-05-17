"""商脉系统 · 通知模块"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_member
from app.database import get_db
from app.models.member import Member
from app.schemas.common import ApiResponse, success

router = APIRouter()


@router.get("", response_model=ApiResponse)
async def list_notifications(
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    unread_only: bool = False,
):
    """通知列表（模拟数据，后续接入真实通知表）"""
    # TODO: 接入 Notification 模型后替换为真实查询
    now = datetime.now()
    mock_notifications = [
        {
            "id": "notif-001",
            "type": "system",
            "title": "欢迎加入商脉",
            "content": "完善您的资料，开启精准匹配之旅",
            "is_read": True,
            "created_at": (now - timedelta(days=3)).isoformat(),
        },
        {
            "id": "notif-002",
            "type": "activity",
            "title": "新活动推荐",
            "content": "「T001-4联调测试活动」即将开始，点击查看详情",
            "is_read": False,
            "created_at": (now - timedelta(hours=5)).isoformat(),
        },
        {
            "id": "notif-003",
            "type": "match",
            "title": "匹配成功",
            "content": "系统为您推荐了3位潜在合作伙伴",
            "is_read": False,
            "created_at": (now - timedelta(hours=2)).isoformat(),
        },
        {
            "id": "notif-004",
            "type": "system",
            "title": "行动力到账",
            "content": "每日签到奖励 +50 行动力已到账",
            "is_read": False,
            "created_at": (now - timedelta(minutes=30)).isoformat(),
        },
        {
            "id": "notif-005",
            "type": "referral",
            "title": "引荐奖励",
            "content": "您邀请的好友已完成注册，获得+100行动力奖励",
            "is_read": True,
            "created_at": (now - timedelta(days=1)).isoformat(),
        },
    ]
    
    items = mock_notifications[:limit]
    if unread_only:
        items = [n for n in items if not n["is_read"]][:limit]
    
    unread_count = sum(1 for n in mock_notifications if not n["is_read"])
    
    return success(data={
        "items": items,
        "total": len(mock_notifications),
        "unread_count": unread_count,
    })


@router.put("/{notif_id}/read", response_model=ApiResponse)
async def mark_notification_read(
    notif_id: str,
    member: Member = Depends(get_current_member),
):
    """标记通知为已读"""
    return success(data={"marked_read": True, "notif_id": notif_id})


@router.post("/read-all", response_model=ApiResponse)
async def mark_all_read(
    member: Member = Depends(get_current_member),
):
    """全部标记已读"""
    return success(data={"marked_all_read": True})
