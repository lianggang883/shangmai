"""
行动力计费引擎 — 统一入口

整合所有子模块:
  - ConsumptionPriorityEngine: 消费优先级（月免费 > 购买 > 赠送）
  - BudgetFSM: 预算确认状态机
  - ReferralEngine: 引荐分成引擎
  - RiskEngine: 风控规则引擎

对外提供 ActionPowerEngine 类，封装完整消费流程。
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.config import MONTHLY_FREE_AP_MAP, settings
from app.services.billing.budget_fsm import (
    BUDGET_THRESHOLD,
    BudgetFSM,
    BudgetSession,
    BudgetState,
)
from app.services.billing.consumption_priority import (
    ActionPowerPool,
    ConsumptionPriorityEngine,
    MemberAccount,
)
from app.services.billing.referral_engine import (
    REFERRAL_DEFAULT_RATE,
    REFERRAL_MAX_RATE,
    ReferralEngine,
    ReferralSettlement,
)
from app.services.billing.risk_engine import (
    DAILY_LIMITS,
    SINGLE_CONSUME_LIMIT,
    RiskEngine,
    RiskCheckResult,
)

logger = logging.getLogger(__name__)


class ActionPowerEngine:
    """
    行动力计费引擎 — 整合所有子模块的统一入口

    完整消费流程:
      1. 风控检查 (RiskEngine.check_before_consume)
      2. 预算评估 (BudgetFSM.handle_estimate)
      3. 用户确认（大额消费时）
      4. 冻结行动力 (ConsumptionPriorityEngine.freeze)
      5. 执行技能
      6. 结算消费 (ConsumptionPriorityEngine.settle_frozen)
      7. 引荐分成 (ReferralEngine.settle_referral)

    对账功能:
      reconcile_accounts() — 定期比对账户余额与交易记录
    """

    def __init__(self) -> None:
        """初始化计费引擎及所有子模块"""
        self.priority_engine = ConsumptionPriorityEngine()
        self.budget_fsm = BudgetFSM(
            on_notify=self._on_budget_notify,
            on_freeze=self._on_budget_freeze,
            on_unfreeze=self._on_budget_unfreeze,
        )
        self.referral_engine = ReferralEngine()
        self.referral_engine.set_credit_callback(self._on_referral_credit)
        self.risk_engine = RiskEngine()
        self.risk_engine.set_freeze_callback(self._on_risk_freeze)

        # 交易记录（生产环境用数据库）
        self._transactions: list[dict] = []

        # 通知推送回调（外部注入）
        self._push_notify: Optional[callable] = None

    def set_push_notify(self, callback: callable) -> None:
        """
        设置消息推送回调

        Args:
            callback: 异步回调 (member_id: str, title: str, body: str) -> Coroutine
        """
        self._push_notify = callback

    # ====================================================================
    # 完整消费流程
    # ====================================================================

    async def process_skill_consumption(
        self,
        member_id: str,
        estimated_amount: int,
        skill_id: str = "",
        level: int = 1,
    ) -> Dict[str, Any]:
        """
        处理技能消费 — 完整流程入口

        流程:
          1. 风控检查
          2. 预算评估（大额需确认）
          3. 冻结行动力
          4. 返回会话信息（前端展示确认对话框或直接执行）

        Args:
            member_id: 会员ID
            estimated_amount: 预估消费量
            skill_id: 技能ID
            level: 会员等级

        Returns:
            {
                "success": bool,
                "session_id": str,
                "state": str,
                "requires_confirm": bool,
                "estimated_amount": int,
                "message": str,
                ...
            }
        """
        # Step 1: 风控检查
        risk_result = await self.risk_engine.check_before_consume(
            member_id=member_id,
            amount=estimated_amount,
            skill_id=skill_id,
            level=level,
        )

        if not risk_result.allowed:
            return {
                "success": False,
                "session_id": "",
                "state": "REJECTED",
                "requires_confirm": False,
                "estimated_amount": estimated_amount,
                "message": risk_result.reason,
                "risk_info": {
                    "anomaly_score": risk_result.anomaly_score,
                    "triggered_rules": risk_result.triggered_rules,
                    "is_frozen": risk_result.is_frozen,
                },
            }

        # Step 2: 检查余额是否足够
        balance = await self.priority_engine.get_balance(member_id)
        if balance < estimated_amount:
            return {
                "success": False,
                "session_id": "",
                "state": "INSUFFICIENT",
                "requires_confirm": False,
                "estimated_amount": estimated_amount,
                "message": f"行动力不足: 可用{balance}, 需要{estimated_amount}",
            }

        # Step 3: 预算评估
        session = await self.budget_fsm.handle_estimate(
            member_id=member_id,
            skill_id=skill_id,
            estimated_amount=estimated_amount,
        )

        requires_confirm = session.state == BudgetState.ESTIMATED

        result: Dict[str, Any] = {
            "success": True,
            "session_id": session.session_id,
            "state": session.state.value,
            "requires_confirm": requires_confirm,
            "estimated_amount": estimated_amount,
            "message": "等待用户确认" if requires_confirm else "行动力已冻结，可执行技能",
        }

        if requires_confirm:
            result["confirm_timeout"] = 300  # 5分钟
        else:
            # 小额消费已自动冻结，记录交易
            self._record_transaction(
                member_id=member_id,
                tx_type="FREEZE",
                amount=estimated_amount,
                trigger_scene="skill_pre_deduct",
                skill_id=skill_id,
                session_id=session.session_id,
            )

        return result

    async def confirm_consumption(
        self,
        session_id: str,
        confirmed: bool = True,
    ) -> Dict[str, Any]:
        """
        用户确认/拒绝消费

        Args:
            session_id: 会话ID
            confirmed: True=确认, False=拒绝

        Returns:
            确认结果
        """
        session = await self.budget_fsm.handle_confirm(session_id, confirmed)

        if confirmed and session.state == BudgetState.CONFIRMED:
            # 确认成功，记录冻结交易
            self._record_transaction(
                member_id=session.member_id,
                tx_type="FREEZE",
                amount=session.estimated_amount,
                trigger_scene="skill_pre_deduct_confirmed",
                skill_id=session.skill_id,
                session_id=session.session_id,
            )

        return {
            "success": confirmed,
            "session_id": session.session_id,
            "state": session.state.value,
            "message": "确认成功，行动力已冻结" if confirmed else "用户已拒绝消费",
        }

    async def settle_consumption(
        self,
        session_id: str,
        actual_amount: int,
    ) -> Dict[str, Any]:
        """
        结算消费 — 技能执行完成后调用

        Args:
            session_id: 会话ID
            actual_amount: 实际消耗量

        Returns:
            结算结果
        """
        session = await self.budget_fsm.handle_settle(session_id, actual_amount)

        # 结算冻结的行动力
        success, remaining, msg = await self.priority_engine.settle_frozen(
            member_id=session.member_id,
            actual_cost=actual_amount,
        )

        # 记录消费交易
        self._record_transaction(
            member_id=session.member_id,
            tx_type="CONSUME",
            amount=actual_amount,
            trigger_scene="skill_settle",
            skill_id=session.skill_id,
            session_id=session.session_id,
        )

        # 处理引荐分成
        referral_result = await self.referral_engine.settle_referral(
            referee_id=session.member_id,
            consumption=actual_amount,
        )

        result: Dict[str, Any] = {
            "success": success,
            "session_id": session.session_id,
            "state": session.state.value,
            "actual_amount": actual_amount,
            "remaining_balance": remaining,
            "message": msg,
        }

        if referral_result:
            result["referral"] = {
                "referrer_id": referral_result.referrer_id,
                "settled_amount": referral_result.settled_amount,
            }

        return result

    async def cancel_consumption(
        self,
        session_id: str,
        reason: str = "手动取消",
    ) -> Dict[str, Any]:
        """
        取消消费 — 退还冻结的行动力

        Args:
            session_id: 会话ID
            reason: 取消原因

        Returns:
            取消结果
        """
        session = await self.budget_fsm.handle_cancel(session_id, reason)

        # 退还冻结的行动力
        if session.estimated_amount > 0:
            await self.priority_engine.unfreeze(
                member_id=session.member_id,
                amount=session.estimated_amount,
            )

        self._record_transaction(
            member_id=session.member_id,
            tx_type="REFUND",
            amount=session.estimated_amount,
            trigger_scene=reason,
            skill_id=session.skill_id,
            session_id=session.session_id,
        )

        return {
            "success": True,
            "session_id": session.session_id,
            "state": session.state.value,
            "refunded": session.estimated_amount,
            "message": f"消费已取消，已退还{session.estimated_amount}行动力",
        }

    # ====================================================================
    # 充值与赠予
    # ====================================================================

    async def recharge(
        self,
        member_id: str,
        amount: int,
        pool_type: str = "purchased",
    ) -> Dict[str, Any]:
        """
        充值行动力

        Args:
            member_id: 会员ID
            amount: 充值数量
            pool_type: 资金池类型 (purchased/gifted)

        Returns:
            充值结果
        """
        success, balance, msg = await self.priority_engine.add_balance(
            member_id=member_id, amount=amount, pool_type=pool_type
        )

        if success:
            self._record_transaction(
                member_id=member_id,
                tx_type="RECHARGE",
                amount=amount,
                trigger_scene=f"recharge_{pool_type}",
            )

        return {
            "success": success,
            "recharged": amount if success else 0,
            "balance": balance,
            "message": msg,
        }

    async def gift(
        self,
        from_member_id: str,
        to_member_id: str,
        amount: int,
    ) -> Dict[str, Any]:
        """
        赠予行动力

        Args:
            from_member_id: 赠予者ID
            to_member_id: 接收者ID
            amount: 赠予数量

        Returns:
            赠予结果
        """
        # 先扣赠予者
        success_from, remaining_from, msg_from = await self.priority_engine.consume(
            member_id=from_member_id, amount=amount
        )

        if not success_from:
            return {"success": False, "message": msg_from}

        # 再加接收者（入 gifted 池）
        success_to, balance_to, msg_to = await self.priority_engine.add_balance(
            member_id=to_member_id, amount=amount, pool_type="gifted"
        )

        if not success_to:
            # 接收失败，退还赠予者
            await self.priority_engine.add_balance(
                member_id=from_member_id, amount=amount, pool_type="purchased"
            )
            return {"success": False, "message": msg_to}

        # 记录双方交易
        self._record_transaction(
            member_id=from_member_id,
            tx_type="GIFT",
            amount=-amount,
            trigger_scene="gift_send",
            related_member_id=to_member_id,
        )
        self._record_transaction(
            member_id=to_member_id,
            tx_type="GIFT",
            amount=amount,
            trigger_scene="gift_receive",
            related_member_id=from_member_id,
        )

        return {"success": True, "gifted": amount}

    # ====================================================================
    # 月度重置
    # ====================================================================

    async def monthly_reset(
        self, member_id: str, level: int
    ) -> Dict[str, Any]:
        """
        月度免费额度重置

        Args:
            member_id: 会员ID
            level: 会员等级

        Returns:
            重置结果
        """
        monthly_free = MONTHLY_FREE_AP_MAP.get(level, 50)
        success, balance, msg = await self.priority_engine.reset_monthly_free(
            member_id=member_id, monthly_free=monthly_free
        )

        if success:
            self._record_transaction(
                member_id=member_id,
                tx_type="MONTHLY_RESET",
                amount=monthly_free,
                trigger_scene="monthly_reset",
            )

        return {
            "success": success,
            "monthly_free": monthly_free,
            "balance": balance,
            "message": msg,
        }

    # ====================================================================
    # 查询
    # ====================================================================

    async def get_balance(self, member_id: str) -> int:
        """查询行动力可用余额"""
        return await self.priority_engine.get_balance(member_id)

    async def get_account_detail(self, member_id: str) -> Optional[Dict[str, Any]]:
        """查询会员账户详情"""
        account = await self.priority_engine.get_account_detail(member_id)
        if not account:
            return None

        return {
            "member_id": account.member_id,
            "level": account.level,
            "balance": account.balance,
            "total_balance": account.total_balance,
            "pools": {
                name: {
                    "pool_type": pool.pool_type,
                    "total": pool.total,
                    "consumed": pool.consumed,
                    "frozen": pool.frozen,
                    "available": pool.available,
                }
                for name, pool in account.pools.items()
            },
        }

    async def get_transactions(
        self, member_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """查询交易记录"""
        member_txs = [
            tx for tx in self._transactions
            if tx["member_id"] == member_id
        ]
        return member_txs[-limit:]

    # ====================================================================
    # 引荐关系管理
    # ====================================================================

    def register_referral(
        self,
        referrer_id: str,
        referee_id: str,
        rate: float = REFERRAL_DEFAULT_RATE,
    ) -> Dict[str, Any]:
        """
        注册引荐关系

        Args:
            referrer_id: 引荐人ID
            referee_id: 被引荐人ID
            rate: 分成费率

        Returns:
            注册结果
        """
        try:
            record = self.referral_engine.register_referral(
                referrer_id=referrer_id, referee_id=referee_id, rate=rate
            )
            return {
                "success": True,
                "referrer_id": record.referrer_id,
                "referee_id": record.referee_id,
                "rate": record.rate,
            }
        except ValueError as e:
            return {"success": False, "message": str(e)}

    # ====================================================================
    # 风控管理
    # ====================================================================

    async def unfreeze_account(self, member_id: str) -> bool:
        """解冻被风控冻结的账户"""
        return await self.risk_engine.unfreeze_account(member_id)

    def is_account_frozen(self, member_id: str) -> bool:
        """检查账户是否被冻结"""
        return self.risk_engine.is_frozen(member_id)

    # ====================================================================
    # 对账功能
    # ====================================================================

    async def reconcile_accounts(self) -> Dict[str, Any]:
        """
        对账 — 定期比对账户余额与交易记录

        检查:
          1. 每个会员的余额 = Σ充值 + Σ赠予 - Σ消费 - Σ冻结
          2. 交易记录完整性
          3. 引荐分成总额与入账记录

        Returns:
            对账结果
        """
        discrepancies: list[dict] = []
        total_accounts = 0
        matched_accounts = 0

        # 获取所有账户
        all_accounts = self.priority_engine._accounts

        for member_id, account in all_accounts.items():
            total_accounts += 1

            # 根据交易记录计算期望余额
            member_txs = [
                tx for tx in self._transactions if tx["member_id"] == member_id
            ]

            expected_balance = 0
            for tx in member_txs:
                amount = tx["amount"]
                tx_type = tx["tx_type"]
                if tx_type in ("RECHARGE", "GIFT", "REFUND", "MONTHLY_RESET"):
                    expected_balance += abs(amount)
                elif tx_type in ("CONSUME", "FREEZE"):
                    expected_balance -= abs(amount)
                elif tx_type == "UNFREEZE":
                    expected_balance += abs(amount)

            actual_balance = account.balance

            if actual_balance != expected_balance:
                discrepancies.append({
                    "member_id": member_id,
                    "expected_balance": expected_balance,
                    "actual_balance": actual_balance,
                    "difference": actual_balance - expected_balance,
                })
                logger.warning(
                    "对账差异: member_id=%s, expected=%d, actual=%d, diff=%d",
                    member_id, expected_balance, actual_balance,
                    actual_balance - expected_balance,
                )
            else:
                matched_accounts += 1

        result = {
            "total_accounts": total_accounts,
            "matched_accounts": matched_accounts,
            "discrepancy_count": len(discrepancies),
            "discrepancies": discrepancies,
            "reconciled_at": datetime.now().isoformat(),
        }

        if discrepancies:
            logger.error(
                "对账完成: %d/%d 账户匹配，%d 个差异",
                matched_accounts, total_accounts, len(discrepancies),
            )
        else:
            logger.info(
                "对账完成: %d/%d 账户全部匹配",
                matched_accounts, total_accounts,
            )

        return result

    # ====================================================================
    # 内部回调
    # ====================================================================

    async def _on_budget_notify(
        self, member_id: str, skill_id: str, estimated_amount: int
    ) -> None:
        """预算确认通知回调"""
        if self._push_notify:
            try:
                await self._push_notify(
                    member_id,
                    "行动力消费确认",
                    f"即将消耗{estimated_amount}行动力执行技能，请确认",
                )
            except Exception as e:
                logger.error("推送确认通知失败: %s", e)

    async def _on_budget_freeze(
        self, member_id: str, amount: int
    ) -> bool:
        """预算确认冻结回调"""
        success, _, _ = await self.priority_engine.freeze(member_id, amount)
        return success

    async def _on_budget_unfreeze(
        self, member_id: str, amount: int
    ) -> bool:
        """预算确认解冻回调"""
        success, _, _ = await self.priority_engine.unfreeze(member_id, amount)
        return success

    async def _on_referral_credit(
        self, referrer_id: str, amount: int
    ) -> None:
        """引荐分成入账回调"""
        success, _, _ = await self.priority_engine.add_balance(
            member_id=referrer_id, amount=amount, pool_type="gifted"
        )
        if success:
            self._record_transaction(
                member_id=referrer_id,
                tx_type="REFERRAL_INCOME",
                amount=amount,
                trigger_scene="referral_settlement",
            )
            logger.info("引荐分成入账: referrer=%s, amount=%d", referrer_id, amount)

    async def _on_risk_freeze(self, member_id: str, reason: str) -> None:
        """风控冻结回调"""
        logger.warning("风控冻结账户: member_id=%s, reason=%s", member_id, reason)
        if self._push_notify:
            try:
                await self._push_notify(
                    member_id,
                    "账户安全提醒",
                    f"您的账户因异常行为已被临时冻结: {reason}",
                )
            except Exception as e:
                logger.error("推送风控通知失败: %s", e)

    def _record_transaction(self, **kwargs: Any) -> dict:
        """记录交易"""
        tx = {
            "id": str(uuid.uuid4()),
            "created_at": datetime.now().isoformat(),
            **kwargs,
        }
        self._transactions.append(tx)
        return tx
