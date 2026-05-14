"""
引荐分成引擎 — 技术规格 7.3

核心算法:
  每次被引荐者消费时触发分成计算:
    raw_amount = consumption * rate + 历史余数
    settled_amount = floor(raw_amount)  — 取整数部分入账
    new_remainder = raw_amount - settled_amount  — 小数部分累计

  rate 默认 0.10 (10%), 上限 0.30 (30%)
  PendingRemainder 表记录 (referrer_id, referee_id) → remainder

设计要点:
  - 使用 floor 取整避免精度丢失
  - 余数累计保证长期公平（不会因为取整而漏发或少发）
  - 支持动态费率（不同引荐关系可有不同费率）
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# 默认引荐分成费率
REFERRAL_DEFAULT_RATE: float = 0.10
# 引荐分成费率上限
REFERRAL_MAX_RATE: float = 0.30


@dataclass
class PendingRemainder:
    """待结算余数 — 记录每一对(引荐人, 被引荐人)的累计小数部分"""
    referrer_id: str
    referee_id: str
    remainder: float = 0.0
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class ReferralRecord:
    """引荐关系记录"""
    referrer_id: str         # 引荐人ID
    referee_id: str          # 被引荐人ID
    rate: float = REFERRAL_DEFAULT_RATE  # 分成费率
    created_at: datetime = field(default_factory=datetime.now)
    is_active: bool = True   # 引荐关系是否生效


@dataclass
class ReferralSettlement:
    """分成结算结果"""
    referrer_id: str
    referee_id: str
    consumption: int          # 被引荐者本次消费
    rate: float               # 费率
    raw_amount: float         # 原始分成金额(含余数)
    settled_amount: int       # 实际入账整数
    new_remainder: float      # 累计余数
    previous_remainder: float # 之前余数


class ReferralEngine:
    """
    引荐分成引擎

    每次被引荐者消费时调用 settle_referral()，计算引荐人应得分成。
    使用 floor 取整 + 余数累计，保证长期公平。
    """

    def __init__(self) -> None:
        # 引荐关系缓存 (referee_id → ReferralRecord)
        self._referrals: Dict[str, ReferralRecord] = {}
        # 待结算余数 (referrer_id:referee_id → PendingRemainder)
        self._remainders: Dict[str, PendingRemainder] = {}
        # 分成入账回调
        self._on_credit: Optional[
            callable  # (referrer_id, amount) -> Coroutine
        ] = None

    def set_credit_callback(self, callback: callable) -> None:
        """
        设置分成入账回调

        Args:
            callback: 异步回调函数 (referrer_id: str, amount: int) -> Coroutine
        """
        self._on_credit = callback

    def register_referral(
        self,
        referrer_id: str,
        referee_id: str,
        rate: float = REFERRAL_DEFAULT_RATE,
    ) -> ReferralRecord:
        """
        注册引荐关系

        Args:
            referrer_id: 引荐人ID
            referee_id: 被引荐人ID
            rate: 分成费率，默认0.10，上限0.30

        Returns:
            引荐关系记录

        Raises:
            ValueError: 费率超出范围
        """
        if rate <= 0 or rate > REFERRAL_MAX_RATE:
            raise ValueError(
                f"引荐分成费率必须在 (0, {REFERRAL_MAX_RATE}] 范围内，当前: {rate}"
            )

        record = ReferralRecord(
            referrer_id=referrer_id,
            referee_id=referee_id,
            rate=rate,
        )
        self._referrals[referee_id] = record

        logger.info(
            "注册引荐关系: referrer=%s, referee=%s, rate=%.2f",
            referrer_id, referee_id, rate,
        )
        return record

    def get_referral(self, referee_id: str) -> Optional[ReferralRecord]:
        """查询被引荐者的引荐关系"""
        return self._referrals.get(referee_id)

    def _get_remainder_key(self, referrer_id: str, referee_id: str) -> str:
        """生成余数记录的键"""
        return f"{referrer_id}:{referee_id}"

    def _get_or_create_remainder(
        self, referrer_id: str, referee_id: str
    ) -> PendingRemainder:
        """获取或创建余数记录"""
        key = self._get_remainder_key(referrer_id, referee_id)
        if key not in self._remainders:
            self._remainders[key] = PendingRemainder(
                referrer_id=referrer_id,
                referee_id=referee_id,
            )
        return self._remainders[key]

    async def settle_referral(
        self, referee_id: str, consumption: int
    ) -> Optional[ReferralSettlement]:
        """
        结算引荐分成 — 被引荐者消费时调用

        计算流程:
          1. 查找引荐关系，无则跳过
          2. raw_amount = consumption * rate + 历史余数
          3. settled_amount = floor(raw_amount) — 入账整数
          4. new_remainder = raw_amount - settled_amount — 累计小数

        Args:
            referee_id: 被引荐者ID
            consumption: 本次消费量

        Returns:
            结算结果，无引荐关系时返回 None
        """
        if consumption <= 0:
            logger.warning("分成结算跳过: consumption=%d (必须大于0)", consumption)
            return None

        # 查找引荐关系
        record = self._referrals.get(referee_id)
        if not record or not record.is_active:
            return None

        referrer_id = record.referrer_id
        rate = record.rate

        # 获取历史余数
        remainder_rec = self._get_or_create_remainder(referrer_id, referee_id)
        previous_remainder = remainder_rec.remainder

        # 计算分成
        raw_amount = consumption * rate + previous_remainder
        settled_amount = int(raw_amount)  # floor 取整
        new_remainder = raw_amount - settled_amount

        # 更新余数
        remainder_rec.remainder = new_remainder
        remainder_rec.updated_at = datetime.now()

        # 执行入账
        if settled_amount > 0 and self._on_credit:
            try:
                await self._on_credit(referrer_id, settled_amount)
            except Exception as e:
                logger.error("引荐分成入账失败: referrer=%s, amount=%d, error=%s",
                             referrer_id, settled_amount, e)

        result = ReferralSettlement(
            referrer_id=referrer_id,
            referee_id=referee_id,
            consumption=consumption,
            rate=rate,
            raw_amount=raw_amount,
            settled_amount=settled_amount,
            new_remainder=new_remainder,
            previous_remainder=previous_remainder,
        )

        logger.info(
            "引荐分成结算: referrer=%s, referee=%s, consumption=%d, "
            "rate=%.2f, raw=%.4f, settled=%d, remainder=%.4f",
            referrer_id, referee_id, consumption, rate,
            raw_amount, settled_amount, new_remainder,
        )

        return result

    async def settle_referral_batch(
        self, settlements: list[Tuple[str, int]]
    ) -> list[Optional[ReferralSettlement]]:
        """
        批量结算引荐分成

        Args:
            settlements: [(referee_id, consumption), ...] 列表

        Returns:
            结算结果列表
        """
        results: list[Optional[ReferralSettlement]] = []
        for referee_id, consumption in settlements:
            result = await self.settle_referral(referee_id, consumption)
            results.append(result)
        return results

    def get_remainder(self, referrer_id: str, referee_id: str) -> float:
        """查询特定引荐对的累计余数"""
        key = self._get_remainder_key(referrer_id, referee_id)
        remainder = self._remainders.get(key)
        return remainder.remainder if remainder else 0.0

    def get_all_remainders(self, referrer_id: str) -> Dict[str, float]:
        """
        查询引荐人所有余数

        Args:
            referrer_id: 引荐人ID

        Returns:
            {referee_id: remainder} 映射
        """
        result: Dict[str, float] = {}
        for key, rem in self._remainders.items():
            if rem.referrer_id == referrer_id:
                result[rem.referee_id] = rem.remainder
        return result

    def deactivate_referral(self, referee_id: str) -> bool:
        """
        停用引荐关系

        Args:
            referee_id: 被引荐者ID

        Returns:
            是否成功停用
        """
        record = self._referrals.get(referee_id)
        if record and record.is_active:
            record.is_active = False
            logger.info("停用引荐关系: referrer=%s, referee=%s",
                        record.referrer_id, referee_id)
            return True
        return False

    def get_referral_stats(self, referrer_id: str) -> Dict[str, int]:
        """
        获取引荐人的统计信息

        Args:
            referrer_id: 引荐人ID

        Returns:
            统计信息字典
        """
        active_count = 0
        total_remainder = 0.0
        for record in self._referrals.values():
            if record.referrer_id == referrer_id and record.is_active:
                active_count += 1
        for rem in self._remainders.values():
            if rem.referrer_id == referrer_id:
                total_remainder += rem.remainder

        return {
            "active_referees": active_count,
            "pending_remainder": total_remainder,
        }
