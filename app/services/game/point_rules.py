"""
商脉系统 — 积分获取规则

实现技术规格 6.2 的完整积分规则表：
  每个行为对应 [积分, 经验, 每日/每周/每月次数限制, 关联徽章]。
  行动力消费额外触发积分奖励。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Optional


# ===== 积分规则定义 =====

class LimitType(str, Enum):
    """限制类型"""
    DAILY = "daily"            # 每日限制
    WEEKLY = "weekly"          # 每周限制
    MONTHLY = "monthly"        # 每月限制
    PER_EVENT = "per_event"    # 每次活动限制
    UNLIMITED = "unlimited"    # 无限制


@dataclass(frozen=True)
class PointRule:
    """单条积分规则"""
    action: str                     # 行为标识（大写蛇形）
    name: str                       # 行为中文名
    points: int                     # 基础积分
    exp: int                        # 基础经验
    limit_type: LimitType           # 限制类型
    limit_value: int                # 限制次数（0=无限制）
    badge_id: Optional[str]         # 关联徽章ID（首次达成时获得）
    description: str = ""           # 补充说明


# ===== 完整积分规则表 =====

POINT_RULES: dict[str, PointRule] = {
    "DAILY_CHECKIN": PointRule(
        action="DAILY_CHECKIN",
        name="每日签到",
        points=10,
        exp=10,
        limit_type=LimitType.DAILY,
        limit_value=1,
        badge_id=None,
        description="每日首次签到",
    ),
    "STREAK_7": PointRule(
        action="STREAK_7",
        name="连续7天签到",
        points=50,
        exp=30,
        limit_type=LimitType.UNLIMITED,
        limit_value=0,
        badge_id="week_warrior",
        description="连续签到7天额外奖励",
    ),
    "STREAK_30": PointRule(
        action="STREAK_30",
        name="连续30天签到",
        points=200,
        exp=100,
        limit_type=LimitType.UNLIMITED,
        limit_value=0,
        badge_id="month_champion",
        description="连续签到30天额外奖励",
    ),
    "PROFILE_COMPLETE": PointRule(
        action="PROFILE_COMPLETE",
        name="完善资料",
        points=20,
        exp=20,
        limit_type=LimitType.UNLIMITED,
        limit_value=0,
        badge_id="first_step",
        description="首次完善个人资料",
    ),
    "SET_ROLES": PointRule(
        action="SET_ROLES",
        name="设置十维角色",
        points=30,
        exp=30,
        limit_type=LimitType.UNLIMITED,
        limit_value=0,
        badge_id="role_master",
        description="首次设置十维角色标识",
    ),
    "TRIGGER_MATCH": PointRule(
        action="TRIGGER_MATCH",
        name="触发匹配",
        points=15,
        exp=20,
        limit_type=LimitType.DAILY,
        limit_value=3,
        badge_id=None,
        description="触发智能匹配",
    ),
    "VIEW_MATCH": PointRule(
        action="VIEW_MATCH",
        name="查看匹配",
        points=5,
        exp=5,
        limit_type=LimitType.DAILY,
        limit_value=5,
        badge_id=None,
        description="查看匹配结果",
    ),
    "ICEBREAK": PointRule(
        action="ICEBREAK",
        name="破冰对话",
        points=25,
        exp=30,
        limit_type=LimitType.DAILY,
        limit_value=3,
        badge_id="icebreaker",
        description="完成破冰对话（首次获徽章）",
    ),
    "RECORD_INTERACTION": PointRule(
        action="RECORD_INTERACTION",
        name="记录互动",
        points=10,
        exp=15,
        limit_type=LimitType.DAILY,
        limit_value=5,
        badge_id=None,
        description="记录人际互动",
    ),
    "REVIEW_FEEDBACK": PointRule(
        action="REVIEW_FEEDBACK",
        name="复盘反馈",
        points=15,
        exp=20,
        limit_type=LimitType.DAILY,
        limit_value=3,
        badge_id=None,
        description="完成复盘反馈",
    ),
    "COACH_DIAGNOSIS": PointRule(
        action="COACH_DIAGNOSIS",
        name="教练诊断",
        points=30,
        exp=40,
        limit_type=LimitType.MONTHLY,
        limit_value=1,
        badge_id="self_aware",
        description="完成教练诊断（首次获徽章）",
    ),
    "CREATE_COOPERATION": PointRule(
        action="CREATE_COOPERATION",
        name="创建合作",
        points=50,
        exp=60,
        limit_type=LimitType.WEEKLY,
        limit_value=2,
        badge_id=None,
        description="创建合作项目",
    ),
    "COMPLETE_COOP_TASK": PointRule(
        action="COMPLETE_COOP_TASK",
        name="完成合作任务",
        points=30,
        exp=40,
        limit_type=LimitType.UNLIMITED,
        limit_value=0,
        badge_id=None,
        description="完成合作项目中的任务",
    ),
    "COMPLETE_COOP_PROJECT": PointRule(
        action="COMPLETE_COOP_PROJECT",
        name="完成合作项目",
        points=100,
        exp=150,
        limit_type=LimitType.UNLIMITED,
        limit_value=0,
        badge_id="cooperator",
        description="完成整个合作项目（首次获徽章）",
    ),
    "ATTEND_EVENT": PointRule(
        action="ATTEND_EVENT",
        name="参加活动",
        points=20,
        exp=20,
        limit_type=LimitType.PER_EVENT,
        limit_value=1,
        badge_id=None,
        description="参加线下/线上活动",
    ),
    "REFERRAL": PointRule(
        action="REFERRAL",
        name="引荐好友",
        points=50,
        exp=60,
        limit_type=LimitType.UNLIMITED,
        limit_value=0,
        badge_id="connector",
        description="成功引荐好友（首次获徽章）",
    ),
    "MECE_ANALYSIS": PointRule(
        action="MECE_ANALYSIS",
        name="MECE分析",
        points=10,
        exp=15,
        limit_type=LimitType.DAILY,
        limit_value=3,
        badge_id=None,
        description="使用MECE工具分析",
    ),
    "SEVEN_STEP": PointRule(
        action="SEVEN_STEP",
        name="七步法",
        points=20,
        exp=25,
        limit_type=LimitType.DAILY,
        limit_value=2,
        badge_id="strategist",
        description="使用七步法工具（首次获徽章）",
    ),
    "CHAIN_ANALYSIS": PointRule(
        action="CHAIN_ANALYSIS",
        name="产业链分析",
        points=15,
        exp=20,
        limit_type=LimitType.DAILY,
        limit_value=3,
        badge_id=None,
        description="使用产业链分析工具",
    ),
    "COACH_DIALOG": PointRule(
        action="COACH_DIALOG",
        name="教练对话",
        points=5,
        exp=8,
        limit_type=LimitType.DAILY,
        limit_value=10,
        badge_id=None,
        description="与AI教练对话（每轮）",
    ),
}


class PointRulesEngine:
    """
    积分规则引擎

    职责：
      - 管理全量积分规则
      - 判断行为是否触发积分（频率限制检查）
      - 计算实际积分/经验（含等级加成、冲刺期加成）
      - 记录行为次数（用于频率限制）
    """

    def __init__(self) -> None:
        # member_id → { action → { date_str → count } }
        self._action_counts: dict[str, dict[str, dict[str, int]]] = {}

    def get_rule(self, action: str) -> Optional[PointRule]:
        """
        获取指定行为的积分规则。

        Args:
            action: 行为标识

        Returns:
            PointRule 或 None
        """
        return POINT_RULES.get(action)

    def get_all_rules(self) -> list[dict]:
        """
        获取全部积分规则列表。

        Returns:
            规则列表
        """
        return [
            {
                "action": r.action,
                "name": r.name,
                "points": r.points,
                "exp": r.exp,
                "limit_type": r.limit_type.value,
                "limit_value": r.limit_value,
                "badge_id": r.badge_id,
                "description": r.description,
            }
            for r in POINT_RULES.values()
        ]

    def check_limit(self, member_id: str, action: str) -> dict:
        """
        检查行为频率限制。

        Args:
            member_id: 会员ID
            action: 行为标识

        Returns:
            {
                "allowed": bool,
                "current_count": int,
                "limit_value": int,
                "limit_type": str,
                "remaining": int  # 剩余次数，-1 表示无限制
            }
        """
        rule = POINT_RULES.get(action)
        if rule is None:
            return {
                "allowed": False,
                "current_count": 0,
                "limit_value": 0,
                "limit_type": "unknown",
                "remaining": 0,
            }

        if rule.limit_type == LimitType.UNLIMITED:
            return {
                "allowed": True,
                "current_count": 0,
                "limit_value": 0,
                "limit_type": "unlimited",
                "remaining": -1,
            }

        current_count = self._get_current_count(member_id, action, rule.limit_type)

        if rule.limit_type == LimitType.PER_EVENT:
            # PER_EVENT 每个活动独立计算，默认允许
            return {
                "allowed": True,
                "current_count": current_count,
                "limit_value": rule.limit_value,
                "limit_type": "per_event",
                "remaining": max(0, rule.limit_value - current_count),
            }

        allowed = current_count < rule.limit_value
        remaining = max(0, rule.limit_value - current_count)

        return {
            "allowed": allowed,
            "current_count": current_count,
            "limit_value": rule.limit_value,
            "limit_type": rule.limit_type.value,
            "remaining": remaining if allowed else 0,
        }

    def record_action(self, member_id: str, action: str) -> None:
        """
        记录一次行为（用于频率限制计数）。

        Args:
            member_id: 会员ID
            action: 行为标识
        """
        rule = POINT_RULES.get(action)
        if rule is None or rule.limit_type == LimitType.UNLIMITED:
            return

        period_key = self._get_period_key(rule.limit_type)

        if member_id not in self._action_counts:
            self._action_counts[member_id] = {}
        if action not in self._action_counts[member_id]:
            self._action_counts[member_id][action] = {}

        current = self._action_counts[member_id][action].get(period_key, 0)
        self._action_counts[member_id][action][period_key] = current + 1

    def calculate_reward(self, member_id: str, action: str,
                         level_multiplier: float = 1.0,
                         sprint_multiplier: float = 1.0) -> dict:
        """
        计算行为对应的实际积分/经验奖励。

        Args:
            member_id: 会员ID
            action: 行为标识
            level_multiplier: 等级加成倍率
            sprint_multiplier: 冲刺期加成倍率

        Returns:
            {
                "action": str,
                "base_points": int,
                "base_exp": int,
                "level_multiplier": float,
                "sprint_multiplier": float,
                "final_points": int,
                "final_exp": int,
                "badge_id": Optional[str]
            }
        """
        rule = POINT_RULES.get(action)
        if rule is None:
            return {
                "action": action,
                "base_points": 0,
                "base_exp": 0,
                "level_multiplier": level_multiplier,
                "sprint_multiplier": sprint_multiplier,
                "final_points": 0,
                "final_exp": 0,
                "badge_id": None,
            }

        # 积分：等级加成 × 冲刺加成
        final_points = int(rule.points * level_multiplier * sprint_multiplier)
        # 经验：只受等级加成，不受冲刺加成
        final_exp = int(rule.exp * level_multiplier)

        return {
            "action": action,
            "base_points": rule.points,
            "base_exp": rule.exp,
            "level_multiplier": level_multiplier,
            "sprint_multiplier": sprint_multiplier,
            "final_points": final_points,
            "final_exp": final_exp,
            "badge_id": rule.badge_id,
        }

    # ----- 内部方法 -----

    def _get_current_count(self, member_id: str, action: str, limit_type: LimitType) -> int:
        """获取当前周期内的行为计数"""
        if member_id not in self._action_counts:
            return 0
        if action not in self._action_counts[member_id]:
            return 0

        period_key = self._get_period_key(limit_type)
        return self._action_counts[member_id][action].get(period_key, 0)

    @staticmethod
    def _get_period_key(limit_type: LimitType) -> str:
        """获取当前周期的缓存键"""
        today = date.today()
        if limit_type == LimitType.DAILY:
            return today.isoformat()
        elif limit_type == LimitType.WEEKLY:
            # 返回本周一的日期
            monday = today - timedelta(days=today.weekday())
            return monday.isoformat()
        elif limit_type == LimitType.MONTHLY:
            return f"{today.year}-{today.month:02d}"
        else:
            return today.isoformat()
