"""Billing (action power account) repository."""
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base import BaseRepository
from app.core.exceptions import NotFoundError

if TYPE_CHECKING:
    from app.models.billing import ActionPowerAccount, Transaction


class BillingRepo:
    """Data access for ActionPower account and transactions."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_account(self, member_id: str) -> "ActionPowerAccount | None":
        stmt = select(ActionPowerAccount).where(ActionPowerAccount.member_id == member_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_account_or_raise(self, member_id: str) -> "ActionPowerAccount":
        account = await self.get_account(member_id)
        if account is None:
            raise NotFoundError(f"ActionPowerAccount for member={member_id} not found")
        return account

    async def create_account(self, member_id: str, level: int) -> "ActionPowerAccount":
        from app.models.billing import ActionPowerAccount
        account = ActionPowerAccount(member_id=member_id, level=level)
        self.session.add(account)
        await self.session.flush()
        await self.session.refresh(account)
        return account

    async def update_account(self, member_id: str, **kwargs) -> "ActionPowerAccount | None":
        account = await self.get_account(member_id)
        if account is None:
            return None
        for key, value in kwargs.items():
            if hasattr(account, key):
                setattr(account, key, value)
        await self.session.flush()
        await self.session.refresh(account)
        return account

    async def get_transactions(
        self, account_id: str, tx_type: str | None = None, limit: int = 50
    ) -> list["Transaction"]:
        from app.models.billing import Transaction
        stmt = select(Transaction).where(Transaction.account_id == account_id)
        if tx_type:
            stmt = stmt.where(Transaction.type == tx_type)
        stmt = stmt.order_by(Transaction.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def record_transaction(
        self,
        account_id: str,
        tx_type: str,
        amount: int,
        balance_after: int,
        description: str,
        ref_id: str | None = None,
    ) -> "Transaction":
        from app.models.billing import Transaction
        tx = Transaction(
            account_id=account_id,
            type=tx_type,
            amount=amount,
            balance_after=balance_after,
            description=description,
            ref_id=ref_id,
        )
        self.session.add(tx)
        await self.session.flush()
        await self.session.refresh(tx)
        return tx

    async def update_daily_consumption(self, account_id: str, amount: int) -> None:
        account = await self.get_account(account_id)
        if account is None:
            return
        account.daily_consumed = (account.daily_consumed or 0) + amount
        await self.session.flush()

    async def reset_monthly(self, account_id: str, monthly_free: int) -> None:
        await self.update_account(account_id, monthly_free_amount=monthly_free, daily_consumed=0)

    async def deduct_balance(self, account_id: str, amount: int) -> None:
        account = await self.get_account_or_raise(account_id)
        if account.balance < amount:
            from app.core.exceptions import InsufficientActionPowerError
            raise InsufficientActionPowerError(required=amount, available=account.balance)
        account.balance -= amount
        await self.session.flush()