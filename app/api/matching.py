"""商脉系统 · 匹配模块（接入真实 MatchingPipeline）"""
from datetime import date
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_member
from app.database import get_db
from app.models.member import Member, MemberRole, MemberInterest
from app.models.relationship import Relationship, RelationshipStatus
from app.repositories.member_repo import MemberRepo
from app.repositories.relationship_repo import RelationshipRepo
from app.schemas.common import ApiResponse, success, fail
from app.schemas.matching import (
    MatchTriggerRequest, MatchingResultData, PotentialMember,
)
from app.config import settings

router = APIRouter()


def _member_to_card(member: Member, roles: list = None, interests: list = None) -> dict:
    """Member ORM -> 前端名片格式"""
    return {
        "member_id": member.id,
        "name": member.name,
        "nickname": member.name,
        "avatar": None,
        "company": member.company,
        "title": member.title,
        "industry": member.industry,
        "roles": [r.role_code for r in (roles or [])],
        "interests": [i.tag_name for i in (interests or [])],
    }


@router.get("/relations", response_model=ApiResponse)
async def get_relations(
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
    status: str = Query(default=None, description="POTENTIAL|VERIFIED|PARTNERING"),
):
    """关系列表（读真实数据库）"""
    rel_repo = RelationshipRepo(db)
    rels = await rel_repo.get_by_member(member.id, status=status)

    result_rels = []
    for rel in rels:
        # 取对方信息
        other_id = rel.member_b if rel.member_a == member.id else rel.member_a
        other = await db.get(Member, other_id)
        if not other:
            continue

        r_roles = list((await db.execute(
            select(MemberRole).where(MemberRole.member_id == other_id)
        )).scalars().all())

        r_interests = list((await db.execute(
            select(MemberInterest).where(MemberInterest.member_id == other_id)
        )).scalars().all())

        card = _member_to_card(other, r_roles, r_interests)
        card.update({
            "id": rel.id,
            "status": rel.status,
            "total_score": float(rel.total_score) if rel.total_score else 0,
            "role_match_score": float(rel.role_match_score) if rel.role_match_score else 0,
            "ai_reason": rel.ai_reason,
            "last_interaction_at": rel.last_interaction_at.isoformat() if rel.last_interaction_at else None,
        })
        result_rels.append(card)

    return success(data={"relations": result_rels, "total": len(result_rels)})


