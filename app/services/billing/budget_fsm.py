"""
预算确认状态机 — 技术规格 7.2

状态流转:
  IDLE → ESTIMATED → FROZEN → CONFIRMED → SETTLED
                                       ↘ CANCELLED
  ESTIMATED → CANCELLED (超时/用户拒绝)
  CONFIRMED → PARTIAL_REFUND (部分退款)

关键参数:
  BUDGET_THRESHOLD = 30  — 单次消费大于30行动力触发确认
  CONFIRM_TIMEOUT = 300  — 5分钟超时自动取消

大额消费时: 进入 ESTIMATED → 推送确认通知 → 启动超时 watcher
用户确认后: ESTIMATED → FROZEN → CONFIRMED（冻结行动力）
用户拒绝:   ESTIMATED → CANCELLED
超时未确认: ESTIMATED → CANCELLED（自动）
"""
from __future__ import annotations

import asyncio
import enum
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Coroutine, Dict, Optional

logger = logging.getLogger(__name__)


class BudgetState(str, enum.Enum):
    """预算状态枚举"""
    IDLE = "IDLE"                     # 初始空闲
    ESTIMATED = "ESTIMATED"           # 已评估，等待用户确认
    FROZEN = "FROZEN"                 # 行动力已冻结
    CONFIRMED = "CONFIRMED"           # 用户已确认
    SETTLED = "SETTLED"               # 已结算
    CANCELLED = "CANCELLED"           # 已取消（超时/拒绝）
    PARTIAL_REFUND = "PARTIAL_REFUND" # 部分退款


# 单次消费大于此值触发预算确认流程
BUDGET_THRESHOLD: int = 30
# 确认超时时间（秒），超时自动取消
CONFIRM_TIMEOUT: int = 300


@dataclass
class BudgetSession:
    """预算确认会话 — 记录一次消费的预算确认全过程"""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    member_id: str = ""
    skill_id: str = ""
    estimated_amount: int = 0
    actual_amount: int = 0
    state: BudgetState = BudgetState.IDLE
    created_at: datetime = field(default_factory=datetime.now)
    confirmed_at: Optional[datetime] = None
    settled_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancel_reason: str = ""
    _timeout_task: Optional[asyncio.Task] = field(
        default=None, repr=False, compare=False
    )

    @property
    def is_terminal(self) -> bool:
        """是否处于终态"""
        return self.state in (
            BudgetState.SETTLED,
            BudgetState.CANCELLED,
            BudgetState.PARTIAL_REFUND,
        )


