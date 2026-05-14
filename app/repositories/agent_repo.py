"""Agent task repository — AI agent workflow tracking."""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError

if TYPE_CHECKING:
    from app.models.agent import AgentTask, SkillInvocation


class AgentRepo:
    """Data access for AI agent tasks and skill invocations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_task(self, task_id: str) -> "AgentTask | None":
        from app.models.agent import AgentTask
        stmt = select(AgentTask).where(AgentTask.id == task_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_task_or_raise(self, task_id: str) -> "AgentTask":
        task = await self.get_task(task_id)
        if task is None:
            raise NotFoundError(f"AgentTask id={task_id} not found")
        return task

    async def get_tasks_by_member(
        self, member_id: str, status: str | None = None
    ) -> list["AgentTask"]:
        from app.models.agent import AgentTask
        stmt = select(AgentTask).where(AgentTask.member_id == member_id)
        if status:
            stmt = stmt.where(AgentTask.status == status)
        stmt = stmt.order_by(AgentTask.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_sub_tasks(self, parent_task_id: str) -> list["AgentTask"]:
        from app.models.agent import AgentTask
        stmt = select(AgentTask).where(AgentTask.parent_task_id == parent_task_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_task(
        self,
        member_id: str,
        agent_type: str,
        input_data: dict,
        parent_task_id: str | None = None,
    ) -> "AgentTask":
        from app.models.agent import AgentTask
        task = AgentTask(
            member_id=member_id,
            agent_type=agent_type,
            input_data=input_data,
            parent_task_id=parent_task_id,
        )
        self.session.add(task)
        await self.session.flush()
        await self.session.refresh(task)
        return task

    async def update_task_status(
        self, task_id: str, status: str, output_data: dict | None = None, error: str | None = None
    ) -> "AgentTask | None":
        from app.models.agent import AgentTask
        task = await self.get_task(task_id)
        if task is None:
            return None
        task.status = status
        if output_data is not None:
            task.output_data = output_data
        if error is not None:
            task.error = error
        if status in ("COMPLETED", "FAILED"):
            task.completed_at = datetime.now()
        self.session.add(task)
        await self.session.flush()
        await self.session.refresh(task)
        return task

    async def get_skill_invocations(
        self, member_id: str, skill_name: str | None = None
    ) -> list["SkillInvocation"]:
        from app.models.agent import SkillInvocation
        stmt = select(SkillInvocation).where(SkillInvocation.member_id == member_id)
        if skill_name:
            stmt = stmt.where(SkillInvocation.skill_name == skill_name)
        stmt = stmt.order_by(SkillInvocation.invoked_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def record_skill_invocation(
        self,
        member_id: str,
        skill_name: str,
        input_data: dict,
        output_data: dict,
        cost: float,
        duration_ms: int,
    ) -> "SkillInvocation":
        from app.models.agent import SkillInvocation
        invocation = SkillInvocation(
            member_id=member_id,
            skill_name=skill_name,
            input_data=input_data,
            output_data=output_data,
            cost=cost,
            duration_ms=duration_ms,
        )
        self.session.add(invocation)
        await self.session.flush()
        await self.session.refresh(invocation)
        return invocation