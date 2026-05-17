"""引荐分成体系 API"""
from uuid import uuid4
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.member import Member
from app.models.referral import ReferralRecord
from app.dependencies.auth import get_current_member
from app.schemas.common import ApiResponse, success, fail
from app.services.game import game_engine

router = APIRouter()




@router.get("/info", response_model=ApiResponse)
async def get_referral_info(
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """引荐综合信息（前端统一入口）"""
    code = str(member.id)[:8].upper()
    total_referrals = (await db.execute(
        select(func.count()).select_from(ReferralRecord)
        .where(ReferralRecord.referrer_id == member.id)
    )).scalar() or 0
    total_earned = (await db.execute(
        select(func.coalesce(func.sum(ReferralRecord.total_earned), 0))
        .where(ReferralRecord.referrer_id == member.id)
    )).scalar() or 0
    return success(data={
        "referral_code": code,
        "referral_link": f"http://114.132.65.96/register?ref={code}",
        "total_referrals": total_referrals,
        "total_earned": int(total_earned),
        "rate": 0.10,
        "max_rate": 0.30,
        "rules": {
            "min_withdrawal": 100,
            "rate_tier1": 0.10,
            "rate_tier2": 0.20,
            "rate_tier3": 0.30,
        },
    })

@router.get("/my-code", response_model=ApiResponse)
async def get_my_referral_code(
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """获取我的引荐码（用member_id前8位作为引荐码）"""
    code = str(member.id)[:8].upper()
    # 统计引荐数据
    total_referrals = (await db.execute(
        select(func.count()).select_from(ReferralRecord)
        .where(ReferralRecord.referrer_id == member.id)
    )).scalar() or 0

    total_earned = (await db.execute(
        select(func.coalesce(func.sum(ReferralRecord.total_earned), 0))
        .where(ReferralRecord.referrer_id == member.id)
    )).scalar() or 0

    return success(data={
        "referral_code": code,
        "referral_link": f"http://114.132.65.96/register?ref={code}",
        "total_referrals": total_referrals,
        "total_earned": int(total_earned),
        "rate": 0.10,
        "max_rate": 0.30,
    })


@router.get("/records", response_model=ApiResponse)
async def list_referral_records(
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """我的引荐记录"""
    records = (await db.execute(
        select(ReferralRecord)
        .where(ReferralRecord.referrer_id == member.id)
        .order_by(ReferralRecord.created_at.desc())
    )).scalars().all()

    items = []
    for r in records:
        referee = await db.get(Member, r.referee_id)
        items.append({
            "id": str(r.id),
            "referee_name": referee.name if referee else "未知",
            "rate": float(r.rate),
            "total_earned": r.total_earned or 0,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return success(data={"records": items, "total": len(items)})


@router.post("/apply", response_model=ApiResponse)
async def apply_referral(
    code: str,
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """使用引荐码（新用户注册后调用）"""
    # 根据引荐码找到推荐人
    all_members = (await db.execute(select(Member))).scalars().all()
    referrer = None
    for m in all_members:
        if str(m.id)[:8].upper() == code.upper():
            referrer = m
            break

    if not referrer:
        return fail(message="引荐码无效")

    if referrer.id == member.id:
        return fail(message="不能使用自己的引荐码")

    # 检查是否已使用
    existing = (await db.execute(
        select(ReferralRecord)
        .where(ReferralRecord.referee_id == member.id)
    )).scalar_one_or_none()
    if existing:
        return fail(message="您已使用过引荐码")

    # 创建引荐记录
    rate = 0.10
    if referrer.referrer_rate:
        rate = float(referrer.referrer_rate)

    record = ReferralRecord(
        id=str(uuid4()),
        referrer_id=referrer.id,
        referee_id=member.id,
        rate=rate,
        total_earned=0,
        created_at=datetime.now(timezone.utc),
    )
    db.add(record)

    # 双方奖励行动力
    member.action_power_balance += 20
    referrer.action_power_balance += 20

    await db.commit()

    # 触发游戏积分：引荐好友
    game_result_referee = await game_engine.on_action(str(member.id), "REFERRAL")
    game_result_referrer = await game_engine.on_action(str(referrer.id), "REFERRAL")

    return success(data={
        "referrer_name": referrer.name,
        "bonus": 20,
        "balance": member.action_power_balance,
        "game_reward": {
            "referee_points": game_result_referee.get("points_earned", 0),
            "referee_exp": game_result_referee.get("exp_earned", 0),
            "referrer_points": game_result_referrer.get("points_earned", 0),
            "referrer_exp": game_result_referrer.get("exp_earned", 0),
            "referee_badge": game_result_referee.get("badge_unlocked"),
            "message": f"引荐好友 +{game_result_referee.get('points_earned', 0)}积分",
        }
    })


@router.get("/rules", response_model=ApiResponse)
async def get_referral_rules():
    """引荐规则说明"""
    return success(data={
        "base_rate": 0.10,
        "max_rate": 0.30,
        "referrer_bonus": 20,
        "referee_bonus": 20,
        "rules": [
            "每成功邀请一位好友注册，双方各获得20行动力",
            "邀请人可享受被邀请人消费行动力的10%分成",
            "邀请人数越多，分成比例越高，最高30%",
            "邀请3人以上：分成比例提升至15%",
            "邀请10人以上：分成比例提升至20%",
            "邀请30人以上：分成比例提升至30%",
        ],
    })
