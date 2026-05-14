"""关系模块 API - 真实数据库接入"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_member
from app.database import get_db
from app.models.member import Member
from app.models.relationship import (
    Relationship,
    Interaction,
    RelationshipStatus,
    DecayLevel,
    InteractionType,
)
from app.repositories.relationship_repo import RelationshipRepo
from app.schemas.common import ApiResponse, success, fail
from app.schemas.relations import (
    IcebreakRequest,
    InteractionRequest,
    FeedbackRequest,
    IcebreakData,
    InteractionData,
    FeedbackData,
    DecayAlertItem,
)
from app.services.game_service import game_service

router = APIRouter()


@router.get("", response_model=ApiResponse)
async def list_relations(
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的关系列表"""
    result = await db.execute(
        select(Relationship)
        .where(or_(Relationship.member_a == member.id, Relationship.member_b == member.id))
        .order_by(Relationship.total_score.desc())
    )
    relationships = result.scalars().all()
    items = []
    for rel in relationships:
        other_id = rel.member_b if rel.member_a == member.id else rel.member_a
        other_result = await db.execute(select(Member).where(Member.id == other_id))
        other_member = other_result.scalar_one_or_none()
        items.append({
            "id": rel.id,
            "member_id": other_id,
            "name": other_member.name if other_member else "Unknown",
            "status": rel.status,
            "total_score": float(rel.total_score) if rel.total_score else 0,
            "role_match_score": float(rel.role_match_score) if rel.role_match_score else 0,
            "industry_chain_score": float(rel.industry_chain_score) if rel.industry_chain_score else 0,
            "motivation_score": float(rel.motivation_score) if rel.motivation_score else 0,
            "decay_level": rel.decay_level,
            "last_interaction_at": str(rel.last_interaction_at) if rel.last_interaction_at else None,
        })
    return success({"total": len(items), "relations": items})


@router.get("/stats", response_model=ApiResponse)
async def get_relation_stats(
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """获取人脉统计数据"""
    # 查询当前用户的所有关系
    result = await db.execute(
        select(Relationship)
        .where(or_(Relationship.member_a == member.id, Relationship.member_b == member.id))
    )
    relationships = result.scalars().all()
    
    # 统计计算
    total = len(relationships)
    if total == 0:
        return success({
            "total": 0,
            "average_score": 0,
            "status_distribution": {
                "new": 0,
                "active": 0,
                "dormant": 0,
                "lost": 0
            },
            "decay_distribution": {
                "healthy": 0,
                "slight": 0,
                "moderate": 0,
                "severe": 0
            },
            "recently_active_count": 0,
            "average_days_since_interaction": 0
        })
    
    # 计算平均分
    total_score = sum(float(r.total_score) if r.total_score else 0 for r in relationships)
    average_score = total_score / total if total > 0 else 0
    
    # 按状态分布
    status_dist = {"new": 0, "active": 0, "dormant": 0, "lost": 0}
    for r in relationships:
        status_key = r.status if r.status in status_dist else "active"
        status_dist[status_key] += 1
    
    # 按衰减等级分布 (green=健康, yellow=轻度, orange=中度, red=重度)
    decay_dist = {"green": 0, "yellow": 0, "orange": 0, "red": 0}
    for r in relationships:
        if r.decay_level == DecayLevel.green:
            decay_dist["green"] += 1
        elif r.decay_level == DecayLevel.yellow:
            decay_dist["yellow"] += 1
        elif r.decay_level == DecayLevel.orange:
            decay_dist["orange"] += 1
        elif r.decay_level == DecayLevel.red:
            decay_dist["red"] += 1
    
    # 最近活跃数量（7天内有互动的）
    from datetime import timedelta
    seven_days_ago = datetime.now() - timedelta(days=7)  # timezone-naive for DB comparison
    recently_active = 0
    for r in relationships:
        if r.last_interaction_at:
            last_time = r.last_interaction_at
            # 统一为 timezone-naive 进行比较
            if last_time.tzinfo is not None:
                last_time = last_time.replace(tzinfo=None)
            if last_time >= seven_days_ago:
                recently_active += 1
    
    # 平均互动间隔
    now = datetime.now()  # timezone-naive
    days_since = []
    for r in relationships:
        if r.last_interaction_at:
            last_time = r.last_interaction_at
            if last_time.tzinfo is not None:
                last_time = last_time.replace(tzinfo=None)
            delta = (now - last_time).days
            days_since.append(delta)
    avg_days = sum(days_since) / len(days_since) if days_since else 0
    
    return success({
        "total": total,
        "average_score": round(average_score, 2),
        "status_distribution": status_dist,
        "decay_distribution": decay_dist,
        "recently_active_count": recently_active,
        "average_days_since_interaction": round(avg_days, 1)
    })


def _get_other_member(rel: Relationship, current_member_id: str) -> Optional[Member]:
    """从关系中获取对方的Member对象"""
    if rel.member_a == current_member_id:
        return rel.member_b_rel
    elif rel.member_b == current_member_id:
        return rel.member_a_rel
    return None


async def _check_action_power(member: Member, required: int) -> None:
    """检查行动力是否足够"""
    available = member.action_power_balance - member.action_power_frozen
    if available < required:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"行动力不足，需要 {required}，当前可用 {available}",
        )


