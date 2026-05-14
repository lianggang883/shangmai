"""Relationship repository — CRUD and domain-specific queries."""
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.repositories.base import BaseRepository
from app.models.relationship import Relationship, Interaction, DecayLevel
from app.core.exceptions import NotFoundError


class RelationshipRepo(BaseRepository[Relationship]):
    """Data access for Relationship and Interaction entities."""

    def __init__(self, session: AsyncSession):
        super().__init__(Relationship, session)

    # ── Custom queries ──────────────────────────────────

    async def get_between(self, member_a: str, member_b: str) -> Relationship | None:
        stmt = select(Relationship).where(
            or_(
                and_(Relationship.member_a == member_a, Relationship.member_b == member_b),
                and_(Relationship.member_a == member_b, Relationship.member_b == member_a),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_member(
        self, member_id: str, status: str | None = None
    ) -> list[Relationship]:
        filters = {
            "member_a": member_id,
        }
        stmt = select(Relationship).where(
            or_(
                Relationship.member_a == member_id,
                Relationship.member_b == member_id,
            )
        )
        if status:
            stmt = stmt.where(Relationship.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_potential(self, member_id: str, limit: int = 20) -> list[Relationship]:
        stmt = (
            select(Relationship)
            .where(
                or_(
                    Relationship.member_a == member_id,
                    Relationship.member_b == member_id,
                )
            )
            .where(Relationship.status == "POTENTIAL")
            .order_by(Relationship.total_score.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_decay_alerts(
        self, member_id: str, days: int = 30
    ) -> list[Relationship]:
        cutoff = datetime.now() - timedelta(days=days)
        stmt = (
            select(Relationship)
            .where(
                or_(
                    Relationship.member_a == member_id,
                    Relationship.member_b == member_id,
                )
            )
            .where(
                Relationship.last_interaction_at <= cutoff,
                Relationship.decay_level.in_(["yellow", "orange", "red"]),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_scores(
        self,
        rel_id: str,
        scores: dict[str, float],
    ) -> Relationship | None:
        update_data = {}
        for key in ["role_match_score", "industry_chain_score", "motivation_score", "activity_score"]:
            if key in scores:
                camel_key = key.replace("_score", "")
                update_data[key] = Decimal(str(scores.get(camel_key, 0)))
        total = sum(float(str(v)) for v in update_data.values()) / max(len(update_data), 1)
        update_data["total_score"] = Decimal(str(round(total, 2)))
        return await self.update(rel_id, update_data)

    async def update_status(self, rel_id: str, status: str) -> Relationship | None:
        return await self.update(rel_id, {"status": status})

    async def add_interaction(
        self, rel_id: str, itype: str, summary: str | None = None
    ) -> Interaction:
        from app.models.relationship import Interaction
        interaction = Interaction(
            relationship_id=rel_id,
            type=itype,
            summary=summary,
        )
        self.session.add(interaction)
        await self.session.flush()
        # update last_interaction_at
        await self.update(rel_id, {"last_interaction_at": interaction.occurred_at})
        await self.session.refresh(interaction)
        return interaction

    async def update_decay_level(self, rel_id: str, decay_level: str) -> Relationship | None:
        return await self.update(rel_id, {"decay_level": decay_level})