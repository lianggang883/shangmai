"""智能体模块"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.common import ApiResponse, success
from app.dependencies.auth import get_current_member
from app.models.member import Member
from app.database import get_db

router = APIRouter()


# ===== Agent Types =====
AGENT_TYPES = [
    {"agent_type": "MATCH", "name": "精准匹配", "description": "基于四维模型匹配商业伙伴", "cost": 15},
    {"agent_type": "SECRETARY", "name": "商务秘书", "description": "生成破冰方案和跟进提醒", "cost": 8},
    {"agent_type": "INDUSTRY", "name": "产业链分析师", "description": "产业链协作分析", "cost": 10},
    {"agent_type": "COACH", "name": "企业教练", "description": "6层诊断与成长规划", "cost": 10},
]

# 模拟任务存储
MOCK_TASKS = [
    {
        "task_id": "task-001",
        "agent_type": "MATCH",
        "name": "精准匹配商业伙伴",
        "description": "基于您的角色定位和需求，匹配潜在合作伙伴",
        "status": "COMPLETED",
        "created_at": "2026-05-10T10:00:00",
        "completed_at": "2026-05-10T10:01:30",
        "result_summary": "匹配到3位潜在合作伙伴"
    },
    {
        "task_id": "task-002",
        "agent_type": "SECRETARY",
        "name": "破冰方案生成",
        "description": "为与新伙伴的首次联系生成个性化破冰话题",
        "status": "COMPLETED",
        "created_at": "2026-05-09T15:30:00",
        "completed_at": "2026-05-09T15:31:15",
        "result_summary": "生成了5个破冰话题建议"
    },
    {
        "task_id": "task-003",
        "agent_type": "INDUSTRY",
        "name": "产业链协作分析",
        "description": "分析上下游产业链协作机会",
        "status": "PROCESSING",
        "created_at": "2026-05-12T09:00:00",
        "progress": 65,
        "result_summary": None
    },
    {
        "task_id": "task-004",
        "agent_type": "COACH",
        "name": "企业成长诊断",
        "description": "基于NLP六层模型进行企业诊断",
        "status": "PENDING",
        "created_at": "2026-05-12T11:00:00",
        "result_summary": None
    }
]


@router.get("/list", response_model=ApiResponse)
async def list_agents():
    """获取可用智能体列表"""
    return success(data=AGENT_TYPES)


@router.get("/tasks", response_model=ApiResponse)
async def list_tasks(
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的任务列表"""
    # 计算各状态任务数量
    completed = sum(1 for t in MOCK_TASKS if t["status"] == "COMPLETED")
    processing = sum(1 for t in MOCK_TASKS if t["status"] == "PROCESSING")
    pending = sum(1 for t in MOCK_TASKS if t["status"] == "PENDING")
    
    return success(data={
        "items": MOCK_TASKS,
        "total": len(MOCK_TASKS),
        "stats": {
            "completed": completed,
            "processing": processing,
            "pending": pending
        }
    })


@router.post("/dispatch", response_model=ApiResponse)
async def dispatch_agent(
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """调度智能体 - 依具体意图动态路由"""
    return ApiResponse(
        data={
            "dispatch_id": "dispatch-uuid-001",
            "agent_plan": [
                {"agent": "MATCH", "task": "精准匹配", "estimated_cost": 15},
                {"agent": "SECRETARY", "task": "联络与生成", "estimated_cost": 8},
                {"agent": "INDUSTRY", "task": "产业链分析", "estimated_cost": 10}
            ],
            "total_estimated_cost": 33,
            "requires_budget_confirm": False
        }
    )


@router.get("/tasks/{task_id}", response_model=ApiResponse)
async def get_task_status(
    task_id: str,
    member: Member = Depends(get_current_member),
):
    """查询任务状态"""
    # 查找任务
    task = next((t for t in MOCK_TASKS if t["task_id"] == task_id), None)
    
    if not task:
        return ApiResponse(
            code=404,
            message="任务不存在",
            data={"error": "任务不存在"}
        )
    
    return ApiResponse(data={
        "task_id": task["task_id"],
        "agent_type": task["agent_type"],
        "name": task["name"],
        "description": task["description"],
        "status": task["status"],
        "output_result": {
            "summary": task.get("result_summary"),
            "progress": task.get("progress")
        },
        "created_at": task["created_at"],
        "completed_at": task.get("completed_at")
    })