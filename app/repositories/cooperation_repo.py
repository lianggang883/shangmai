"""Cooperation project repository."""
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base import BaseRepository

if TYPE_CHECKING:
    from app.models.cooperation import CooperationProject


class CooperationRepo(BaseRepository["CooperationProject"]):
    """Data access for CooperationProject."""

    def __init__(self, session: AsyncSession):
        super().__init__(CooperationProject, session)

    async def get_by_relationship(self, relationship_id: str) -> list["CooperationProject"]:
        stmt = (
            select(CooperationProject)
            .where(CooperationProject.relationship_id == relationship_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_by_member(self, member_id: str) -> list["CooperationProject"]:
        stmt = (
            select(CooperationProject)
            .where(CooperationProject.member_id == member_id)
            .where(CooperationProject.status == "ACTIVE")
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_status(self, status: str, limit: int = 50) -> list["CooperationProject"]:
        stmt = (
            select(CooperationProject)
            .where(CooperationProject.status == status)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())