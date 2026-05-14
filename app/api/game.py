"""商脉系统 · 游戏化模块（接入真实数据库）"""
from datetime import date, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, Body
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_member
from app.database import get_db
from app.models.member import Member
from app.models.game import GameProfile, GameTaskProgress, GameLeaderboard
from pydantic import BaseModel
from app.services.game import game_engine


class ActionRequest(BaseModel):
    """行为触发请求"""
    action: str
from app.schemas.common import ApiResponse, success, fail

router = APIRouter()


async def _get_or_create_profile(member_id: str, db: AsyncSession) -> GameProfile:
    """获取或创建游戏档案"""
    result = await db.execute(
        select(GameProfile).where(GameProfile.member_id == member_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        profile = GameProfile(member_id=member_id, level=1, exp=0, total_points=0)
        db.add(profile)
        await db.flush()
    return profile


@router.get("/profile", response_model=ApiResponse)
async def get_game_profile(
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """游戏档案"""
    profile = await _get_or_create_profile(member.id, db)
    await db.commit()

    return success(data={
        "member_id": member.id,
        "level": profile.level,
        "exp": profile.exp,
        "total_points": profile.total_points or 0,
        "badges": profile.badges or [],
        "daily_checkin_streak": profile.daily_checkin_streak or 0,
        "last_checkin": profile.last_checkin.isoformat() if profile.last_checkin else None,
    })


@router.post("/checkin", response_model=ApiResponse)
async def daily_checkin(
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """每日签到"""
    profile = await _get_or_create_profile(member.id, db)

    today = date.today()
    if profile.last_checkin == today:
        return fail(code=400, message="今日已签到")

    # 连续签到计算
    streak = profile.daily_checkin_streak or 0
    if profile.last_checkin:
        delta = (today - profile.last_checkin).days
        if delta == 1:
            streak += 1
        elif delta > 1:
            streak = 1
    else:
        streak = 1

    # 积分奖励
    base_points = 10
    streak_bonus = min(streak * 2, 30)
    total_points = base_points + streak_bonus

    # 更新档案
    profile.last_checkin = today
    profile.daily_checkin_streak = streak
    profile.total_points = (profile.total_points or 0) + total_points
    profile.exp = (profile.exp or 0) + total_points

    # 等级检查
    level = profile.level
    exp = profile.exp
    level_thresholds = [0, 100, 500, 1500, 4000, 10000]
    new_level = 1
    for i, threshold in enumerate(level_thresholds):
        if exp >= threshold:
            new_level = i + 1
    new_level = min(new_level, 6)
    level_up = new_level > level
    profile.level = new_level

    await db.commit()

    return success(data={
        "checked_in": True,
        "points_earned": total_points,
        "streak": streak,
        "streak_bonus": streak_bonus,
        "total_points": profile.total_points,
        "level": profile.level,
        "level_up": level_up,
    })


@router.get("/tasks", response_model=ApiResponse)
async def get_tasks(task_type: str = None):
    """任务列表"""
    all_tasks = game_engine.point_rules.get_all_rules()
    if task_type:
        all_tasks = [t for t in all_tasks if task_type.lower() in t.action.lower()]
    return ApiResponse(data={"tasks": all_tasks})


@router.get("/leaderboard", response_model=ApiResponse)
async def get_leaderboard(
    category: str = "POINTS",
    season_id: str = None,
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """排行榜（真实数据）"""
    # 先尝试从 GameLeaderboard 表读取
    stmt = (
        select(GameLeaderboard, Member.name)
        .join(Member, GameLeaderboard.member_id == Member.id)
    )
    if season_id:
        stmt = stmt.where(GameLeaderboard.season_id == season_id)
    stmt = stmt.order_by(GameLeaderboard.rank).limit(20)
    result = await db.execute(stmt)
    rows = result.all()

    if rows:
        rankings = [{
            "rank": r.rank,
            "member_id": r.member_id,
            "name": name or "未知",
            "score": r.score,
        } for r, name in rows]
    else:
        # 降级：从 GameProfile 读取
        stmt2 = (
            select(GameProfile, Member.name)
            .join(Member, GameProfile.member_id == Member.id)
            .order_by(GameProfile.total_points.desc())
            .limit(20)
        )
        result2 = await db.execute(stmt2)
        rows2 = result2.all()
        rankings = [{
            "rank": i,
            "member_id": p.member_id,
            "name": name or "未知",
            "score": p.total_points or 0,
            "level": p.level,
        } for i, (p, name) in enumerate(rows2, 1)]

    if not rankings:
        profile = await _get_or_create_profile(member.id, db)
        rankings = [{"rank": 1, "member_id": member.id, "name": member.name, "score": profile.total_points or 0, "level": profile.level}]

    season_info = game_engine.season_system.get_current_season()

    return success(data={
        "season_id": season_id or season_info.season_id,
        "category": category,
        "rankings": rankings,
    })


@router.get("/badges", response_model=ApiResponse)
async def get_badges():
    """徽章目录"""
    return ApiResponse(data=game_engine.badge_system.get_all_badge_definitions())


@router.post("/badges/{badge_id}/claim", response_model=ApiResponse)
async def claim_badge(
    badge_id: str,
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """领取徽章"""
    result = await game_engine.on_badge_claim(member.id, badge_id)
    if not result.get("success"):
        return fail(code=400, message=result.get("reason", "未达成条件"))

    # 更新 profile badges
    profile = await _get_or_create_profile(member.id, db)
    current_badges = profile.badges or []
    if badge_id not in current_badges:
        current_badges.append(badge_id)
        profile.badges = current_badges
    await db.commit()

    return success(data=result)


@router.get("/season", response_model=ApiResponse)
async def get_season_info():
    """赛季信息"""
    info = game_engine.season_system.get_current_season()
    season_dict = {
        "season_id": info.season_id,
        "year": info.year,
        "quarter": info.quarter,
        "start_date": str(info.start_date),
        "end_date": str(info.end_date),
        "sprint_start": str(info.sprint_start),
        "is_current": info.is_current,
        "rewards": game_engine.season_system.get_season_rewards(),
        "reset_info": {"type": "manual", "description": "赛季结束需手动重置"},
    }
    return ApiResponse(data=season_dict)


@router.post("/action", response_model=ApiResponse)
async def trigger_action(
    body: ActionRequest,
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """
    通用行为触发接口 - 会员贡献积分统一入口
    
    action 可选值：
      ATTEND_EVENT      - 参加活动
      CREATE_ACTIVITY   - 创建活动
      REFERRAL          - 引荐好友成功
      PROFILE_COMPLETE  - 完善资料
      SET_ROLES         - 设置十维角色
      TRIGGER_MATCH     - 触发匹配
      VIEW_MATCH        - 查看匹配
      ICEBREAK          - 破冰对话
      RECORD_INTERACTION- 记录互动
      REVIEW_FEEDBACK   - 复盘反馈
      COACH_DIAGNOSIS   - 教练诊断
      CREATE_COOPERATION- 创建合作
      COMPLETE_COOP_TASK- 完成合作任务
      MECE_ANALYSIS     - MECE分析
      SEVEN_STEP        - 七步法
      CHAIN_ANALYSIS    - 产业链分析
      COACH_DIALOG      - 教练对话
    
    返回：积分获得数量、经验、等级变化、徽章解锁情况
    """
    result = await game_engine.on_action(str(member.id), body.action)
    
    # 同步更新数据库
    if result["success"]:
        # 更新会员经验值
        db_member = await db.get(Member, member.id)
        if db_member:
            # 获取当前等级对应的经验值
            level_info = game_engine.level_system.get_level_info(db_member.level or 1)
            exp_for_level = level_info.exp_required if level_info else 0
            # 累加经验
            db_member.exp_points = (db_member.exp_points or 0) + result["exp_earned"]
            
            # 等级变化时更新会员表
            if result["level_up"]:
                db_member.level = result["new_level"]
            
            await db.commit()
    
    return success(data={
        "action": body.action,
        "action_name": _get_action_name(body.action),
        "success": result["success"],
        "points_earned": result.get("points_earned", 0),
        "exp_earned": result.get("exp_earned", 0),
        "level_up": result.get("level_up", False),
        "old_level": result.get("old_level", 0),
        "new_level": result.get("new_level", 0),
        "badge_unlocked": result.get("badge_unlocked"),
        "season_points_earned": result.get("season_points_earned", 0),
        "sprint_active": result.get("sprint_active", False),
        "limit_remaining": result.get("limit_remaining", -1),
        "message": result.get("message", ""),
    })



@router.get("/levels", response_model=ApiResponse)
async def get_level_rules():
    """获取等级规则表（公开）"""
    from app.services.game.level_system import LEVEL_TABLE, LevelInfo
    levels = []
    for lv in range(1, 7):
        info = LEVEL_TABLE.get(lv)
        if not info:
            continue
        levels.append({
            "level": info.level,
            "name": info.name,
            "exp_required": info.exp_required,
            "exp_next": info.exp_next,
            "monthly_free_ap": info.monthly_free_ap,
            "reward_multiplier": info.reward_multiplier,
        })
    return success(data={"levels": levels})

def _get_action_name(action: str) -> str:
    """行为标识转中文名"""
    names = {
        "ATTEND_EVENT": "参加活动",
        "CREATE_ACTIVITY": "创建活动",
        "REFERRAL": "引荐好友",
        "PROFILE_COMPLETE": "完善资料",
        "SET_ROLES": "设置十维角色",
        "TRIGGER_MATCH": "触发匹配",
        "VIEW_MATCH": "查看匹配",
        "ICEBREAK": "破冰对话",
        "RECORD_INTERACTION": "记录互动",
        "REVIEW_FEEDBACK": "复盘反馈",
        "COACH_DIAGNOSIS": "教练诊断",
        "CREATE_COOPERATION": "创建合作",
        "COMPLETE_COOP_TASK": "完成合作任务",
        "COMPLETE_COOP_PROJECT": "完成合作项目",
        "MECE_ANALYSIS": "MECE分析",
        "SEVEN_STEP": "七步法",
        "CHAIN_ANALYSIS": "产业链分析",
        "COACH_DIALOG": "教练对话",
        "DAILY_CHECKIN": "每日签到",
    }
    return names.get(action, action)