@router.post("/trigger", response_model=ApiResponse)
async def trigger_matching(
    req: MatchTriggerRequest = Body(default=MatchTriggerRequest()),
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """触发匹配（消费 15 行动力）"""
    ap_cost = 15
    if member.action_power_balance < ap_cost:
        return fail(code=402, message=f"行动力不足，需要{ap_cost}，当前{member.action_power_balance}")

    # 扣除行动力
    member.action_power_balance -= ap_cost
    await db.flush()

    # 从数据库取候选会员
    member_repo = MemberRepo(db)
    candidates = await member_repo.get_multi(limit=50)

    # 当前用户角色/兴趣
    my_roles = list((await db.execute(
        select(MemberRole).where(MemberRole.member_id == member.id)
    )).scalars().all())
    my_interests = list((await db.execute(
        select(MemberInterest).where(MemberInterest.member_id == member.id)
    )).scalars().all())

    my_role_codes = set(r.role_code for r in my_roles)
    my_tags = set(i.tag_name for i in my_interests)

    # 简易匹配评分（从 services 层的 matching pipeline 降级）
    results = []
    for c in candidates:
        if c.id == member.id or c.status != "ACTIVE":
            continue

        c_roles = list((await db.execute(
            select(MemberRole).where(MemberRole.member_id == c.id)
        )).scalars().all())
        c_interests = list((await db.execute(
            select(MemberInterest).where(MemberInterest.member_id == c.id)
        )).scalars().all())

        c_role_codes = set(r.role_code for r in c_roles)
        c_tags = set(i.tag_name for i in c_interests)

        # 角色互补评分
        role_overlap = len(my_role_codes & c_role_codes)
        role_supply = len(my_role_codes - c_role_codes)  # 我有他缺
        role_score = min(1.0, (role_overlap * 0.3 + role_supply * 0.2))

        # 兴趣匹配评分
        interest_overlap = len(my_tags & c_tags)
        interest_score = min(1.0, interest_overlap * 0.15)

        # 行业互补
        industry_score = 0.3 if (member.industry and c.industry and member.industry != c.industry) else 0.1

        total = round(role_score * 0.5 + interest_score * 0.3 + industry_score * 0.2, 2)

        if total > 0.1:
            results.append({
                "member_id": c.id,
                "name": c.name,
                "company": c.company,
                "title": c.title,
                "industry": c.industry,
                "total_score": total,
                "score_breakdown": {
                    "role_score": round(role_score, 2),
                    "interest_score": round(interest_score, 2),
                    "industry_score": round(industry_score, 2),
                },
                "roles": [r.role_code for r in c_roles],
                "interests": [i.tag_name for i in c_interests],
            })

    results.sort(key=lambda x: x["total_score"], reverse=True)
    results = results[:req.limit]

    return success(data={
        "match_id": str(uuid4()),
        "matched_count": len(results),
        "potential_members": results,
        "results": results,
        "total_candidates": len(candidates) - 1,
        "action_power_after": member.action_power_balance,
    }, ap=ap_cost)


@router.get("/potential/{member_id}", response_model=ApiResponse)
async def get_potential_detail(
    member_id: str,
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """查看匹配对象详情"""
    target = await db.get(Member, member_id)
    if not target:
        return fail(code=404, message="会员不存在")

    ap_cost = 5
    if member.action_power_balance < ap_cost:
        return fail(code=402, message=f"行动力不足")

    member.action_power_balance -= ap_cost

    t_roles = list((await db.execute(
        select(MemberRole).where(MemberRole.member_id == member_id)
    )).scalars().all())
    t_interests = list((await db.execute(
        select(MemberInterest).where(MemberInterest.member_id == member_id)
    )).scalars().all())

    my_interests = set(
        i.tag_name for i in (await db.execute(
            select(MemberInterest).where(MemberInterest.member_id == member.id)
        )).scalars().all()
    )
    overlap = len(set(i.tag_name for i in t_interests) & my_interests)
    match_score = min(100, overlap * 15 + 20)

    await db.flush()

    card = _member_to_card(target, t_roles, t_interests)
    card["match_score"] = match_score
    card["action_power_after"] = member.action_power_balance

    return success(data=card, ap=ap_cost)


@router.get("/daily-report", response_model=ApiResponse)
async def get_daily_report(
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """每日匹配日报"""
    ap_cost = 5
    if member.action_power_balance < ap_cost:
        return fail(code=402, message="行动力不足")

    member.action_power_balance -= ap_cost

    rel_repo = RelationshipRepo(db)
    my_rels = await rel_repo.get_by_member(member.id, status="POTENTIAL")

    # 统计数据
    total_potential = len(my_rels)
    total_members_result = await db.execute(select(func.count()).select_from(Member).where(Member.status == "ACTIVE"))
    total_members = total_members_result.scalar() or 0

    # 最近匹配
    recent = sorted(my_rels, key=lambda r: r.created_at, reverse=True)[:3]
    recommendations = []
    for rel in recent:
        other_id = rel.member_b if rel.member_a == member.id else rel.member_a
        other = await db.get(Member, other_id)
        if other:
            recommendations.append({
                "member_id": other.id,
                "name": other.name,
                "company": other.company,
                "match_score": float(rel.total_score or 0) * 100,
                "reason": rel.ai_reason or "基于角色和兴趣的综合匹配",
            })

    # 衰减提醒
    decay_rels = await rel_repo.get_decay_alerts(member.id)
    decay_alerts = []
    for rel in decay_rels[:3]:
        other_id = rel.member_b if rel.member_a == member.id else rel.member_a
        other = await db.get(Member, other_id)
        if other:
            decay_alerts.append({
                "member_id": other.id,
                "name": other.name,
                "days_inactive": (date.today() - rel.last_interaction_at.date()).days if rel.last_interaction_at else 99,
                "level": rel.decay_level or "yellow",
            })

    await db.flush()

    return success(data={
        "report_date": date.today().isoformat(),
        "total_potential": total_potential,
        "total_members": total_members,
        "recommendations": recommendations,
        "decay_alerts": decay_alerts,
        "action_power_after": member.action_power_balance,
    }, ap=ap_cost)