"""合作模块 Schema"""

from pydantic import BaseModel, Field


# ── Request ───────────────────────────────────────────
class EvaluateRequest(BaseModel):
    partner_id: str = Field(..., description="合作对象ID")
    context: str = Field(default="", max_length=1000, description="合作背景描述")
    cooperation_type: str = Field(default="general", description="合作类型: general | project | resource_exchange | joint_venture")


class CreateCooperationRequest(BaseModel):
    partner_id: str = Field(...)
    title: str = Field(..., max_length=128)
    description: str = Field(default="", max_length=2000)
    cooperation_type: str = Field(default="general")
    expected_value: str | None = Field(default=None, max_length=500)
    start_date: str | None = Field(default=None, description="预计开始日期 YYYY-MM-DD")


class CreateTaskRequest(BaseModel):
    title: str = Field(..., max_length=128)
    assignee_id: str | None = Field(default=None, description="负责人ID(空=自己)")
    description: str = Field(default="", max_length=2000)
    due_date: str | None = Field(default=None, description="截止日期")
    priority: str = Field(default="medium", description="low | medium | high | urgent")


class UpdateTaskRequest(BaseModel):
    title: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    status: str | None = Field(default=None, description="pending | in_progress | completed | cancelled")
    priority: str | None = Field(default=None)
    due_date: str | None = Field(default=None)


# ── Response data ─────────────────────────────────────
class EvaluateData(BaseModel):
    compatibility_score: int = Field(description="合作契合度 0-100")
    strengths: list[str] = []
    risks: list[str] = []
    recommendations: list[str] = []
    action_power_after: int


class CooperationTask(BaseModel):
    id: str
    title: str
    description: str = ""
    status: str = "pending"
    priority: str = "medium"
    assignee_id: str | None = None
    assignee_name: str | None = None
    due_date: str | None = None
    created_at: str | None = None


class CooperationDetail(BaseModel):
    id: str
    partner_id: str
    partner_name: str
    partner_avatar: str | None = None
    title: str
    description: str = ""
    cooperation_type: str = "general"
    status: str = Field(description="active | completed | cancelled")
    expected_value: str | None = None
    progress: int = Field(default=0, ge=0, le=100)
    tasks: list[CooperationTask] = []
    start_date: str | None = None
    created_at: str | None = None


class CreateCooperationData(BaseModel):
    cooperation_id: str
    action_power_after: int


class CompleteCooperationData(BaseModel):
    cooperation_id: str
    final_score: int = Field(description="合作成果评分 0-100")
    summary: str
    action_power_after: int
