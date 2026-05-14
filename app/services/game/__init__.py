"""
商脉系统 — 游戏化引擎统一入口

GameEngine 整合所有子模块：
  - LevelSystem:  等级经验系统
  - BadgeSystem:  徽章体系
  - SeasonSystem: 赛季机制
  - PointRulesEngine: 积分获取规则

对外暴露统一的 GameEngine 类，提供：
  - on_action():          行为触发积分
  - on_checkin():         签到处理
  - on_badge_claim():     徽章领取
  - get_full_profile():   完整游戏化档案
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from app.services.game.level_system import LevelSystem, LevelInfo, LEVEL_TABLE
from app.services.game.badge_system import BadgeSystem, BadgeRarity, BADGE_DEFINITIONS
from app.services.game.season_system import SeasonSystem, SeasonInfo
from app.services.game.point_rules import PointRulesEngine, POINT_RULES


class GameEngine:
    """
    游戏化引擎

    统一整合等级、徽章、赛季、积分四个子系统，
    对外提供简洁的行为驱动接口。
    """

    def __init__(self) -> None:
        """初始化游戏化引擎，创建所有子系统实例"""
        self.level_system: LevelSystem = LevelSystem()
        self.badge_system: BadgeSystem = BadgeSystem()
        self.season_system: SeasonSystem = SeasonSystem()
        self.point_rules: PointRulesEngine = PointRulesEngine()

    # ============================================================
    # 行为触发接口
    # ============================================================

    async def on_action(self, member_id: str, action: str,
                        context: Optional[dict] = None) -> dict:
        """
        行为触发积分入口。

        统一处理流程：
          1. 检查频率限制
          2. 计算积分/经验（含加成）
          3. 增加经验（自动检查升级）
          4. 增加赛季积分
          5. 检查关联徽章
          6. 记录行为次数

        Args:
            member_id: 会员ID
            action: 行为标识（对应 POINT_RULES 的 key）
            context: 附加上下文（预留扩展）

        Returns:
            {
                "success": bool,
                "action": str,
                "points_earned": int,
                "exp_earned": int,
                "level_up": bool,
                "old_level": int,
                "new_level": int,
                "badge_unlocked": Optional[str],
                "season_points_earned": int,
                "sprint_active": bool,
                "limit_remaining": int
            }
        """
        # 1. 检查频率限制
        limit_check = self.point_rules.check_limit(member_id, action)
        if not limit_check["allowed"]:
            return {
                "success": False,
                "action": action,
                "points_earned": 0,
                "exp_earned": 0,
                "level_up": False,
                "old_level": self.level_system.get_level(member_id),
                "new_level": self.level_system.get_level(member_id),
                "badge_unlocked": None,
                "season_points_earned": 0,
                "sprint_active": False,
                "limit_remaining": 0,
                "message": f"已达{limit_check['limit_type']}上限 ({limit_check['limit_value']}次)",
            }

        # 2. 计算加成
        level_multiplier = self.level_system.get_reward_multiplier(member_id)
        sprint_multiplier = self.season_system.get_sprint_multiplier()

        # 3. 计算奖励
        reward = self.point_rules.calculate_reward(
            member_id, action, level_multiplier, sprint_multiplier
        )

        # 4. 增加经验 → 自动检查升级
        old_level = self.level_system.get_level(member_id)
        level_result = self.level_system.add_exp(member_id, reward["final_exp"])

        # 5. 增加赛季积分
        season_points = self.season_system.add_season_points(
            member_id, reward["final_points"]
        )

        # 6. 记录行为次数
        self.point_rules.record_action(member_id, action)

        # 7. 检查关联徽章
        badge_unlocked: Optional[str] = None
        badge_id = reward.get("badge_id")
        if badge_id:
            eligibility = await self.badge_system.check_badge_eligibility(member_id, badge_id)
            if eligibility["eligible"] and not eligibility["already_earned"]:
                self.badge_system.grant_badge_directly(member_id, badge_id)
                badge_unlocked = badge_id

        return {
            "success": True,
            "action": action,
            "points_earned": reward["final_points"],
            "exp_earned": reward["final_exp"],
            "level_up": level_result["level_up"],
            "old_level": old_level,
            "new_level": level_result["new_level"],
            "badge_unlocked": badge_unlocked,
            "season_points_earned": season_points,
            "sprint_active": sprint_multiplier > 1.0,
            "limit_remaining": limit_check["remaining"] - 1,
        }

    async def on_checkin(self, member_id: str) -> dict:
        """
        每日签到处理。

        签到特殊逻辑：
          1. 基础签到积分 (10/10)
          2. 连续7天额外奖励 (50/30) + week_warrior徽章
          3. 连续30天额外奖励 (200/100) + month_champion徽章
          4. 自动更新签到连击数

        Args:
            member_id: 会员ID

        Returns:
            {
                "success": bool,
                "streak": int,
                "base_points": int,
                "base_exp": int,
                "streak_bonus_points": int,
                "streak_bonus_exp": int,
                "total_points": int,
                "total_exp": int,
                "new_badges": list[str],
                "level_up": bool,
                "new_level": int
            }
        """
        # 先用 on_action 处理基础签到
        base_result = await self.on_action(member_id, "DAILY_CHECKIN")
        if not base_result["success"]:
            return {
                "success": False,
                "streak": 0,
                "base_points": 0,
                "base_exp": 0,
                "streak_bonus_points": 0,
                "streak_bonus_exp": 0,
                "total_points": 0,
                "total_exp": 0,
                "new_badges": [],
                "level_up": False,
                "new_level": self.level_system.get_level(member_id),
                "message": "今日已签到",
            }

        # 获取当前连击数（由外部签到系统维护或从 badge_system 统计查询获取）
        streak = await self._get_checkin_streak(member_id)

        new_badges: list[str] = []
        streak_bonus_points = 0
        streak_bonus_exp = 0

        # 连续7天额外奖励
        if streak >= 7 and streak % 7 == 0:
            # 每7天整触发一次额外奖励（7、14、21、28...）
            streak_result_7 = await self.on_action(member_id, "STREAK_7")
            if streak_result_7["success"]:
                streak_bonus_points += streak_result_7["points_earned"]
                streak_bonus_exp += streak_result_7["exp_earned"]
                if streak_result_7.get("badge_unlocked"):
                    new_badges.append(streak_result_7["badge_unlocked"])

        # 连续30天额外奖励
        if streak >= 30 and streak % 30 == 0:
            streak_result_30 = await self.on_action(member_id, "STREAK_30")
            if streak_result_30["success"]:
                streak_bonus_points += streak_result_30["points_earned"]
                streak_bonus_exp += streak_result_30["exp_earned"]
                if streak_result_30.get("badge_unlocked"):
                    new_badges.append(streak_result_30["badge_unlocked"])

        # 汇总签到基础奖励
        base_points = base_result["points_earned"]
        base_exp = base_result["exp_earned"]
        total_points = base_points + streak_bonus_points
        total_exp = base_exp + streak_bonus_exp

        # 合并徽章
        if base_result.get("badge_unlocked"):
            new_badges.insert(0, base_result["badge_unlocked"])

        return {
            "success": True,
            "streak": streak,
            "base_points": base_points,
            "base_exp": base_exp,
            "streak_bonus_points": streak_bonus_points,
            "streak_bonus_exp": streak_bonus_exp,
            "total_points": total_points,
            "total_exp": total_exp,
            "new_badges": new_badges,
            "level_up": base_result["level_up"],
            "new_level": base_result["new_level"],
        }

    async def on_badge_claim(self, member_id: str, badge_id: str) -> dict:
        """
        徽章领取处理。

        领取徽章时发放额外积分/经验奖励。

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
                "level_up": bool,
                "new_level": int,
                "message": str
            }
        """
        claim_result = await self.badge_system.claim_badge(member_id, badge_id)

        if not claim_result["success"]:
            return {
                "success": False,
                "badge_id": badge_id,
                "badge_name": claim_result.get("badge_name", ""),
                "rarity": claim_result.get("rarity", ""),
                "bonus_points": 0,
                "bonus_exp": 0,
                "level_up": False,
                "new_level": self.level_system.get_level(member_id),
                "message": claim_result.get("message", "领取失败"),
            }

        # 发放额外经验
        bonus_exp = claim_result.get("bonus_exp", 0)
        level_result = self.level_system.add_exp(member_id, bonus_exp)

        return {
            "success": True,
            "badge_id": badge_id,
            "badge_name": claim_result["badge_name"],
            "rarity": claim_result["rarity"],
            "bonus_points": claim_result.get("bonus_points", 0),
            "bonus_exp": bonus_exp,
            "level_up": level_result["level_up"],
            "new_level": level_result["new_level"],
            "message": claim_result.get("message", "领取成功"),
        }

    # ============================================================
    # 查询接口
    # ============================================================

    async def get_full_profile(self, member_id: str) -> dict:
        """
        获取完整游戏化档案。

        汇总等级、经验进度、赛季信息、徽章列表、赛季任务进度等。

        Args:
            member_id: 会员ID

        Returns:
            完整档案字典
        """
        # 等级信息
        level = self.level_system.get_level(member_id)
        level_info = self.level_system.get_level_info(level)
        exp_progress = self.level_system.get_exp_progress(member_id)

        # 赛季信息
        season = self.season_system.get_current_season()
        season_score = self.season_system.get_member_season_score(member_id)
        season_tasks = self.season_system.get_season_task_progress(member_id)

        # 徽章
        badges = self.badge_system.get_member_badges(member_id)

        # 月免费行动力
        monthly_free_ap = self.level_system.get_monthly_free_ap(member_id)

        return {
            "member_id": member_id,
            "level": {
                "current": level,
                "name": level_info.name if level_info else "",
                "exp_progress": exp_progress,
                "reward_multiplier": level_info.reward_multiplier if level_info else 1.0,
                "monthly_free_ap": monthly_free_ap,
            },
            "season": {
                "season_id": season.season_id,
                "score": season_score,
                "sprint_active": self.season_system.is_sprint_period(),
                "sprint_multiplier": self.season_system.get_sprint_multiplier(),
                "tasks": season_tasks,
            },
            "badges": badges,
            "badge_count": len(badges),
        }

    # ============================================================
    # 辅助方法
    # ============================================================

    async def _get_checkin_streak(self, member_id: str) -> int:
        """
        获取签到连击数。

        尝试通过 badge_system 注册的统计查询获取，
        若无注册则返回 0。

        Args:
            member_id: 会员ID

        Returns:
            连续签到天数
        """
        query_fn = self.badge_system._stat_queries.get("checkin_streak")
        if query_fn:
            try:
                return await query_fn(member_id)
            except Exception:
                return 0
        return 0

    def register_stat_query(self, stat_name: str, query_fn) -> None:
        """
        注册统计查询回调（透传到 BadgeSystem）。

        Args:
            stat_name: 统计名称
            query_fn: async (member_id) → int 回调
        """
        self.badge_system.register_stat_query(stat_name, query_fn)


# 单例全局实例（API层直接引用）
game_engine = GameEngine()

__all__ = ["GameEngine", "game_engine", "LevelInfo", "BadgeRarity", "SeasonInfo"]