async def _deduct_action_power(
    db: AsyncSession, member: Member, amount: int
) -> int:
    """扣除行动力，返回扣除后的可用行动力"""
    member.action_power_balance -= amount
    await db.flush()
    await db.refresh(member)
    return member.action_power_balance - member.action_power_frozen


@router.post("/{relation_id}/icebreak", response_model=ApiResponse)
async def icebreak(
    relation_id: str,
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """破冰 - AI生成破冰方案"""
    repo = RelationshipRepo(db)
    rel = await repo.get_by_id(relation_id)
    if not rel:
        raise HTTPException(status_code=404, detail="关系不存在")
    await _check_action_power(member, 8)
    other = _get_other_member(rel, member.id)
    result = await repo.icebreak(rel, member, other)
    await _deduct_action_power(db, member, 8)
    game_service.award_action(member.id, "ICEBREAK", 8)
    return success(result)


@router.post("/{relation_id}/interaction", response_model=ApiResponse)
async def record_interaction(
    relation_id: str,
    req: InteractionRequest,
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """记录互动"""
    repo = RelationshipRepo(db)
    rel = await repo.get_by_id(relation_id)
    if not rel:
        raise HTTPException(status_code=404, detail="关系不存在")
    result = await repo.record_interaction(rel, member, req)
    return success(result)


@router.post("/{relation_id}/feedback", response_model=ApiResponse)
async def provide_feedback(
    relation_id: str,
    req: FeedbackRequest,
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """反馈评价"""
    repo = RelationshipRepo(db)
    rel = await repo.get_by_id(relation_id)
    if not rel:
        raise HTTPException(status_code=404, detail="关系不存在")
    result = await repo.provide_feedback(rel, member, req)
    return success(result)


@router.get("/decay-alerts", response_model=ApiResponse)
async def decay_alerts(
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """获取关系衰减预警"""
    repo = RelationshipRepo(db)
    alerts = await repo.get_decay_alerts(member.id)
    alert_items = []
    for rel in alerts:
        other_id = rel.member_b if rel.member_a == member.id else rel.member_a
        alert_items.append({
            "id": rel.id,
            "other_member_id": other_id,
            "status": rel.status,
            "total_score": float(rel.total_score) if rel.total_score else 0,
            "decay_level": rel.decay_level,
            "last_interaction_at": str(rel.last_interaction_at) if rel.last_interaction_at else None,
        })
    return success({"total": len(alert_items), "alerts": alert_items})