"""Member repository — CRUD and domain-specific queries."""
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.repositories.base import BaseRepository
from app.models.member import Member, MemberRole, MemberDiagnosis
from app.core.exceptions import NotFoundError


class MemberRepo(BaseRepository[Member]):
    """Data access for Member and related entities."""

    def __init__(self, session: AsyncSession):
        super().__init__(Member, session)

    # ── Custom queries ──────────────────────────────────

    async def get_by_phone(self, phone: str) -> Member | None:
        return await self.get_by_field("phone", phone)

    async def get_by_phone_or_raise(self, phone: str) -> Member:
        member = await self.get_by_phone(phone)
        if member is None:
            raise NotFoundError(f"Member with phone={phone} not found")
        return member

    async def get_with_roles(self, member_id: str) -> Member | None:
        stmt = (
            select(Member)
            .options(selectinload(Member.roles))
            .where(Member.id == member_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_with_diagnosis(self, member_id: str) -> Member | None:
        stmt = (
            select(Member)
            .options(selectinload(Member.diagnoses))
            .where(Member.id == member_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_industry(self, industry: str, limit: int = 20) -> list[Member]:
        stmt = (
            select(Member)
            .where(Member.industry == industry)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_referrals(self, referrer_id: str) -> list[Member]:
        stmt = (
            select(Member)
            .where(Member.referrer_id == referrer_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_level(self, member_id: str, level: int, exp: int) -> Member | None:
        return await self.update(member_id, {"level": level, "exp_points": exp})

    async def update_action_power(
        self, member_id: str, balance: int, frozen: int
    ) -> Member | None:
        return await self.update(
            member_id,
            {"action_power_balance": balance, "action_power_frozen": frozen},
        )