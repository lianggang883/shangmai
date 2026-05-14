"""
商脉系统 — 等级经验系统

实现技术规格 6.1 的等级经验表：
  Lv1(新人,0/500,50AP,1.0x) → Lv2(探索者,500/1500,80AP,1.1x)
  → Lv3(达人,2000/4000,120AP,1.2x) → Lv4(专家,6000/8000,180AP,1.3x)
  → Lv5(领袖,14000/16000,260AP,1.5x) → Lv6(宗师,30000/无限,360AP,2.0x)

经验值只升不降，升级自动发放月免费行动力额度增量。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ===== 等级经验表定义 =====

@dataclass(frozen=True)
class LevelInfo:
    """单个等级的完整信息"""
    level: int                       # 等级编号 1-6
    name: str                        # 等级名称
    exp_required: int                # 升至下一级所需累计经验 (Lv6 为进入该级门槛)
    exp_next: Optional[int]          # 下一级累计经验门槛，Lv6 为 None (无上限)
    monthly_free_ap: int             # 月免费行动力额度
    reward_multiplier: float         # 积分/经验加成倍率


LEVEL_TABLE: dict[int, LevelInfo] = {
    1: LevelInfo(level=1, name="新人",   exp_required=0,     exp_next=500,   monthly_free_ap=50,  reward_multiplier=1.0),
    2: LevelInfo(level=2, name="探索者", exp_required=500,   exp_next=1500,  monthly_free_ap=80,  reward_multiplier=1.1),
    3: LevelInfo(level=3, name="达人",   exp_required=2000,  exp_next=4000,  monthly_free_ap=120, reward_multiplier=1.2),
    4: LevelInfo(level=4, name="专家",   exp_required=6000,  exp_next=8000,  monthly_free_ap=180, reward_multiplier=1.3),
    5: LevelInfo(level=5, name="领袖",   exp_required=14000, exp_next=16000, monthly_free_ap=260, reward_multiplier=1.5),
    6: LevelInfo(level=6, name="宗师",   exp_required=30000, exp_next=None,  monthly_free_ap=360, reward_multiplier=2.0),
}

MAX_LEVEL: int = 6


@dataclass
class MemberLevelState:
    """会员等级状态（内存中的快照）"""
    member_id: str
    level: int = 1
    exp_points: int = 0
    monthly_free_ap: int = 50


class LevelSystem:
    """
    等级经验系统

    职责：
      - 管理会员经验值增减（只升不降）
      - 自动检查并触发升级
      - 提供等级详情查询
      - 按等级递增月免费行动力
    """

    def __init__(self) -> None:
        # member_id → MemberLevelState
        self._states: dict[str, MemberLevelState] = {}

    # ----- 公开接口 -----

    def add_exp(self, member_id: str, amount: int) -> dict:
        """
        增加经验值，自动检查升级。

        Args:
            member_id: 会员ID
            amount: 经验增量（必须 > 0）

        Returns:
            {
                "old_level": int,
                "new_level": int,
                "exp_added": int,
                "exp_total": int,
                "level_up": bool,
                "levels_gained": int  # 连跳几级
            }
        """
        if amount <= 0:
            return self._no_change_result(member_id)

        state = self._get_or_create(member_id)
        old_level = state.level
        state.exp_points += amount

        # 循环检查升级（支持连跳）
        levels_gained = 0
        while state.level < MAX_LEVEL:
            next_info = LEVEL_TABLE[state.level + 1]
            if state.exp_points >= next_info.exp_required:
                state.level += 1
                state.monthly_free_ap = LEVEL_TABLE[state.level].monthly_free_ap
                levels_gained += 1
            else:
                break

        return {
            "old_level": old_level,
            "new_level": state.level,
            "exp_added": amount,
            "exp_total": state.exp_points,
            "level_up": state.level > old_level,
            "levels_gained": levels_gained,
        }

    def get_level(self, member_id: str) -> int:
        """
        查询会员当前等级。

        Args:
            member_id: 会员ID

        Returns:
            当前等级 1-6
        """
        state = self._get_or_create(member_id)
        return state.level

    def get_level_info(self, level: int) -> Optional[LevelInfo]:
        """
        查询指定等级的详情。

        Args:
            level: 等级编号 1-6

        Returns:
            LevelInfo 或 None（等级不存在时）
        """
        return LEVEL_TABLE.get(level)

    def get_member_state(self, member_id: str) -> MemberLevelState:
        """
        获取会员等级状态快照。

        Args:
            member_id: 会员ID

        Returns:
            MemberLevelState 实例
        """
        return self._get_or_create(member_id)

    def get_monthly_free_ap(self, member_id: str) -> int:
        """
        查询会员月免费行动力额度。

        Args:
            member_id: 会员ID

        Returns:
            月免费行动力点数
        """
        state = self._get_or_create(member_id)
        return state.monthly_free_ap

    def get_reward_multiplier(self, member_id: str) -> float:
        """
        查询会员当前积分/经验加成倍率。

        Args:
            member_id: 会员ID

        Returns:
            加成倍率 (1.0 ~ 2.0)
        """
        state = self._get_or_create(member_id)
        return LEVEL_TABLE[state.level].reward_multiplier

    def get_exp_progress(self, member_id: str) -> dict:
        """
        查询经验进度详情（当前/下一级门槛/进度百分比）。

        Args:
            member_id: 会员ID

        Returns:
            {
                "level": int,
                "current_exp": int,
                "next_level_exp": Optional[int],  # 下一级门槛，Lv6 返回 None
                "progress_pct": float,             # 当前级到下一级的进度百分比
            }
        """
        state = self._get_or_create(member_id)
        info = LEVEL_TABLE[state.level]

        if info.exp_next is None:
            # 已达满级
            return {
                "level": state.level,
                "current_exp": state.exp_points,
                "next_level_exp": None,
                "progress_pct": 100.0,
            }

        current_base = info.exp_required
        next_exp = info.exp_next
        progress = (state.exp_points - current_base) / (next_exp - current_base) * 100.0
        progress = max(0.0, min(100.0, progress))

        return {
            "level": state.level,
            "current_exp": state.exp_points,
            "next_level_exp": next_exp,
            "progress_pct": round(progress, 1),
        }

    # ----- 内部方法 -----

    def _get_or_create(self, member_id: str) -> MemberLevelState:
        """获取或创建会员等级状态"""
        if member_id not in self._states:
            self._states[member_id] = MemberLevelState(member_id=member_id)
        return self._states[member_id]

    def _no_change_result(self, member_id: str) -> dict:
        """生成无变化的结果"""
        state = self._get_or_create(member_id)
        return {
            "old_level": state.level,
            "new_level": state.level,
            "exp_added": 0,
            "exp_total": state.exp_points,
            "level_up": False,
            "levels_gained": 0,
        }
