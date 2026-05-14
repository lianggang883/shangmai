"""商脉系统 - 协作模块（接入真实数据库）"""
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_member
from app.database import get_db
from app.models.member import Member, MemberRole
from app.models.relationship import Relationship, RelationshipStatus
from app.models.cooperation import CooperationProject, ProjectTask, ProjectStatus, TaskStatus
from app.schemas.common import ApiResponse, success, fail
from app.schemas.cooperations import (
    EvaluateRequest, CreateCooperationRequest,
    CreateTaskRequest, UpdateTaskRequest,
)

router = APIRouter()


@router.get("", response_model=ApiResponse)
async def list_cooperations(
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的协作项目列表"""
    result = await db.execute(
        select(CooperationProject)
        .join(Relationship, CooperationProject.relationship_id == Relationship.id)
        .where(or_(Relationship.member_a == member.id, Relationship.member_b == member.id))
        .order_by(CooperationProject.created_at.desc())
    )
    projects = result.scalars().all()
    items = []
    for p in projects:
        items.append({
            "id": p.id,
            "title": p.title,
            "description": p.description,
            "status": p.status,
            "action_power_budget": p.action_power_budget,
            "created_at": str(p.created_at) if p.created_at else None,
        })
    return success({"total": len(items), "projects": items})


@router.post("/evaluate", response_model=ApiResponse)
async def evaluate_cooperation(
    req: EvaluateRequest,
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """评估协作可行性"""
    result = {
        "feasibility_score": 0.75,
        "recommended_actions": ["安排线下见面", "交换名片", "了解对方需求"],
        "estimated_value": "高价值",
        "risk_factors": ["时间不匹配", "资源不对等"],
    }
    return success(result)


@router.post("", response_model=ApiResponse)
async def create_cooperation(
    req: CreateCooperationRequest,
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """创建协作项目"""
    # 根据partner_id查找或创建关系
    rel_result = await db.execute(
        select(Relationship).where(
            or_(
                (Relationship.member_a == member.id) & (Relationship.member_b == req.partner_id),
                (Relationship.member_a == req.partner_id) & (Relationship.member_b == member.id),
            )
        )
    )
    rel = rel_result.scalar_one_or_none()
    if not rel:
        # 自动创建关系
        rel = Relationship(
            id=str(uuid4()),
            member_a=member.id,
            member_b=req.partner_id,
            status=RelationshipStatus.POTENTIAL.value,
        )
        db.add(rel)
        await db.flush()

    project = CooperationProject(
        id=str(uuid4()),
        relationship_id=rel.id,
        title=req.title,
        description=req.description or "",
        status=ProjectStatus.DRAFT.value,
        action_power_budget=20,
    )
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return success({
        "id": project.id,
        "title": project.title,
        "status": project.status,
        "message": "协作项目已创建，等待对方确认",
    })


@router.get("/{project_id}", response_model=ApiResponse)
async def get_cooperation(
    project_id: str,
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """获取协作项目详情"""
    project = await db.execute(
        select(CooperationProject).where(CooperationProject.id == project_id)
    )
    proj = project.scalar_one_or_none()
    if not proj:
        return fail("项目不存在")
    return success({
        "id": proj.id,
        "title": proj.title,
        "description": proj.description,
        "status": proj.status,
        "mvp_plan": proj.mvp_plan,
        "result_report": proj.result_report,
        "action_power_budget": proj.action_power_budget,
    })


@router.post("/{project_id}/tasks", response_model=ApiResponse)
async def create_task(
    project_id: str,
    req: CreateTaskRequest,
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """创建项目任务"""
    task = ProjectTask(
        id=str(uuid4()),
        project_id=project_id,
        title=req.title,
        description=req.description or "",
        assignee_id=req.assignee_id or member.id,
        status=TaskStatus.PENDING.value,
    )
    db.add(task)
    await db.flush()
    return success({"id": task.id, "title": task.title, "status": task.status})


@router.put("/{project_id}/tasks/{task_id}", response_model=ApiResponse)
async def update_task(
    project_id: str,
    task_id: str,
    req: UpdateTaskRequest,
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """更新任务状态"""
    result = await db.execute(
        select(ProjectTask).where(ProjectTask.id == task_id, ProjectTask.project_id == project_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        return fail("任务不存在")
    if req.status:
        task.status = req.status
    if req.result:
        task.result = req.result
    await db.flush()
    return success({"id": task.id, "status": task.status})


@router.post("/{project_id}/complete", response_model=ApiResponse)
async def complete_cooperation(
    project_id: str,
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """完成协作项目"""
    result = await db.execute(
        select(CooperationProject).where(CooperationProject.id == project_id)
    )
    proj = result.scalar_one_or_none()
    if not proj:
        return fail("项目不存在")
    proj.status = ProjectStatus.COMPLETED.value
    await db.flush()
    return success({"id": proj.id, "status": proj.status, "message": "协作项目已完成"})
