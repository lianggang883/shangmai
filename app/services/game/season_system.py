"""
商脉系统 — 赛季机制

实现技术规格 6.4 的赛季系统：
  - 赛季周期: 90天(每季度)，格式 S2025Q3
  - 赛季重置: 排行榜、赛季积分、赛季任务进度
  - 赛季保留: 等级、总经验、已获徽章、历史合作项目
  - 赛季任务: 3个专属任务
  - 冲刺期: 最后3天积分1.5倍加成
  - Top10/Top50/Top100 阶梯奖励
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Optional


# ===== 赛季常量 =====

SEASON_DURATION_DAYS: int = 90     # 赛季持续天数
SPRINT_DAYS: int = 3               # 冲刺期天数
SPRINT_MULTIPLIER: float = 1.5     # 冲刺期积分加成


# ===== 赛季数据结构 =====

@dataclass(frozen=True)
class SeasonInfo:
    """赛季基本信息"""
    season_id: str                  # 格式 S2025Q3
    quarter: int                    # 季度 1-4
    year: int                       # 年份
    start_date: date                # 开始日期
    end_date: date                  # 结束日期
    sprint_start: date              # 冲刺期开始日期
    is_current: bool = False        # 是否当前赛季


@dataclass
class SeasonTask:
    """赛季专属任务"""
    task_id: str
    season_id: str
    name: str                       # 任务名称
    description: str                # 任务描述
    target_value: int               # 目标值
    points_reward: int              # 积分奖励
    exp_reward: int                 # 经验奖励
    badge_reward: Optional[str]     # 徽章奖励ID


@dataclass(frozen=True)
class SeasonReward:
    """赛季排名奖励"""
    rank_min: int                   # 最低排名（含）
    rank_max: int                   # 最高排名（含）
    badge_id: str                   # 限定徽章
    action_power: int               # 行动力奖励
    card_name: str                  # 专属名片名称
    bonus_points: int = 0           # 额外积分


# ===== 赛季奖励表 =====

SEASON_REWARDS: list[SeasonReward] = [
    SeasonReward(
        rank_min=1, rank_max=10,
        badge_id="season_top10",
        action_power=500,
        card_name="赛季十强专属名片",
        bonus_points=500,
    ),
    SeasonReward(
        rank_min=11, rank_max=50,
        badge_id="season_top50",
        action_power=200,
        card_name="赛季五十强名片",
        bonus_points=200,
    ),
    SeasonReward(
        rank_min=51, rank_max=100,
        badge_id="season_top100",
        action_power=100,
        card_name="赛季百强名片",
        bonus_points=100,
    ),
]


# ===== 默认赛季任务模板 =====

DEFAULT_SEASON_TASKS: list[dict] = [
    {
        "task_id": "cross_industry_match",
        "name": "跨界匹配",
        "description": "完成5个跨行业匹配",
        "target_value": 5,
        "points_reward": 200,
        "exp_reward": 150,
        "badge_reward": None,
    },
    {
        "task_id": "deep_connection",
        "name": "深度连接",
        "description": "完成3次破冰对话并记录互动",
        "target_value": 3,
        "points_reward": 150,
        "exp_reward": 120,
        "badge_reward": None,
    },
    {
        "task_id": "mvp_launch",
        "name": "MVP启动",
        "description": "创建并启动1个MVP合作计划",
        "target_value": 1,
        "points_reward": 300,
        "exp_reward": 200,
        "badge_reward": None,
    },
]


class SeasonSystem:
    """
    赛季机制

    职责：
      - 管理赛季周期（90天/季度）
      - 赛季积分排行与结算
      - 冲刺期加成计算
      - 赛季任务管理
      - 赛季结算奖励发放
      - 赛季重置（保留等级/经验/徽章）
    """

    def __init__(self) -> None:
        # season_id → { member_id → season_score }
        self._rankings: dict[str, dict[str, int]] = {}
        # season_id → SeasonInfo
        self._seasons: dict[str, SeasonInfo] = {}
        # season_id → [SeasonTask]
        self._tasks: dict[str, list[SeasonTask]] = {}
        # member_id → { season_id → { task_id → progress } }
        self._task_progress: dict[str, dict[str, dict[str, int]]] = {}
        # 初始化当前赛季
        self._ensure_current_season()

    # ----- 公开接口 -----

    def get_current_season(self) -> SeasonInfo:
        """
        获取当前赛季信息。

        Returns:
            SeasonInfo 实例
        """
        season_id = self._calc_season_id(date.today())
        if season_id not in self._seasons:
            self._ensure_current_season()
        info = self._seasons[season_id]
        return info

    def get_season_rewards(self, season_id: Optional[str] = None) -> list[dict]:
        """
        获取赛季奖励配置。

        Args:
            season_id: 赛季ID，默认当前赛季

        Returns:
            奖励配置列表
        """
        return [
            {
                "rank_range": f"{r.rank_min}-{r.rank_max}",
                "badge_id": r.badge_id,
                "action_power": r.action_power,
                "card_name": r.card_name,
                "bonus_points": r.bonus_points,
            }
            for r in SEASON_REWARDS
        ]

    async def calculate_season_ranking(self, season_id: Optional[str] = None) -> list[dict]:
        """
        计算赛季排名。

        Args:
            season_id: 赛季ID，默认当前赛季

        Returns:
            排名列表 [{ rank, member_id, score }]
        """
        if season_id is None:
            season_id = self.get_current_season().season_id

        ranking_data = self._rankings.get(season_id, {})
        sorted_entries = sorted(ranking_data.items(), key=lambda x: x[1], reverse=True)

        return [
            {"rank": i + 1, "member_id": mid, "score": score}
            for i, (mid, score) in enumerate(sorted_entries)
        ]

    def get_member_season_score(self, member_id: str, season_id: Optional[str] = None) -> int:
        """
        查询会员赛季积分。

        Args:
            member_id: 会员ID
            season_id: 赛季ID，默认当前赛季

        Returns:
            赛季积分
        """
        if season_id is None:
            season_id = self.get_current_season().season_id
        return self._rankings.get(season_id, {}).get(member_id, 0)

    def add_season_points(self, member_id: str, points: int, season_id: Optional[str] = None) -> int:
        """
        增加赛季积分（含冲刺期加成）。

        Args:
            member_id: 会员ID
            points: 基础积分
            season_id: 赛季ID，默认当前赛季

        Returns:
            实际增加的积分（含加成）
        """
        if season_id is None:
            season_id = self.get_current_season().season_id

        # 冲刺期加成
        actual_points = points
        if self._is_sprint_period(season_id):
            actual_points = int(points * SPRINT_MULTIPLIER)

        if season_id not in self._rankings:
            self._rankings[season_id] = {}
        self._rankings[season_id][member_id] = \
            self._rankings[season_id].get(member_id, 0) + actual_points

        return actual_points

    def is_sprint_period(self) -> bool:
        """
        判断当前是否处于赛季冲刺期。

        Returns:
            是否冲刺期
        """
        season_id = self._calc_season_id(date.today())
        return self._is_sprint_period(season_id)

    def get_sprint_multiplier(self) -> float:
        """
        获取当前冲刺期加成倍率。

        Returns:
            加成倍率（非冲刺期返回 1.0）
        """
        if self.is_sprint_period():
            return SPRINT_MULTIPLIER
        return 1.0

    def get_season_tasks(self, season_id: Optional[str] = None) -> list[dict]:
        """
        获取赛季专属任务列表。

        Args:
            season_id: 赛季ID，默认当前赛季

        Returns:
            任务列表
        """
        if season_id is None:
            season_id = self.get_current_season().season_id

        tasks = self._tasks.get(season_id, [])
        return [
            {
                "task_id": t.task_id,
                "name": t.name,
                "description": t.description,
                "target_value": t.target_value,
                "points_reward": t.points_reward,
                "exp_reward": t.exp_reward,
                "badge_reward": t.badge_reward,
            }
            for t in tasks
        ]

    def get_season_task_progress(self, member_id: str, season_id: Optional[str] = None) -> list[dict]:
        """
        获取会员赛季任务进度。

        Args:
            member_id: 会员ID
            season_id: 赛季ID，默认当前赛季

        Returns:
            任务进度列表
        """
        if season_id is None:
            season_id = self.get_current_season().season_id

        tasks = self._tasks.get(season_id, [])
        progress_map = self._task_progress.get(member_id, {}).get(season_id, {})

        result: list[dict] = []
        for t in tasks:
            current = progress_map.get(t.task_id, 0)
            result.append({
                "task_id": t.task_id,
                "name": t.name,
                "target_value": t.target_value,
                "current_value": current,
                "completed": current >= t.target_value,
                "points_reward": t.points_reward,
                "exp_reward": t.exp_reward,
            })
        return result

    def update_season_task_progress(self, member_id: str, task_id: str, increment: int = 1,
                                     season_id: Optional[str] = None) -> dict:
        """
        更新赛季任务进度。

        Args:
            member_id: 会员ID
            task_id: 任务ID
            increment: 进度增量
            season_id: 赛季ID，默认当前赛季

        Returns:
            更新后的进度信息
        """
        if season_id is None:
            season_id = self.get_current_season().season_id

        if member_id not in self._task_progress:
            self._task_progress[member_id] = {}
        if season_id not in self._task_progress[member_id]:
            self._task_progress[member_id][season_id] = {}

        current = self._task_progress[member_id][season_id].get(task_id, 0)
        new_value = current + increment
        self._task_progress[member_id][season_id][task_id] = new_value

        # 查找任务定义获取 target
        tasks = self._tasks.get(season_id, [])
        task_def = next((t for t in tasks if t.task_id == task_id), None)
        target = task_def.target_value if task_def else 0

        return {
            "task_id": task_id,
            "current_value": new_value,
            "target_value": target,
            "completed": new_value >= target if target > 0 else False,
        }

    async def settle_season(self, season_id: str) -> list[dict]:
        """
        赛季结算：计算排名并发放奖励。

        Args:
            season_id: 要结算的赛季ID

        Returns:
            结算结果列表 [{ member_id, rank, rewards }]
        """
        ranking = await self.calculate_season_ranking(season_id)
        results: list[dict] = []

        for entry in ranking:
            rank = entry["rank"]
            member_id = entry["member_id"]
            reward = self._get_reward_for_rank(rank)

            results.append({
                "member_id": member_id,
                "rank": rank,
                "score": entry["score"],
                "badge_id": reward.badge_id if reward else None,
                "action_power": reward.action_power if reward else 0,
                "card_name": reward.card_name if reward else None,
                "bonus_points": reward.bonus_points if reward else 0,
            })

        return results

    def reset_season(self, season_id: str) -> dict:
        """
        重置赛季数据（排行榜、赛季积分、任务进度）。
        保留：等级、总经验、已获徽章、历史合作项目。

        Args:
            season_id: 要重置的赛季ID

        Returns:
            重置结果
        """
        # 清除排名数据
        cleared_rankings = len(self._rankings.pop(season_id, {}))

        # 清除赛季任务进度
        cleared_progress = 0
        for member_id in list(self._task_progress.keys()):
            if season_id in self._task_progress[member_id]:
                del self._task_progress[member_id][season_id]
                cleared_progress += 1

        return {
            "season_id": season_id,
            "cleared_rankings": cleared_rankings,
            "cleared_progress": cleared_progress,
            "preserved": ["level", "exp_points", "badges", "cooperation_projects"],
        }

    # ----- 内部方法 -----

    def _ensure_current_season(self) -> None:
        """确保当前赛季信息已初始化"""
        today = date.today()
        season_id = self._calc_season_id(today)

        if season_id in self._seasons:
            return

        # 计算赛季起止日期
        quarter = (today.month - 1) // 3 + 1
        start_month = (quarter - 1) * 3 + 1
        start_date = date(today.year, start_month, 1)

        # 季度最后一个月的最后一天
        end_month = start_month + 2
        if end_month == 3:
            end_day = 31
        elif end_month == 6:
            end_day = 30
        elif end_month == 9:
            end_day = 30
        else:
            end_day = 31
        end_date = date(today.year, end_month, end_day)

        # 冲刺期开始日期
        sprint_start = end_date - timedelta(days=SPRINT_DAYS - 1)

        self._seasons[season_id] = SeasonInfo(
            season_id=season_id,
            quarter=quarter,
            year=today.year,
            start_date=start_date,
            end_date=end_date,
            sprint_start=sprint_start,
            is_current=True,
        )

        # 初始化赛季任务
        if season_id not in self._tasks:
            self._tasks[season_id] = [
                SeasonTask(
                    task_id=t["task_id"],
                    season_id=season_id,
                    name=t["name"],
                    description=t["description"],
                    target_value=t["target_value"],
                    points_reward=t["points_reward"],
                    exp_reward=t["exp_reward"],
                    badge_reward=t.get("badge_reward"),
                )
                for t in DEFAULT_SEASON_TASKS
            ]

    @staticmethod
    def _calc_season_id(d: date) -> str:
        """
        计算赛季ID，格式 S2025Q3。

        Args:
            d: 日期

        Returns:
            赛季ID字符串
        """
        quarter = (d.month - 1) // 3 + 1
        return f"S{d.year}Q{quarter}"

    def _is_sprint_period(self, season_id: str) -> bool:
        """判断指定赛季当前是否在冲刺期"""
        season = self._seasons.get(season_id)
        if season is None:
            return False
        today = date.today()
        return today >= season.sprint_start and today <= season.end_date

    @staticmethod
    def _get_reward_for_rank(rank: int) -> Optional[SeasonReward]:
        """根据排名获取对应奖励"""
        for reward in SEASON_REWARDS:
            if reward.rank_min <= rank <= reward.rank_max:
                return reward
        return None
