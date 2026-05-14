"""
商脉系统 — 徽章体系

实现技术规格 6.3 的完整徽章体系：
  - 基础徽章 (common): 完成入门动作即获得
  - 产业链徽章 (uncommon): 深度使用产业链工具获得
  - 稀有徽章 (rare): 需要持续投入或特殊成就
  - 限定徽章 (epic): 赛季/活动/时间限定，不可重复获取

徽章永久保留，不随赛季重置。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# ===== 徽章稀有度 =====

class BadgeRarity(str, Enum):
    """徽章稀有度"""
    COMMON = "common"          # 基础徽章
    UNCOMMON = "uncommon"      # 产业链徽章
    RARE = "rare"              # 稀有徽章
    EPIC = "epic"              # 限定徽章


# ===== 徽章定义 =====

@dataclass(frozen=True)
class BadgeDef:
    """徽章定义"""
    badge_id: str                   # 唯一标识
    name: str                       # 徽章名称
    description: str                # 徽章描述
    rarity: BadgeRarity             # 稀有度
    category: str                   # 分类: basic / chain / rare / limited
    hidden: bool = False            # 是否隐藏（未达成时不显示获取条件）
    bonus_points: int = 0           # 领取时额外奖励积分
    bonus_exp: int = 0              # 领取时额外奖励经验
    seasonal: bool = False          # 是否赛季限定


BADGE_DEFINITIONS: dict[str, BadgeDef] = {
    # ---- 基础徽章 (common) ----
    "first_step": BadgeDef(
        badge_id="first_step",
        name="第一步",
        description="完善个人资料",
        rarity=BadgeRarity.COMMON,
        category="basic",
        bonus_points=20,
        bonus_exp=20,
    ),
    "role_master": BadgeDef(
        badge_id="role_master",
        name="角色大师",
        description="设置十维角色标识",
        rarity=BadgeRarity.COMMON,
        category="basic",
        bonus_points=30,
        bonus_exp=30,
    ),
    "first_match": BadgeDef(
        badge_id="first_match",
        name="初次匹配",
        description="触发首次智能匹配",
        rarity=BadgeRarity.COMMON,
        category="basic",
        bonus_points=15,
        bonus_exp=20,
    ),
    "icebreaker": BadgeDef(
        badge_id="icebreaker",
        name="破冰者",
        description="完成首次破冰对话",
        rarity=BadgeRarity.COMMON,
        category="basic",
        bonus_points=25,
        bonus_exp=30,
    ),
    "week_warrior": BadgeDef(
        badge_id="week_warrior",
        name="七日战士",
        description="连续7天签到",
        rarity=BadgeRarity.COMMON,
        category="basic",
        bonus_points=50,
        bonus_exp=30,
    ),

    # ---- 产业链徽章 (uncommon) ----
    "chain_explorer": BadgeDef(
        badge_id="chain_explorer",
        name="产业链探索者",
        description="完成3次产业链分析",
        rarity=BadgeRarity.UNCOMMON,
        category="chain",
        bonus_points=45,
        bonus_exp=60,
    ),
    "cooperator": BadgeDef(
        badge_id="cooperator",
        name="合作达人",
        description="完成首个合作项目",
        rarity=BadgeRarity.UNCOMMON,
        category="chain",
        bonus_points=100,
        bonus_exp=150,
    ),
    "strategist": BadgeDef(
        badge_id="strategist",
        name="策略家",
        description="使用七步法2次",
        rarity=BadgeRarity.UNCOMMON,
        category="chain",
        bonus_points=40,
        bonus_exp=50,
    ),
    "self_aware": BadgeDef(
        badge_id="self_aware",
        name="自知者明",
        description="完成教练诊断",
        rarity=BadgeRarity.UNCOMMON,
        category="chain",
        bonus_points=30,
        bonus_exp=40,
    ),
    "mvp_builder": BadgeDef(
        badge_id="mvp_builder",
        name="MVP构建师",
        description="创建3个MVP合作计划",
        rarity=BadgeRarity.UNCOMMON,
        category="chain",
        bonus_points=150,
        bonus_exp=200,
    ),

    # ---- 稀有徽章 (rare) ----
    "connector": BadgeDef(
        badge_id="connector",
        name="连接者",
        description="成功引荐好友加入平台",
        rarity=BadgeRarity.RARE,
        category="rare",
        bonus_points=50,
        bonus_exp=60,
    ),
    "month_champion": BadgeDef(
        badge_id="month_champion",
        name="月签到达人",
        description="连续30天签到",
        rarity=BadgeRarity.RARE,
        category="rare",
        bonus_points=200,
        bonus_exp=100,
    ),
    "ecosystem_builder": BadgeDef(
        badge_id="ecosystem_builder",
        name="生态构建者",
        description="完成10个跨行业合作项目",
        rarity=BadgeRarity.RARE,
        category="rare",
        bonus_points=300,
        bonus_exp=400,
    ),
    "network_king": BadgeDef(
        badge_id="network_king",
        name="人脉之王",
        description="建立50个验证关系",
        rarity=BadgeRarity.RARE,
        category="rare",
        bonus_points=250,
        bonus_exp=300,
    ),
    "deal_maker": BadgeDef(
        badge_id="deal_maker",
        name="交易促成者",
        description="完成5个合作项目",
        rarity=BadgeRarity.RARE,
        category="rare",
        bonus_points=200,
        bonus_exp=250,
    ),

    # ---- 限定徽章 (epic) ----
    "event_pioneer": BadgeDef(
        badge_id="event_pioneer",
        name="活动先锋",
        description="参加首次线下活动",
        rarity=BadgeRarity.EPIC,
        category="limited",
        bonus_points=100,
        bonus_exp=100,
    ),
    "season_top10": BadgeDef(
        badge_id="season_top10",
        name="赛季十强",
        description="赛季排行榜Top10",
        rarity=BadgeRarity.EPIC,
        category="limited",
        seasonal=True,
        bonus_points=500,
        bonus_exp=300,
    ),
    "early_adopter": BadgeDef(
        badge_id="early_adopter",
        name="早期布道师",
        description="平台首批100名用户",
        rarity=BadgeRarity.EPIC,
        category="limited",
        bonus_points=200,
        bonus_exp=200,
    ),
    "anniversary_1st": BadgeDef(
        badge_id="anniversary_1st",
        name="一周年纪念",
        description="平台一周年纪念徽章",
        rarity=BadgeRarity.EPIC,
        category="limited",
        bonus_points=100,
        bonus_exp=100,
    ),
}


# ===== 会员徽章记录 =====

@dataclass
class MemberBadge:
    """会员已获得的徽章记录"""
    badge_id: str
    earned_at: datetime
    claimed: bool = False          # 是否已领取奖励
    claimed_at: Optional[datetime] = None


class BadgeSystem:
    """
    徽章体系

    职责：
      - 定义并管理全量徽章
      - 检查会员是否满足徽章获取条件
      - 处理徽章领取（含额外积分/经验奖励）
      - 查询已获徽章列表
    """

    def __init__(self) -> None:
        # member_id → { badge_id → MemberBadge }
        self._earned: dict[str, dict[str, MemberBadge]] = {}
        # 外部注入的统计查询回调（用于判断条件）
        self._stat_queries: dict[str, callable] = {}

    def register_stat_query(self, stat_name: str, query_fn: callable) -> None:
        """
        注册统计查询回调，用于徽章条件判断。

        Args:
            stat_name: 统计名称，如 "checkin_streak", "match_count" 等
            query_fn: async/member_id → int 的回调函数
        """
        self._stat_queries[stat_name] = query_fn

    # ----- 公开接口 -----

    async def check_badge_eligibility(self, member_id: str, badge_id: str) -> dict:
        """
        检查会员是否达成指定徽章的获取条件。

        Args:
            member_id: 会员ID
            badge_id: 徽章ID

        Returns:
            {
                "badge_id": str,
                "eligible": bool,
                "already_earned": bool,
                "condition_detail": str  # 条件说明
            }
        """
        badge_def = BADGE_DEFINITIONS.get(badge_id)
        if badge_def is None:
            return {
                "badge_id": badge_id,
                "eligible": False,
                "already_earned": False,
                "condition_detail": "徽章不存在",
            }

        # 已获得则不再重复判断
        if self._is_already_earned(member_id, badge_id):
            return {
                "badge_id": badge_id,
                "eligible": True,
                "already_earned": True,
                "condition_detail": "已获得此徽章",
            }

        # 根据徽章ID检查条件
        eligible = await self._evaluate_condition(member_id, badge_id)

        return {
            "badge_id": badge_id,
            "eligible": eligible,
            "already_earned": False,
            "condition_detail": badge_def.description,
        }

    async def claim_badge(self, member_id: str, badge_id: str) -> dict:
        """
        领取徽章（发放奖励积分/经验）。

        Args:
            member_id: 会员ID
            badge_id: 徽章ID

        Returns:
            {
                "success": bool,
                "badge_id": str,
                "badge_name": str,
                "rarity": str,
                "bonus_points": int,
                "bonus_exp": int,
                "message": str
            }
        """
        badge_def = BADGE_DEFINITIONS.get(badge_id)
        if badge_def is None:
            return {
                "success": False,
                "badge_id": badge_id,
                "badge_name": "",
                "rarity": "",
                "bonus_points": 0,
                "bonus_exp": 0,
                "message": "徽章不存在",
            }

        # 检查是否已获得
        if self._is_already_earned(member_id, badge_id):
            existing = self._earned[member_id][badge_id]
            if existing.claimed:
                return {
                    "success": False,
                    "badge_id": badge_id,
                    "badge_name": badge_def.name,
                    "rarity": badge_def.rarity.value,
                    "bonus_points": 0,
                    "bonus_exp": 0,
                    "message": "徽章已领取，不可重复领取",
                }
            # 已达成但未领取 → 补领
            existing.claimed = True
            existing.claimed_at = datetime.now()
            return {
                "success": True,
                "badge_id": badge_id,
                "badge_name": badge_def.name,
                "rarity": badge_def.rarity.value,
                "bonus_points": badge_def.bonus_points,
                "bonus_exp": badge_def.bonus_exp,
                "message": "徽章奖励已补领",
            }

        # 检查条件
        eligible = await self._evaluate_condition(member_id, badge_id)
        if not eligible:
            return {
                "success": False,
                "badge_id": badge_id,
                "badge_name": badge_def.name,
                "rarity": badge_def.rarity.value,
                "bonus_points": 0,
                "bonus_exp": 0,
                "message": "未达成获取条件",
            }

        # 发放徽章
        self._grant_badge(member_id, badge_id)
        record = self._earned[member_id][badge_id]
        record.claimed = True
        record.claimed_at = datetime.now()

        return {
            "success": True,
            "badge_id": badge_id,
            "badge_name": badge_def.name,
            "rarity": badge_def.rarity.value,
            "bonus_points": badge_def.bonus_points,
            "bonus_exp": badge_def.bonus_exp,
            "message": "徽章领取成功",
        }

    def get_member_badges(self, member_id: str) -> list[dict]:
        """
        查询会员已获得的全部徽章。

        Args:
            member_id: 会员ID

        Returns:
            徽章列表，每项包含 badge_id, name, description, rarity, earned_at, claimed
        """
        earned = self._earned.get(member_id, {})
        result: list[dict] = []
        for badge_id, record in earned.items():
            badge_def = BADGE_DEFINITIONS.get(badge_id)
            if badge_def is None:
                continue
            result.append({
                "badge_id": badge_id,
                "name": badge_def.name,
                "description": badge_def.description,
                "rarity": badge_def.rarity.value,
                "category": badge_def.category,
                "earned_at": record.earned_at.isoformat(),
                "claimed": record.claimed,
            })
        return result

    def grant_badge_directly(self, member_id: str, badge_id: str) -> bool:
        """
        直接授予徽章（不检查条件，由外部系统调用）。
        适用于赛季结算、管理员发放等场景。

        Args:
            member_id: 会员ID
            badge_id: 徽章ID

        Returns:
            是否成功授予（重复授予返回 False）
        """
        if badge_id not in BADGE_DEFINITIONS:
            return False
        if self._is_already_earned(member_id, badge_id):
            return False
        self._grant_badge(member_id, badge_id)
        return True

    def get_all_badge_definitions(self) -> list[dict]:
        """
        获取全部徽章定义列表。

        Returns:
            徽章定义列表
        """
        result: list[dict] = []
        for badge_id, badge_def in BADGE_DEFINITIONS.items():
            result.append({
                "badge_id": badge_id,
                "name": badge_def.name,
                "description": badge_def.description,
                "rarity": badge_def.rarity.value,
                "category": badge_def.category,
                "hidden": badge_def.hidden,
                "bonus_points": badge_def.bonus_points,
                "bonus_exp": badge_def.bonus_exp,
                "seasonal": badge_def.seasonal,
            })
        return result

    # ----- 内部方法 -----

    def _is_already_earned(self, member_id: str, badge_id: str) -> bool:
        """判断会员是否已获得指定徽章"""
        return badge_id in self._earned.get(member_id, {})

    def _grant_badge(self, member_id: str, badge_id: str) -> None:
        """授予徽章（内部方法，不做条件检查）"""
        if member_id not in self._earned:
            self._earned[member_id] = {}
        self._earned[member_id][badge_id] = MemberBadge(
            badge_id=badge_id,
            earned_at=datetime.now(),
        )

    async def _evaluate_condition(self, member_id: str, badge_id: str) -> bool:
        """
        评估会员是否满足徽章获取条件。

        通过注册的统计查询回调获取实际数据，
        与徽章的阈值条件进行比较。

        Args:
            member_id: 会员ID
            badge_id: 徽章ID

        Returns:
            是否满足条件
        """
        # 徽章条件映射：badge_id → (stat_name, threshold)
        BADGE_CONDITIONS: dict[str, tuple[str, int]] = {
            "first_step":       ("profile_complete", 1),
            "role_master":      ("roles_set", 1),
            "first_match":      ("match_count", 1),
            "icebreaker":       ("icebreak_count", 1),
            "week_warrior":     ("checkin_streak", 7),
            "chain_explorer":   ("chain_analysis_count", 3),
            "cooperator":       ("completed_projects", 1),
            "strategist":       ("seven_step_count", 2),
            "self_aware":       ("coach_diagnosis_count", 1),
            "mvp_builder":      ("mvp_created", 3),
            "connector":        ("referral_count", 1),
            "month_champion":   ("checkin_streak", 30),
            "ecosystem_builder":("cross_industry_projects", 10),
            "network_king":     ("verified_relations", 50),
            "deal_maker":       ("completed_projects", 5),
            "event_pioneer":    ("event_participation", 1),
            "season_top10":     ("season_rank", 10),     # rank <= 10
            "early_adopter":    ("early_adopter_flag", 1),
            "anniversary_1st":  ("anniversary_flag", 1),
        }

        condition = BADGE_CONDITIONS.get(badge_id)
        if condition is None:
            return False

        stat_name, threshold = condition
        query_fn = self._stat_queries.get(stat_name)

        if query_fn is None:
            # 没有注册查询回调时，默认不满足
            return False

        try:
            actual_value = await query_fn(member_id)
            # season_top10 是排名，需要 <= threshold
            if badge_id == "season_top10":
                return 1 <= actual_value <= threshold
            return actual_value >= threshold
        except Exception:
            return False
