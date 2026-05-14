"""
商脉系统 — 游戏化引擎 (兼容层)

本模块用新的 GameEngine 替换原来的简单实现，
保留全局单例 game_service 接口兼容。

新架构：
  app/services/game/          ← 完整游戏化引擎
    ├── __init__.py           ← GameEngine 统一入口
    ├── level_system.py       ← 等级经验系统
    ├── badge_system.py       ← 徽章体系
    ├── season_system.py      ← 赛季机制
    └── point_rules.py        ← 积分获取规则

  本文件 (game_service.py)   ← 全局单例 + 兼容接口

参考技术规格样板 Chapter 6
"""
from __future__ import annotations

from typing import Optional

from app.services.game import GameEngine


class GameService:
    """
    游戏化服务（兼容层）

    封装 GameEngine，提供与旧接口兼容的方法签名，
    同时暴露完整的 GameEngine 能力。
    """

    def __init__(self) -> None:
        """初始化游戏化服务，创建 GameEngine 实例"""
        self.engine: GameEngine = GameEngine()

    # ============================================================
    # 旧接口兼容方法
    # ============================================================

    async def get_or_create_profile(self, member_id: str) -> dict:
        """
        获取或创建游戏化档案。

        Args:
            member_id: 会员ID

        Returns:
            完整游戏化档案字典
        """
        return await self.engine.get_full_profile(member_id)

    async def checkin(self, member_id: str) -> dict:
        """
        每日签到。

        Args:
            member_id: 会员ID

        Returns:
            签到结果（含连击、额外奖励、徽章）
        """
        return await self.engine.on_checkin(member_id)

    async def record_event(self, member_id: str, event_type: str,
                           context: Optional[dict] = None) -> dict:
        """
        记录游戏化事件（通用行为触发积分入口）。

        Args:
            member_id: 会员ID
            event_type: 行为标识（对应 POINT_RULES 的 key）
            context: 附加上下文

        Returns:
            行为触发结果
        """
        return await self.engine.on_action(member_id, event_type, context)

    async def get_leaderboard(self, season: Optional[str] = None) -> list[dict]:
        """
        获取排行榜。

        Args:
            season: 赛季ID，默认当前赛季

        Returns:
            排名列表
        """
        return await self.engine.season_system.calculate_season_ranking(season)

    async def get_tasks(self, member_id: str, task_type: Optional[str] = None) -> list[dict]:
        """
        获取任务列表（含赛季任务）。

        Args:
            member_id: 会员ID
            task_type: 任务类型筛选（暂未实现分类，返回赛季任务）

        Returns:
            任务列表
        """
        return self.engine.season_system.get_season_task_progress(member_id)

    async def complete_task(self, member_id: str, task_name: str) -> dict:
        """
        完成任务（预留接口，具体实现依赖外部任务系统）。

        Args:
            member_id: 会员ID
            task_name: 任务名称

        Returns:
            完成结果
        """
        # 尝试作为赛季任务更新进度
        result = self.engine.season_system.update_season_task_progress(
            member_id, task_name
        )
        if result.get("completed"):
            # 获取任务定义的奖励
            tasks = self.engine.season_system.get_season_tasks()
            task_def = next((t for t in tasks if t["task_id"] == task_name), None)
            if task_def:
                # 发放积分和经验
                await self.engine.on_action(member_id, "COMPLETE_COOP_TASK")
                return {
                    "success": True,
                    "task_name": task_name,
                    "points_earned": task_def.get("points_reward", 0),
                    "exp_earned": task_def.get("exp_reward", 0),
                }

        return {
            "success": True,
            "task_name": task_name,
            "progress": result,
        }

    # ============================================================
    # 新增接口（直接暴露 GameEngine 能力）
    # ============================================================

    async def claim_badge(self, member_id: str, badge_id: str) -> dict:
        """
        领取徽章。

        Args:
            member_id: 会员ID
            badge_id: 徽章ID

        Returns:
            领取结果（含额外积分/经验奖励）
        """
        return await self.engine.on_badge_claim(member_id, badge_id)

    async def get_badges(self, member_id: str) -> list[dict]:
        """
        查询已获徽章列表。

        Args:
            member_id: 会员ID

        Returns:
            徽章列表
        """
        return self.engine.badge_system.get_member_badges(member_id)

    async def check_badge_eligibility(self, member_id: str, badge_id: str) -> dict:
        """
        检查徽章获取条件。

        Args:
            member_id: 会员ID
            badge_id: 徽章ID

        Returns:
            条件检查结果
        """
        return await self.engine.badge_system.check_badge_eligibility(member_id, badge_id)

    def get_level_info(self, level: int) -> Optional[dict]:
        """
        查询指定等级详情。

        Args:
            level: 等级编号 1-6

        Returns:
            等级详情字典或 None
        """
        info = self.engine.level_system.get_level_info(level)
        if info is None:
            return None
        return {
            "level": info.level,
            "name": info.name,
            "exp_required": info.exp_required,
            "exp_next": info.exp_next,
            "monthly_free_ap": info.monthly_free_ap,
            "reward_multiplier": info.reward_multiplier,
        }

    def get_season_info(self) -> dict:
        """
        获取当前赛季信息。

        Returns:
            赛季信息字典
        """
        season = self.engine.season_system.get_current_season()
        return {
            "season_id": season.season_id,
            "quarter": season.quarter,
            "year": season.year,
            "start_date": season.start_date.isoformat(),
            "end_date": season.end_date.isoformat(),
            "sprint_start": season.sprint_start.isoformat(),
            "is_current": season.is_current,
            "sprint_active": self.engine.season_system.is_sprint_period(),
            "sprint_multiplier": self.engine.season_system.get_sprint_multiplier(),
        }

    def get_season_rewards(self) -> list[dict]:
        """
        获取赛季奖励配置。

        Returns:
            奖励配置列表
        """
        return self.engine.season_system.get_season_rewards()

    def get_point_rules(self) -> list[dict]:
        """
        获取全部积分规则。

        Returns:
            积分规则列表
        """
        return self.engine.point_rules.get_all_rules()

    def register_stat_query(self, stat_name: str, query_fn) -> None:
        """
        注册统计查询回调。

        Args:
            stat_name: 统计名称
            query_fn: async (member_id) → int 回调
        """
        self.engine.register_stat_query(stat_name, query_fn)

    async def get_full_profile(self, member_id: str) -> dict:
        """
        获取完整游戏化档案（新接口）。

        Args:
            member_id: 会员ID

        Returns:
            完整档案
        """
        return await self.engine.get_full_profile(member_id)


# 全局单例（与旧代码兼容）
game_service = GameService()
