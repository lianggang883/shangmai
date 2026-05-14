"""
风控规则引擎 — 技术规格 7.4

核心规则:
  1. 日消费限额（按等级）:
     Lv1=100, Lv2=200, Lv3=400, Lv4=800, Lv5=1500, Lv6=3000
  2. 单次限额: 500
  3. 突发频率: 10分钟内最多10次
  4. 异常模式检测（5维度规则引擎）:
     - 维度1: 单次金额异常（与历史均值偏差 > 3σ）
     - 维度2: 频率异常（短时高频消费）
     - 维度3: 时间异常（凌晨/非活跃时段突发消费）
     - 维度4: 目标异常（消费目标与历史模式不符）
     - 维度5: 累计异常（短时累计金额异常）
     总分 > 0.85 → 自动冻结账户

统一入口: check_before_consume()
"""
from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ===== 常量 =====

# 日消费限额（按等级）
DAILY_LIMITS: Dict[int, int] = {
    1: 100,
    2: 200,
    3: 400,
    4: 800,
    5: 1500,
    6: 3000,
}

# 单次消费限额
SINGLE_CONSUME_LIMIT: int = 500

# 突发频率限制: 时间窗口(秒) / 最大次数
FREQUENCY_WINDOW_SECONDS: int = 600  # 10分钟
FREQUENCY_MAX_COUNT: int = 10        # 最多10次

# 异常模式检测阈值
ANOMALY_FREEZE_THRESHOLD: float = 0.85  # 总分超过此值自动冻结
ANOMALY_WEIGHTS: Dict[str, float] = {
    "amount_deviation": 0.25,   # 维度1: 单次金额偏差
    "frequency_burst": 0.25,    # 维度2: 频率突发
    "time_anomaly": 0.15,       # 维度3: 时间异常
    "target_anomaly": 0.15,     # 维度4: 目标异常
    "cumulative_anomaly": 0.20, # 维度5: 累计异常
}


@dataclass
class ConsumeEvent:
    """消费事件记录"""
    member_id: str
    amount: int
    skill_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class MemberRiskProfile:
    """会员风控画像"""
    member_id: str
    level: int = 1
    is_frozen: bool = False
    frozen_reason: str = ""
    frozen_at: Optional[datetime] = None
    # 历史消费记录（最近N条）
    recent_consumptions: List[ConsumeEvent] = field(default_factory=list)
    # 日消费累计
    daily_consumed: Dict[str, int] = field(default_factory=dict)  # date_str → amount
    # 历史统计（用于异常检测）
    avg_consumption: float = 0.0
    std_consumption: float = 0.0
    total_count: int = 0
    # 异常评分记录
    last_anomaly_score: float = 0.0


@dataclass
class RiskCheckResult:
    """风控检查结果"""
    allowed: bool
    reason: str = ""
    daily_remaining: int = 0
    anomaly_score: float = 0.0
    triggered_rules: List[str] = field(default_factory=list)
    is_frozen: bool = False


