"""智能体模块 Schema"""

from pydantic import BaseModel, Field


# ── Request ───────────────────────────────────────────
class DispatchRequest(BaseModel):
    agent_type: str = Field(..., description="智能体类型: matcher | coach | analyst | icebreaker")
    task: str = Field(..., max_length=2000, description="任务描述")
    context: dict | None = Field(default=None, description="上下文数据")
    priority: str = Field(default="normal", description="low | normal | high")


# ── Response data ─────────────────────────────────────
class DispatchData(BaseModel):
    task_id: str
    agent_type: str
    status: str = "queued"  # queued | processing | completed | failed
    estimated_time_seconds: int | None = None


class AgentTaskStatus(BaseModel):
    task_id: str
    agent_type: str
    status: str
    progress: int = Field(default=0, ge=0, le=100)
    result: dict | str | None = None
    error: str | None = None
    created_at: str | None = None
    completed_at: str | None = None
