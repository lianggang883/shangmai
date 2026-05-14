from datetime import datetime
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.activity import Activity, ActivityParticipant, ActivityStatus, ActivityType
from app.models.member import Member
from app.dependencies.auth import get_current_member
from app.schemas.common import success, fail
from app.services.game import game_engine

router = APIRouter()  # NO prefix - main.py provides /api/v1/activities


@router.get("")
async def list_activities(
    status: str = None, activity_type: str = None,
    limit: int = 20, offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    query = select(Activity).options(selectinload(Activity.organizer)).order_by(Activity.event_time.desc())
    if status:
        query = query.where(Activity.status == status)
    if activity_type:
        query = query.where(Activity.activity_type == activity_type)
    query = query.offset(offset).limit(limit)
    activities = (await db.execute(query)).scalars().all()
    count_q = select(func.count(Activity.id))
    if status: count_q = count_q.where(Activity.status == status)
    if activity_type: count_q = count_q.where(Activity.activity_type == activity_type)
    total = (await db.execute(count_q)).scalar()
    return success(data={
        "items": [{
            "id": str(a.id), "title": a.title, "activity_type": a.activity_type,
            "event_time": a.event_time.isoformat() if a.event_time else None,
            "location": a.location, "max_participants": a.max_participants,
            "current_participants": a.current_participants, "status": a.status,
            "organizer_name": a.organizer.name if a.organizer else None,
        } for a in activities], "total": total or 0,
    })


@router.post("")
async def create_activity(
    title: str = Body(...), description: str = Body(""),
    activity_type: str = Body("other"),
    event_time: str = Body(None), location: str = Body(""),
    max_participants: int = Body(20),
    current_member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    if current_member.action_power_balance < 5:
        return fail(code=402, message="行动力不足，发起活动需要5点")
    try:
        event_dt = datetime.fromisoformat(event_time.replace("Z", "+00:00")) if event_time else datetime.utcnow()
    except:
        event_dt = datetime.utcnow()
    activity = Activity(
        organizer_id=str(current_member.id), title=title, description=description,
        activity_type=activity_type, event_time=event_dt, location=location,
        max_participants=max_participants, current_participants=1,
        status=ActivityStatus.open.value,
    )
    db.add(activity)
    db.add(ActivityParticipant(activity_id=str(activity.id), member_id=str(current_member.id)))
    current_member.action_power_balance -= 5
    await db.commit()
    await db.refresh(activity)
    return success(data={"id": str(activity.id), "title": activity.title, "status": activity.status}, ap=5)


@router.get("/{activity_id}")
async def get_activity(activity_id: str, db: AsyncSession = Depends(get_db)):
    query = select(Activity).where(Activity.id == activity_id).options(
        selectinload(Activity.organizer),
        selectinload(Activity.participants).selectinload(ActivityParticipant.member),
    )
    activity = (await db.execute(query)).scalar_one_or_none()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    return success(data={
        "id": str(activity.id), "title": activity.title, "description": activity.description,
        "activity_type": activity.activity_type,
        "event_time": activity.event_time.isoformat() if activity.event_time else None,
        "location": activity.location, "max_participants": activity.max_participants,
        "current_participants": activity.current_participants, "status": activity.status,
        "organizer": {"id": str(activity.organizer.id), "name": activity.organizer.name},
        "participants": [{"id": str(p.member.id), "name": p.member.name} for p in activity.participants],
    })


@router.post("/{activity_id}/join")
async def join_activity(
    activity_id: str, current_member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    activity = (await db.execute(select(Activity).where(Activity.id == activity_id))).scalar_one_or_none()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    if activity.status != ActivityStatus.open.value:
        return fail(message="活动已关闭")
    if activity.current_participants >= activity.max_participants:
        return fail(message="活动人数已满")
    existing = (await db.execute(select(ActivityParticipant).where(
        ActivityParticipant.activity_id == activity_id,
        ActivityParticipant.member_id == str(current_member.id)))).scalar_one_or_none()
    if existing:
        return fail(message="已参加该活动")
    db.add(ActivityParticipant(activity_id=activity_id, member_id=str(current_member.id)))
    activity.current_participants += 1
    if activity.current_participants >= activity.max_participants:
        activity.status = ActivityStatus.full.value
    await db.commit()

    # 触发游戏积分：参加活动
    game_result = await game_engine.on_action(str(current_member.id), "ATTEND_EVENT")

    return success(data={
        "joined": True,
        "game_reward": {
            "points": game_result.get("points_earned", 0),
            "exp": game_result.get("exp_earned", 0),
            "level_up": game_result.get("level_up", False),
            "badge": game_result.get("badge_unlocked"),
            "message": f"参加活动 +{game_result.get('points_earned', 0)}积分",
        }
    })


@router.delete("/{activity_id}/join")
async def leave_activity(
    activity_id: str, current_member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    participant = (await db.execute(select(ActivityParticipant).where(
        ActivityParticipant.activity_id == activity_id,
        ActivityParticipant.member_id == str(current_member.id)))).scalar_one_or_none()
    if not participant:
        return fail(message="未参加该活动")
    await db.delete(participant)
    activity = (await db.execute(select(Activity).where(Activity.id == activity_id))).scalar_one_or_none()
    if activity:
        activity.current_participants = max(0, activity.current_participants - 1)
        if activity.status == ActivityStatus.full.value:
            activity.status = ActivityStatus.open.value
    await db.commit()
    return success(data={"left": True})