class RiskEngine:
    """
    风控规则引擎

    统一入口: check_before_consume()
    在每次消费前调用，检查:
      - 账户是否被冻结
      - 日消费限额
      - 单次消费限额
      - 突发频率限制
      - 异常模式检测
    """

    def __init__(self) -> None:
        # 会员风控画像缓存
        self._profiles: Dict[str, MemberRiskProfile] = {}
        # 冻结回调
        self._on_freeze_account: Optional[callable] = None
        # 最大保留历史消费条数
        self._max_history: int = 100

    def set_freeze_callback(self, callback: callable) -> None:
        """
        设置账户冻结回调

        Args:
            callback: 异步回调 (member_id, reason) -> Coroutine
        """
        self._on_freeze_account = callback

    def _get_or_create_profile(
        self, member_id: str, level: int = 1
    ) -> MemberRiskProfile:
        """获取或创建会员风控画像"""
        if member_id not in self._profiles:
            self._profiles[member_id] = MemberRiskProfile(
                member_id=member_id, level=level
            )
        return self._profiles[member_id]

    def update_member_level(self, member_id: str, level: int) -> None:
        """更新会员等级"""
        profile = self._get_or_create_profile(member_id, level)
        profile.level = level

    async def check_before_consume(
        self,
        member_id: str,
        amount: int,
        skill_id: str = "",
        level: int = 1,
    ) -> RiskCheckResult:
        """
        消费前风控检查 — 统一入口

        检查顺序:
          1. 账户是否冻结
          2. 单次消费限额
          3. 日消费限额
          4. 突发频率限制
          5. 异常模式检测

        Args:
            member_id: 会员ID
            amount: 本次消费金额
            skill_id: 技能ID
            level: 会员等级

        Returns:
            风控检查结果
        """
        profile = self._get_or_create_profile(member_id, level)
        triggered_rules: list[str] = []

        # 1. 检查账户冻结
        if profile.is_frozen:
            return RiskCheckResult(
                allowed=False,
                reason=f"账户已被冻结: {profile.frozen_reason}",
                is_frozen=True,
                triggered_rules=["account_frozen"],
            )

        # 2. 单次消费限额
        if amount > SINGLE_CONSUME_LIMIT:
            triggered_rules.append("single_limit")
            return RiskCheckResult(
                allowed=False,
                reason=f"单次消费超限: {amount} > {SINGLE_CONSUME_LIMIT}",
                daily_remaining=self._get_daily_remaining(profile),
                triggered_rules=triggered_rules,
            )

        # 3. 日消费限额
        daily_remaining = self._get_daily_remaining(profile)
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_consumed = profile.daily_consumed.get(today_str, 0)

        if today_consumed + amount > DAILY_LIMITS.get(profile.level, 100):
            triggered_rules.append("daily_limit")
            daily_limit = DAILY_LIMITS.get(profile.level, 100)
            return RiskCheckResult(
                allowed=False,
                reason=(
                    f"日消费限额: 已消费{today_consumed}+本次{amount}"
                    f" > {daily_limit} (Lv{profile.level})"
                ),
                daily_remaining=daily_remaining,
                triggered_rules=triggered_rules,
            )

        # 4. 突发频率限制
        freq_ok, freq_reason = self._check_frequency(profile)
        if not freq_ok:
            triggered_rules.append("frequency_burst")
            return RiskCheckResult(
                allowed=False,
                reason=freq_reason,
                daily_remaining=daily_remaining,
                triggered_rules=triggered_rules,
            )

        # 5. 异常模式检测
        anomaly_score = self._calculate_anomaly_score(profile, amount, skill_id)
        if anomaly_score > ANOMALY_FREEZE_THRESHOLD:
            triggered_rules.append("anomaly_freeze")
            # 自动冻结
            await self._freeze_account(
                profile, f"异常模式检测触发，评分={anomaly_score:.2f}"
            )
            return RiskCheckResult(
                allowed=False,
                reason=f"异常消费行为检测，账户已冻结 (评分={anomaly_score:.2f})",
                daily_remaining=daily_remaining,
                anomaly_score=anomaly_score,
                triggered_rules=triggered_rules,
                is_frozen=True,
            )

        # 记录本次消费事件
        profile.recent_consumptions.append(
            ConsumeEvent(member_id=member_id, amount=amount, skill_id=skill_id)
        )
        # 更新日消费
        profile.daily_consumed[today_str] = today_consumed + amount
        # 更新历史统计
        self._update_stats(profile)
        profile.last_anomaly_score = anomaly_score

        # 清理过期历史
        self._cleanup_history(profile)

        return RiskCheckResult(
            allowed=True,
            reason="风控检查通过",
            daily_remaining=daily_remaining - amount,
            anomaly_score=anomaly_score,
        )

    def _get_daily_remaining(self, profile: MemberRiskProfile) -> int:
        """获取今日剩余可消费额度"""
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_consumed = profile.daily_consumed.get(today_str, 0)
        daily_limit = DAILY_LIMITS.get(profile.level, 100)
        return max(0, daily_limit - today_consumed)

    def _check_frequency(self, profile: MemberRiskProfile) -> Tuple[bool, str]:
        """
        检查突发频率

        10分钟内消费次数不超过 FREQUENCY_MAX_COUNT 次

        Returns:
            (是否通过, 原因)
        """
        now = datetime.now()
        window_start = now - timedelta(seconds=FREQUENCY_WINDOW_SECONDS)

        recent_count = sum(
            1 for evt in profile.recent_consumptions
            if evt.timestamp >= window_start
        )

        if recent_count >= FREQUENCY_MAX_COUNT:
            return False, (
                f"突发频率限制: {FREQUENCY_WINDOW_SECONDS}秒内已消费{recent_count}次"
                f"，超过{FREQUENCY_MAX_COUNT}次上限"
            )
        return True, ""

    def _calculate_anomaly_score(
        self,
        profile: MemberRiskProfile,
        amount: int,
        skill_id: str,
    ) -> float:
        """
        计算异常模式检测评分（5维度）

        维度1: 单次金额偏差 (amount_deviation)
        维度2: 频率突发 (frequency_burst)
        维度3: 时间异常 (time_anomaly)
        维度4: 目标异常 (target_anomaly)
        维度5: 累计异常 (cumulative_anomaly)

        总分 = Σ(维度得分 × 权重)，范围 [0, 1]
        """
        scores: Dict[str, float] = {}

        # 维度1: 单次金额偏差 — 与历史均值的标准差倍数
        scores["amount_deviation"] = self._score_amount_deviation(profile, amount)

        # 维度2: 频率突发 — 近10分钟消费次数归一化
        scores["frequency_burst"] = self._score_frequency_burst(profile)

        # 维度3: 时间异常 — 凌晨(0-6时)消费
        scores["time_anomaly"] = self._score_time_anomaly()

        # 维度4: 目标异常 — 新的 skill_id 是否首次出现
        scores["target_anomaly"] = self._score_target_anomaly(profile, skill_id)

        # 维度5: 累计异常 — 近1小时累计消费
        scores["cumulative_anomaly"] = self._score_cumulative_anomaly(profile, amount)

        # 加权总分
        total_score = sum(
            scores.get(dim, 0.0) * weight
            for dim, weight in ANOMALY_WEIGHTS.items()
        )

        total_score = min(1.0, max(0.0, total_score))

        if total_score > 0.5:
            logger.warning(
                "异常评分较高: member_id=%s, score=%.3f, details=%s, amount=%d",
                profile.member_id, total_score,
                {k: f"{v:.2f}" for k, v in scores.items()}, amount,
            )

        return total_score

    def _score_amount_deviation(
        self, profile: MemberRiskProfile, amount: int
    ) -> float:
        """
        维度1: 单次金额偏差评分

        与历史均值比较，偏差越大评分越高。
        无历史数据时返回0。
        """
        if profile.total_count < 3 or profile.std_consumption == 0:
            return 0.0

        deviation = abs(amount - profile.avg_consumption) / profile.std_consumption
        # 3σ 以上为高分
        score = min(1.0, deviation / 3.0)
        return score

    def _score_frequency_burst(self, profile: MemberRiskProfile) -> float:
        """
        维度2: 频率突发评分

        10分钟内消费次数归一化到 [0, 1]。
        """
        now = datetime.now()
        window_start = now - timedelta(seconds=FREQUENCY_WINDOW_SECONDS)
        recent_count = sum(
            1 for evt in profile.recent_consumptions
            if evt.timestamp >= window_start
        )
        # 次数 / 最大次数 → 归一化
        score = min(1.0, recent_count / FREQUENCY_MAX_COUNT)
        return score

    def _score_time_anomaly(self) -> float:
        """
        维度3: 时间异常评分

        凌晨时段(0:00-6:00)消费视为异常。
        """
        hour = datetime.now().hour
        if 0 <= hour < 6:
            return 0.8  # 凌晨消费，高分
        elif 6 <= hour < 8:
            return 0.3  # 早间，轻微异常
        return 0.0  # 正常时段

    def _score_target_anomaly(
        self, profile: MemberRiskProfile, skill_id: str
    ) -> float:
        """
        维度4: 目标异常评分

        消费的 skill 是否在历史消费中出现过。
        首次出现的 skill 视为轻微异常。
        """
        if not skill_id or not profile.recent_consumptions:
            return 0.0

        seen_skills = {evt.skill_id for evt in profile.recent_consumptions}
        if skill_id not in seen_skills:
            return 0.5  # 新目标，中等评分
        return 0.0

    def _score_cumulative_anomaly(
        self, profile: MemberRiskProfile, amount: int
    ) -> float:
        """
        维度5: 累计异常评分

        近1小时累计消费金额与日限额的比例。
        """
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)

        recent_total = sum(
            evt.amount for evt in profile.recent_consumptions
            if evt.timestamp >= one_hour_ago
        )
        recent_total += amount  # 加上本次

        daily_limit = DAILY_LIMITS.get(profile.level, 100)
        # 累计占日限额的比例
        ratio = recent_total / daily_limit
        # 超过50%开始评分，超过100%满分
        if ratio <= 0.5:
            return 0.0
        score = min(1.0, (ratio - 0.5) / 0.5)
        return score

    def _update_stats(self, profile: MemberRiskProfile) -> None:
        """更新历史统计（均值、标准差）"""
        amounts = [evt.amount for evt in profile.recent_consumptions]
        n = len(amounts)
        if n == 0:
            return

        profile.total_count = n
        profile.avg_consumption = sum(amounts) / n

        if n >= 2:
            variance = sum(
                (a - profile.avg_consumption) ** 2 for a in amounts
            ) / (n - 1)
            profile.std_consumption = math.sqrt(variance)
        else:
            profile.std_consumption = 0.0

    def _cleanup_history(self, profile: MemberRiskProfile) -> None:
        """清理过期的消费历史记录"""
        # 只保留最近 N 条
        if len(profile.recent_consumptions) > self._max_history:
            profile.recent_consumptions = profile.recent_consumptions[-self._max_history:]

        # 清理7天前的日消费记录
        cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        expired_keys = [
            k for k in profile.daily_consumed if k < cutoff
        ]
        for k in expired_keys:
            del profile.daily_consumed[k]

    async def _freeze_account(
        self, profile: MemberRiskProfile, reason: str
    ) -> None:
        """冻结账户"""
        profile.is_frozen = True
        profile.frozen_reason = reason
        profile.frozen_at = datetime.now()

        logger.warning(
            "账户冻结: member_id=%s, reason=%s",
            profile.member_id, reason,
        )

        if self._on_freeze_account:
            try:
                await self._on_freeze_account(profile.member_id, reason)
            except Exception as e:
                logger.error("冻结回调执行失败: %s", e)

    async def unfreeze_account(self, member_id: str) -> bool:
        """
        解冻账户

        Args:
            member_id: 会员ID

        Returns:
            是否成功解冻
        """
        profile = self._profiles.get(member_id)
        if not profile or not profile.is_frozen:
            return False

        profile.is_frozen = False
        profile.frozen_reason = ""
        profile.frozen_at = None

        logger.info("账户解冻: member_id=%s", member_id)
        return True

    def get_profile(self, member_id: str) -> Optional[MemberRiskProfile]:
        """查询会员风控画像"""
        return self._profiles.get(member_id)

    def is_frozen(self, member_id: str) -> bool:
        """检查账户是否被冻结"""
        profile = self._profiles.get(member_id)
        return profile.is_frozen if profile else False
