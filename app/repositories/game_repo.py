"""Game (gamification) repository."""
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.models.game import MemberGameProfile, GameTask, TaskProgress, LeaderboardEntry


class GameRepo:
    """Data access for gamification entities."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_profile(self, member_id: str) -> "MemberGameProfile | None":
        stmt = select(MemberGameProfile).where(MemberGameProfile.member_id == member_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_profile(self, member_id: str) -> "MemberGameProfile":
        from app.models.game import MemberGameProfile
        profile = MemberGameProfile(member_id=member_id)
        self.session.add(profile)
        await self.session.flush()
        await self.session.refresh(profile)
        return profile

    async def get_or_create_profile(self, member_id: str) -> "MemberGameProfile":
        profile = await self.get_profile(member_id)
        if profile is None:
            profile = await self.create_profile(member_id)
        return profile

    async def get_tasks_by_type(self, task_type: str) -> list["GameTask"]:
        stmt = select(GameTask).where(GameTask.type == task_type)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_tasks(self) -> list["GameTask"]:
        stmt = select(GameTask).where(GameTask.is_active == True)  # noqa: E712
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_task_progress(
        self, member_id: str, task_id: str
    ) -> "TaskProgress | None":
        stmt = select(TaskProgress).where(
            TaskProgress.member_id == member_id,
            TaskProgress.task_id == task_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_task_progress(
        self, member_id: str, task_id: str, progress: int, target: int
    ) -> "TaskProgress":
        from app.models.game import TaskProgress
        existing = await self.get_task_progress(member_id, task_id)
        if existing:
            existing.progress = progress
            existing.target = target
            existing.completed = progress >= target
            self.session.add(existing)
            await self.session.flush()
            await self.session.refresh(existing)
            return existing
        tp = TaskProgress(
            member_id=member_id,
            task_id=task_id,
            progress=progress,
            target=target,
            completed=progress >= target,
        )
        self.session.add(tp)
        await self.session.flush()
        await self.session.refresh(tp)
        return tp

    async def update_leaderboard(
        self, season_id: str, member_id: str, rank: int, score: int
    ) -> "LeaderboardEntry":
        from app.models.game import LeaderboardEntry
        stmt = select(LeaderboardEntry).where(
            LeaderboardEntry.season_id == season_id,
            LeaderboardEntry.member_id == member_id,
        )
        result = await self.session.execute(stmt)
        entry = result.scalar_one_or_none()
        if entry:
            entry.rank = rank
            entry.score = score
            self.session.add(entry)
        else:
            entry = LeaderboardEntry(
                season_id=season_id,
                member_id=member_id,
                rank=rank,
                score=score,
            )
            self.session.add(entry)
        await self.session.flush()
        await self.session.refresh(entry)
        return entry

    async def get_leaderboard(self, season_id: str, limit: int = 100) -> list["LeaderboardEntry"]:
        stmt = (
            select(LeaderboardEntry)
            .where(LeaderboardEntry.season_id == season_id)
            .order_by(LeaderboardEntry.rank.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())