"""
商脉系统 — 行动力计费引擎 (兼容层)

本模块保留全局单例 billing_service，对上层接口兼容。
底层实现已迁移至 app.services.billing 包的 ActionPowerEngine。

迁移说明:
  - 旧接口 (pre_deduct/settle/refund/recharge/gift) 仍然可用
  - 新接口 (process_skill_consumption/confirm_consumption/settle_consumption)
    提供完整的预算确认流程
  - 推荐使用新接口以获得风控、预算确认、引荐分成的完整能力

参考技术规格样板 Chapter 7
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from app.config import MONTHLY_FREE_AP_MAP, settings
from app.services.billing import ActionPowerEngine

logger = logging.getLogger(__name__)


class BillingService:
    """
    行动力计费引擎 — 兼容层

    保留旧接口兼容性，底层委托给 ActionPowerEngine。
    新代码建议直接使用 ActionPowerEngine。
    """

    # 旧接口常量保留
    DAILY_CONSUME_LIMIT: int = 500
    BIG_BUDGET_THRESHOLD: int = settings.ACTION_POWER_BIG_BUDGET_THRESHOLD

    def __init__(self) -> None:
        """初始化计费引擎，创建底层 ActionPowerEngine 实例"""
        self._engine = ActionPowerEngine()

    @property
    def engine(self) -> ActionPowerEngine:
        """获取底层 ActionPowerEngine 实例，用于新接口调用"""
        return self._engine

    # ==================================================================
    # 旧接口兼容
    # ==================================================================

    async def get_or_create_account(
        self, member_id: str, level: int = 1
    ) -> Dict[str, Any]:
        """
        获取或创建行动力账户（兼容旧接口）

        Args:
            member_id: 会员ID
            level: 会员等级

        Returns:
            账户信息字典
        """
        monthly_free = MONTHLY_FREE_AP_MAP.get(level, 50)
        account = await self._engine.priority_engine.get_or_create_account(
            member_id=member_id, level=level, monthly_free=monthly_free
        )
        return {
            "member_id": account.member_id,
            "balance": account.balance,
            "total_recharged": account.pools["purchased"].total,
            "total_consumed": sum(p.consumed for p in account.pools.values()),
            "total_gifted": account.pools["gifted"].total,
            "monthly_free": account.pools["free"].total,
            "level": account.level,
            "current_month_reset_at": account.updated_at.isoformat(),
        }

    async def get_balance(self, member_id: str) -> int:
        """
        查询行动力余额

        Args:
            member_id: 会员ID

        Returns:
            可用余额
        """
        return await self._engine.get_balance(member_id)

    async def pre_deduct(
        self, member_id: str, amount: int
    ) -> Dict[str, Any]:
        """
        预扣 — SKILL调用前冻结行动力（兼容旧接口）

        新代码建议使用 process_skill_consumption() 代替。

        Args:
            member_id: 会员ID
            amount: 预扣数量

        Returns:
            {"success": bool, "remaining": int, "message": str}
        """
        balance = await self._engine.get_balance(member_id)

        if balance < amount:
            return {
                "success": False,
                "remaining": balance,
                "message": f"行动力不足: 余额{balance}, 需要{amount}",
            }

        # 大额确认检查（兼容旧阈值）
        if amount >= self.BIG_BUDGET_THRESHOLD:
            return {
                "success": False,
                "remaining": balance,
                "message": f"大额消耗({amount}点)，需要用户确认",
                "requires_confirm": True,
            }

        # 冻结行动力
        success, remaining, msg = await self._engine.priority_engine.freeze(
            member_id=member_id, amount=amount
        )

        if success:
            self._engine._record_transaction(
                member_id=member_id,
                tx_type="FREEZE",
                amount=amount,
                trigger_scene="skill_pre_deduct",
            )

        return {
            "success": success,
            "remaining": remaining,
            "message": "预扣成功" if success else msg,
        }

    async def settle(
        self,
        member_id: str,
        actual_cost: int,
        skill_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        结算 — 按实际消耗确认（兼容旧接口）

        新代码建议使用 settle_consumption() 代替。

        Args:
            member_id: 会员ID
            actual_cost: 实际消耗
            skill_id: 技能ID

        Returns:
            结算结果
        """
        success, remaining, msg = await self._engine.priority_engine.settle_frozen(
            member_id=member_id, actual_cost=actual_cost
        )

        if success:
            self._engine._record_transaction(
                member_id=member_id,
                tx_type="CONSUME",
                amount=actual_cost,
                trigger_scene="skill_settle",
                skill_id=skill_id,
            )

            # 处理引荐分成
            await self._engine.referral_engine.settle_referral(
                referee_id=member_id, consumption=actual_cost
            )

        return {
            "success": success,
            "consumed": actual_cost,
            "remaining": remaining,
            "message": msg,
        }

    async def refund(
        self, member_id: str, amount: int, reason: str = "execution_failed"
    ) -> Dict[str, Any]:
        """
        退款 — SKILL执行失败时退还预扣的行动力（兼容旧接口）

        Args:
            member_id: 会员ID
            amount: 退款数量
            reason: 退款原因

        Returns:
            退款结果
        """
        success, remaining, msg = await self._engine.priority_engine.unfreeze(
            member_id=member_id, amount=amount
        )

        if success:
            self._engine._record_transaction(
                member_id=member_id,
                tx_type="REFUND",
                amount=amount,
                trigger_scene=reason,
            )

        return {
            "success": success,
            "refunded": amount if success else 0,
            "remaining": remaining,
            "message": msg,
        }

    async def recharge(
        self,
        member_id: str,
        amount: int,
        payment_method: str = "wechat",
    ) -> Dict[str, Any]:
        """
        充值（兼容旧接口）

        Args:
            member_id: 会员ID
            amount: 充值数量
            payment_method: 支付方式

        Returns:
            充值结果
        """
        result = await self._engine.recharge(
            member_id=member_id, amount=amount, pool_type="purchased"
        )
        return result

    async def gift(
        self,
        from_member_id: str,
        to_member_id: str,
        amount: int,
    ) -> Dict[str, Any]:
        """
        赠予行动力（兼容旧接口）

        Args:
            from_member_id: 赠予者ID
            to_member_id: 接收者ID
            amount: 赠予数量

        Returns:
            赠予结果
        """
        return await self._engine.gift(
            from_member_id=from_member_id,
            to_member_id=to_member_id,
            amount=amount,
        )

    async def monthly_reset(
        self, member_id: str, level: int
    ) -> Dict[str, Any]:
        """
        月度免费额度重置（兼容旧接口）

        Args:
            member_id: 会员ID
            level: 会员等级

        Returns:
            重置结果
        """
        return await self._engine.monthly_reset(member_id=member_id, level=level)

    async def check_daily_limit(
        self, member_id: str, additional: int = 0
    ) -> bool:
        """
        检查日限额（兼容旧接口）

        Args:
            member_id: 会员ID
            additional: 附加消费

        Returns:
            是否在限额内
        """
        today = str(date.today())
        daily = self._engine.risk_engine._profiles.get(member_id)
        if not daily:
            return True
        consumed = daily.daily_consumed.get(today, 0)
        limit = self.DAILY_CONSUME_LIMIT
        return (consumed + additional) <= limit

    async def get_transactions(
        self, member_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        查询交易记录（兼容旧接口）

        Args:
            member_id: 会员ID
            limit: 返回条数

        Returns:
            交易记录列表
        """
        return await self._engine.get_transactions(member_id, limit)


# 全局单例 — 保持与旧代码的兼容
billing_service = BillingService()
