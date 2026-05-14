"""
消费优先级模块 — 技术规格 7.1

消费优先级顺序:
  1. 月免费额度（优先消耗）
  2. 购买额度
  3. 赠送充值余额

每次消费按优先级依次扣除，保证各类额度的消耗符合业务规则。
使用 asyncio.Lock 模拟行锁，防止并发消费导致超扣。
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ActionPowerPool:
    """行动力资金池 — 表示某一来源的行动力额度"""
    pool_type: str          # free / purchased / gifted
    total: int = 0          # 总额度
    consumed: int = 0       # 已消耗
    frozen: int = 0         # 冻结中（预扣）

    @property
    def available(self) -> int:
        """可用额度（总额 - 已消耗 - 冻结中）"""
        return max(0, self.total - self.consumed - self.frozen)

    @property
    def remaining_total(self) -> int:
        """剩余总额（总额 - 已消耗）"""
        return max(0, self.total - self.consumed)


@dataclass
class MemberAccount:
    """会员行动力账户 — 包含三类资金池"""
    member_id: str
    level: int = 1
    pools: Dict[str, ActionPowerPool] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """初始化三类资金池"""
        if not self.pools:
            self.pools = {
                "free": ActionPowerPool(pool_type="free"),
                "purchased": ActionPowerPool(pool_type="purchased"),
                "gifted": ActionPowerPool(pool_type="gifted"),
            }

    @property
    def balance(self) -> int:
        """总可用余额"""
        return sum(p.available for p in self.pools.values())

    @property
    def total_balance(self) -> int:
        """总剩余额度（含冻结）"""
        return sum(p.remaining_total for p in self.pools.values())


class ConsumptionPriorityEngine:
    """
    消费优先级引擎

    按优先级扣除行动力: 月免费 > 购买 > 赠送
    使用 asyncio.Lock 模拟行锁，避免并发超扣。
    """

    # 消费优先级顺序
    PRIORITY_ORDER: list[str] = ["free", "purchased", "gifted"]

    def __init__(self) -> None:
        # 会员账户缓存 (生产环境用 Redis + DB)
        self._accounts: Dict[str, MemberAccount] = {}
        # 每会员一把行锁
        self._locks: Dict[str, asyncio.Lock] = {}

    def _get_lock(self, member_id: str) -> asyncio.Lock:
        """获取会员专属行锁"""
        if member_id not in self._locks:
            self._locks[member_id] = asyncio.Lock()
        return self._locks[member_id]

    async def get_or_create_account(
        self, member_id: str, level: int = 1, monthly_free: int = 50
    ) -> MemberAccount:
        """获取或创建会员行动力账户"""
        if member_id not in self._accounts:
            account = MemberAccount(member_id=member_id, level=level)
            account.pools["free"].total = monthly_free
            self._accounts[member_id] = account
            logger.info("创建行动力账户: member_id=%s, level=%d, monthly_free=%d",
                        member_id, level, monthly_free)
        return self._accounts[member_id]

    async def consume(self, member_id: str, amount: int) -> Tuple[bool, int, str]:
        """
        按优先级消费行动力

        Args:
            member_id: 会员ID
            amount: 消费数量

        Returns:
            (成功与否, 剩余余额, 消息)
        """
        if amount <= 0:
            return False, 0, f"消费金额必须大于0，当前: {amount}"

        lock = self._get_lock(member_id)
        async with lock:
            account = await self.get_or_create_account(member_id)

            # 检查总余额
            if account.balance < amount:
                return False, account.balance, (
                    f"行动力不足: 可用余额{account.balance}, 需要{amount}"
                )

            # 按优先级依次扣除
            remaining = amount
            deduction_detail: list[str] = []

            for pool_type in self.PRIORITY_ORDER:
                pool = account.pools[pool_type]
                if remaining <= 0:
                    break
                if pool.available <= 0:
                    continue

                deduct = min(pool.available, remaining)
                pool.consumed += deduct
                remaining -= deduct
                deduction_detail.append(f"{pool_type}:{deduct}")

            if remaining > 0:
                # 理论上不会到这里（前面已检查余额）
                logger.error("消费后仍有余额未扣除: member_id=%s, remaining=%d",
                             member_id, remaining)
                return False, account.balance, "消费异常，请联系管理员"

            account.updated_at = datetime.now()
            logger.info("行动力消费: member_id=%s, amount=%d, 扣除明细=[%s], 余额=%d",
                        member_id, amount, ", ".join(deduction_detail), account.balance)

            return True, account.balance, "消费成功"

    async def freeze(self, member_id: str, amount: int) -> Tuple[bool, int, str]:
        """
        冻结行动力（预扣）— 按优先级冻结

        Args:
            member_id: 会员ID
            amount: 冻结数量

        Returns:
            (成功与否, 剩余可用余额, 消息)
        """
        if amount <= 0:
            return False, 0, f"冻结金额必须大于0，当前: {amount}"

        lock = self._get_lock(member_id)
        async with lock:
            account = await self.get_or_create_account(member_id)

            if account.balance < amount:
                return False, account.balance, (
                    f"行动力不足，无法冻结: 可用余额{account.balance}, 需要{amount}"
                )

            remaining = amount
            for pool_type in self.PRIORITY_ORDER:
                pool = account.pools[pool_type]
                if remaining <= 0:
                    break
                if pool.available <= 0:
                    continue

                freeze_amount = min(pool.available, remaining)
                pool.frozen += freeze_amount
                remaining -= freeze_amount

            if remaining > 0:
                logger.error("冻结后仍有余额未处理: member_id=%s, remaining=%d",
                             member_id, remaining)
                return False, account.balance, "冻结异常"

            account.updated_at = datetime.now()
            logger.info("行动力冻结: member_id=%s, amount=%d, 可用余额=%d",
                        member_id, amount, account.balance)

            return True, account.balance, "冻结成功"

    async def settle_frozen(
        self, member_id: str, actual_cost: int
    ) -> Tuple[bool, int, str]:
        """
        结算冻结的行动力 — 扣除实际消耗，退还多余冻结

        Args:
            member_id: 会员ID
            actual_cost: 实际消耗数量

        Returns:
            (成功与否, 剩余余额, 消息)
        """
        lock = self._get_lock(member_id)
        async with lock:
            account = await self.get_or_create_account(member_id)

            total_frozen = sum(p.frozen for p in account.pools.values())

            if actual_cost > total_frozen:
                logger.warning("实际消耗超过冻结量: member_id=%s, actual=%d, frozen=%d",
                               member_id, actual_cost, total_frozen)
                # 追加扣费从可用余额中扣
                extra = actual_cost - total_frozen
                # 先将所有冻结转为消耗
                for pool_type in self.PRIORITY_ORDER:
                    pool = account.pools[pool_type]
                    pool.consumed += pool.frozen
                    pool.frozen = 0
                # 再从可用余额扣除差额
                remain_extra = extra
                for pool_type in self.PRIORITY_ORDER:
                    pool = account.pools[pool_type]
                    if remain_extra <= 0:
                        break
                    deduct = min(pool.available, remain_extra)
                    pool.consumed += deduct
                    remain_extra -= deduct

                if remain_extra > 0:
                    return False, account.balance, "实际消耗超过可用额度"
            else:
                # 按优先级将冻结转为消耗
                to_consume = actual_cost
                to_unfreeze = total_frozen - actual_cost

                for pool_type in self.PRIORITY_ORDER:
                    pool = account.pools[pool_type]
                    if to_consume <= 0 and to_unfreeze <= 0:
                        break
                    if pool.frozen <= 0:
                        continue

                    consume_from_frozen = min(pool.frozen, to_consume)
                    pool.consumed += consume_from_frozen
                    pool.frozen -= consume_from_frozen
                    to_consume -= consume_from_frozen

                    # 退还多余的冻结
                    unfreeze_from_pool = min(pool.frozen, to_unfreeze)
                    pool.frozen -= unfreeze_from_pool
                    to_unfreeze -= unfreeze_from_pool

            account.updated_at = datetime.now()
            logger.info("冻结结算: member_id=%s, actual_cost=%d, 余额=%d",
                        member_id, actual_cost, account.balance)

            return True, account.balance, "结算成功"

    async def unfreeze(self, member_id: str, amount: int) -> Tuple[bool, int, str]:
        """
        退还冻结的行动力（全部退还）

        Args:
            member_id: 会员ID
            amount: 需要退还的冻结量

        Returns:
            (成功与否, 剩余余额, 消息)
        """
        lock = self._get_lock(member_id)
        async with lock:
            account = await self.get_or_create_account(member_id)

            remaining = amount
            for pool_type in reversed(self.PRIORITY_ORDER):
                pool = account.pools[pool_type]
                if remaining <= 0:
                    break
                unfreeze_amount = min(pool.frozen, remaining)
                pool.frozen -= unfreeze_amount
                remaining -= unfreeze_amount

            account.updated_at = datetime.now()
            logger.info("冻结退还: member_id=%s, amount=%d, 余额=%d",
                        member_id, amount, account.balance)

            return True, account.balance, "退还成功"

    async def add_balance(
        self,
        member_id: str,
        amount: int,
        pool_type: str = "purchased"
    ) -> Tuple[bool, int, str]:
        """
        增加行动力额度

        Args:
            member_id: 会员ID
            amount: 增加数量
            pool_type: 资金池类型 (free/purchased/gifted)

        Returns:
            (成功与否, 新余额, 消息)
        """
        if amount <= 0:
            return False, 0, "增加额度必须大于0"

        lock = self._get_lock(member_id)
        async with lock:
            account = await self.get_or_create_account(member_id)

            if pool_type not in account.pools:
                return False, account.balance, f"未知的资金池类型: {pool_type}"

            account.pools[pool_type].total += amount
            account.updated_at = datetime.now()

            logger.info("增加行动力: member_id=%s, amount=%d, pool=%s, 余额=%d",
                        member_id, amount, pool_type, account.balance)

            return True, account.balance, "充值成功"

    async def reset_monthly_free(
        self, member_id: str, monthly_free: int
    ) -> Tuple[bool, int, str]:
        """
        重置月度免费额度

        Args:
            member_id: 会员ID
            monthly_free: 新的月度免费额度

        Returns:
            (成功与否, 新余额, 消息)
        """
        lock = self._get_lock(member_id)
        async with lock:
            account = await self.get_or_create_account(member_id)

            old_free = account.pools["free"].total
            account.pools["free"].total = monthly_free
            account.pools["free"].consumed = 0
            account.pools["free"].frozen = 0
            account.updated_at = datetime.now()

            logger.info("月度免费额度重置: member_id=%s, old=%d, new=%d",
                        member_id, old_free, monthly_free)

            return True, account.balance, "月度免费额度已重置"

    async def get_balance(self, member_id: str) -> int:
        """查询会员可用余额"""
        account = await self.get_or_create_account(member_id)
        return account.balance

    async def get_account_detail(self, member_id: str) -> Optional[MemberAccount]:
        """查询会员账户详情"""
        return self._accounts.get(member_id)

    async def partial_refund(
        self, member_id: str, amount: int, pool_type: str = "free"
    ) -> Tuple[bool, int, str]:
        """
        部分退款 — 退还到指定资金池

        Args:
            member_id: 会员ID
            amount: 退款数量
            pool_type: 退还到哪个资金池

        Returns:
            (成功与否, 新余额, 消息)
        """
        if amount <= 0:
            return False, 0, "退款金额必须大于0"

        lock = self._get_lock(member_id)
        async with lock:
            account = await self.get_or_create_account(member_id)

            if pool_type not in account.pools:
                return False, account.balance, f"未知的资金池类型: {pool_type}"

            pool = account.pools[pool_type]
            # 退款减少 consumed（相当于归还已消耗的额度）
            actual_refund = min(amount, pool.consumed)
            pool.consumed -= actual_refund
            account.updated_at = datetime.now()

            logger.info("部分退款: member_id=%s, amount=%d, pool=%s, actual_refund=%d",
                        member_id, amount, pool_type, actual_refund)

            return True, account.balance, f"已退还{actual_refund}行动力"