class BudgetFSM:
    """
    预算确认状态机

    管理大额行动力消费的确认流程:
    1. 评估预算 → 是否需要用户确认
    2. 需要确认 → 进入 ESTIMATED，推送通知，启动超时
    3. 用户确认 → 冻结行动力，进入 CONFIRMED
    4. 用户拒绝/超时 → CANCELLED
    5. 实际结算 → SETTLED / PARTIAL_REFUND
    """

    def __init__(
        self,
        on_notify: Optional[
            Callable[[str, str, int], Coroutine[None, None, None]]
        ] = None,
        on_freeze: Optional[
            Callable[[str, int], Coroutine[None, None, bool]]
        ] = None,
        on_unfreeze: Optional[
            Callable[[str, int], Coroutine[None, None, bool]]
        ] = None,
    ) -> None:
        """
        初始化预算确认状态机

        Args:
            on_notify: 确认通知回调 (member_id, skill_id, estimated_amount)
            on_freeze: 冻结行动力回调 (member_id, amount) → 成功与否
            on_unfreeze: 解冻行动力回调 (member_id, amount) → 成功与否
        """
        self._sessions: Dict[str, BudgetSession] = {}
        self._member_sessions: Dict[str, str] = {}  # member_id → session_id
        self._on_notify = on_notify
        self._on_freeze = on_freeze
        self._on_unfreeze = on_unfreeze

    def get_session(self, session_id: str) -> Optional[BudgetSession]:
        """根据 session_id 获取会话"""
        return self._sessions.get(session_id)

    def get_member_active_session(self, member_id: str) -> Optional[BudgetSession]:
        """获取会员当前的活跃确认会话"""
        sid = self._member_sessions.get(member_id)
        if sid:
            session = self._sessions.get(sid)
            if session and not session.is_terminal:
                return session
        return None

    async def handle_estimate(
        self,
        member_id: str,
        skill_id: str,
        estimated_amount: int,
    ) -> BudgetSession:
        """
        评估预算 — 消费前的入口

        如果 estimated_amount <= BUDGET_THRESHOLD，直接跳过确认，进入 FROZEN。
        如果 estimated_amount > BUDGET_THRESHOLD，进入 ESTIMATED，等待用户确认。

        Args:
            member_id: 会员ID
            skill_id: 技能ID
            estimated_amount: 预估消费量

        Returns:
            预算会话对象
        """
        # 如果该会员已有活跃会话，先取消
        active = self.get_member_active_session(member_id)
        if active:
            await self._cancel_session(active, "新的消费请求，旧会话自动取消")

        session = BudgetSession(
            member_id=member_id,
            skill_id=skill_id,
            estimated_amount=estimated_amount,
            state=BudgetState.IDLE,
        )
        self._sessions[session.session_id] = session
        self._member_sessions[member_id] = session.session_id

        if estimated_amount <= BUDGET_THRESHOLD:
            # 小额消费，无需确认，直接冻结
            session.state = BudgetState.ESTIMATED
            await self._do_freeze(session)
            logger.info(
                "小额消费直接冻结: member_id=%s, amount=%d, session=%s",
                member_id, estimated_amount, session.session_id,
            )
        else:
            # 大额消费，需要用户确认
            session.state = BudgetState.ESTIMATED
            # 推送确认通知
            if self._on_notify:
                try:
                    await self._on_notify(member_id, skill_id, estimated_amount)
                except Exception as e:
                    logger.error("推送确认通知失败: %s", e)

            # 启动超时 watcher
            session._timeout_task = asyncio.create_task(
                self._timeout_watcher(session.session_id)
            )
            logger.info(
                "大额消费等待确认: member_id=%s, amount=%d, session=%s, timeout=%ds",
                member_id, estimated_amount, session.session_id, CONFIRM_TIMEOUT,
            )

        return session

    async def handle_confirm(
        self,
        session_id: str,
        confirmed: bool = True,
    ) -> BudgetSession:
        """
        处理用户确认/拒绝

        Args:
            session_id: 会话ID
            confirmed: True=用户确认, False=用户拒绝

        Returns:
            更新后的会话对象

        Raises:
            ValueError: 会话不存在或状态不允许确认
        """
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"会话不存在: {session_id}")

        if session.state != BudgetState.ESTIMATED:
            raise ValueError(
                f"当前状态不允许确认: state={session.state.value}, session={session_id}"
            )

        # 取消超时 watcher
        if session._timeout_task and not session._timeout_task.done():
            session._timeout_task.cancel()
            try:
                await session._timeout_task
            except asyncio.CancelledError:
                pass

        if confirmed:
            # 用户确认 → 冻结行动力
            await self._do_freeze(session)
            session.confirmed_at = datetime.now()
            logger.info(
                "用户确认消费: member_id=%s, amount=%d, session=%s",
                session.member_id, session.estimated_amount, session_id,
            )
        else:
            # 用户拒绝 → 取消
            await self._cancel_session(session, "用户拒绝")
            logger.info(
                "用户拒绝消费: member_id=%s, amount=%d, session=%s",
                session.member_id, session.estimated_amount, session_id,
            )

        return session

    async def handle_settle(
        self,
        session_id: str,
        actual_amount: int,
    ) -> BudgetSession:
        """
        结算消费

        Args:
            session_id: 会话ID
            actual_amount: 实际消耗量

        Returns:
            更新后的会话对象

        Raises:
            ValueError: 会话不存在或状态不允许结算
        """
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"会话不存在: {session_id}")

        if session.state not in (BudgetState.CONFIRMED, BudgetState.FROZEN):
            raise ValueError(
                f"当前状态不允许结算: state={session.state.value}, session={session_id}"
            )

        session.actual_amount = actual_amount

        if actual_amount < session.estimated_amount:
            # 实际消耗小于预估 → 部分退款
            refund = session.estimated_amount - actual_amount
            if self._on_unfreeze:
                try:
                    await self._on_unfreeze(session.member_id, refund)
                except Exception as e:
                    logger.error("部分退款失败: %s", e)

            session.state = BudgetState.PARTIAL_REFUND
            session.settled_at = datetime.now()
            logger.info(
                "部分退款结算: member_id=%s, estimated=%d, actual=%d, refund=%d",
                session.member_id, session.estimated_amount, actual_amount, refund,
            )
        else:
            # 实际消耗等于预估 → 正常结算
            session.state = BudgetState.SETTLED
            session.settled_at = datetime.now()
            logger.info(
                "正常结算: member_id=%s, actual=%d",
                session.member_id, actual_amount,
            )

        return session

    async def handle_cancel(
        self,
        session_id: str,
        reason: str = "手动取消",
    ) -> BudgetSession:
        """
        手动取消会话

        Args:
            session_id: 会话ID
            reason: 取消原因

        Returns:
            更新后的会话对象
        """
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"会话不存在: {session_id}")

        if session.is_terminal:
            raise ValueError(
                f"终态会话无法取消: state={session.state.value}, session={session_id}"
            )

        # 取消超时 watcher
        if session._timeout_task and not session._timeout_task.done():
            session._timeout_task.cancel()
            try:
                await session._timeout_task
            except asyncio.CancelledError:
                pass

        # 如果已冻结，退还行动力
        if session.state in (BudgetState.FROZEN, BudgetState.CONFIRMED):
            if self._on_unfreeze:
                try:
                    await self._on_unfreeze(session.member_id, session.estimated_amount)
                except Exception as e:
                    logger.error("取消时解冻失败: %s", e)

        await self._cancel_session(session, reason)
        return session

    async def _do_freeze(self, session: BudgetSession) -> None:
        """执行冻结行动力操作"""
        if self._on_freeze:
            try:
                success = await self._on_freeze(
                    session.member_id, session.estimated_amount
                )
                if success:
                    session.state = BudgetState.CONFIRMED
                else:
                    # 冻结失败（余额不足等），取消会话
                    await self._cancel_session(session, "冻结行动力失败（余额不足）")
            except Exception as e:
                logger.error("冻结行动力异常: %s", e)
                await self._cancel_session(session, f"冻结行动力异常: {e}")
        else:
            # 无冻结回调，直接确认
            session.state = BudgetState.CONFIRMED

    async def _cancel_session(self, session: BudgetSession, reason: str) -> None:
        """取消会话"""
        session.state = BudgetState.CANCELLED
        session.cancelled_at = datetime.now()
        session.cancel_reason = reason
        logger.info(
            "会话取消: session=%s, member_id=%s, reason=%s",
            session.session_id, session.member_id, reason,
        )

    async def _timeout_watcher(self, session_id: str) -> None:
        """
        超时 watcher — 等待确认超时后自动取消

        流程:
          1. asyncio.sleep(CONFIRM_TIMEOUT)
          2. 检查会话状态是否仍为 ESTIMATED
          3. 如果是 → 自动取消
        """
        try:
            await asyncio.sleep(CONFIRM_TIMEOUT)

            session = self._sessions.get(session_id)
            if session and session.state == BudgetState.ESTIMATED:
                logger.warning(
                    "确认超时，自动取消: session=%s, member_id=%s, amount=%d",
                    session_id, session.member_id, session.estimated_amount,
                )
                await self._cancel_session(session, f"确认超时({CONFIRM_TIMEOUT}秒)")
        except asyncio.CancelledError:
            # 正常取消（用户在超时前确认了），忽略
            pass

    def cleanup_expired(self, max_age_hours: int = 24) -> int:
        """
        清理过期的终态会话

        Args:
            max_age_hours: 最大保留小时数

        Returns:
            清理的会话数
        """
        now = datetime.now()
        expired_ids: list[str] = []

        for sid, session in self._sessions.items():
            if session.is_terminal:
                age = (now - (session.settled_at or session.cancelled_at or session.created_at)).total_seconds()
                if age > max_age_hours * 3600:
                    expired_ids.append(sid)

        for sid in expired_ids:
            del self._sessions[sid]

        if expired_ids:
            logger.info("清理过期会话: count=%d", len(expired_ids))

        return len(expired_ids)
