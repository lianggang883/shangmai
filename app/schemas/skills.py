"""SKILL模块 Schema"""

from pydantic import BaseModel, Field


# ── Request ───────────────────────────────────────────
class MECEAnalysisRequest(BaseModel):
    topic: str = Field(..., max_length=256, description="待拆解主题")
    context: str = Field(default="", max_length=1000, description="背景补充")
    dimensions: list[str] | None = Field(default=None, description="指定拆解维度")


class SevenStepsRequest(BaseModel):
    goal: str = Field(..., max_length=256, description="目标/问题")
    background: str = Field(default="", max_length=2000, description="背景信息")
    constraints: list[str] | None = Field(default=None, description="约束条件")


class RoleAnalysisRequest(BaseModel):
    member_id: str | None = Field(default=None, description="分析对象(空=自己)")
    scenario: str = Field(default="networking", description="场景: networking | cooperation | leadership")


class IndustryChainRequest(BaseModel):
    industry: str = Field(..., max_length=128, description="行业名称")
    focus: str | None = Field(default=None, max_length=256, description="关注点/细分领域")


class CoachDiagnoseRequest(BaseModel):
    focus_areas: list[str] | None = Field(default=None, description="聚焦领域")
    context: str = Field(default="", max_length=2000, description="个人背景补充")


class CoachDialogueRequest(BaseModel):
    session_id: str | None = Field(default=None, description="会话ID(首次为空)")
    message: str = Field(..., max_length=2000, description="用户消息")


# ── Response data ─────────────────────────────────────
class MECEAnalysisData(BaseModel):
    analysis_id: str
    topic: str
    dimensions: list[dict] = Field(description="拆解维度列表, 每项含name/children/description")
    completeness_score: int = Field(description="完整性评分 0-100")
    action_power_after: int


class SevenStepsData(BaseModel):
    analysis_id: str
    goal: str
    steps: list[dict] = Field(description="7个步骤, 每步含title/content/key_actions")
    risk_assessment: str | None = None
    action_power_after: int


class RoleAnalysisData(BaseModel):
    analysis_id: str
    member_id: str
    role_profile: dict = Field(description="角色画像")
    strengths: list[str] = []
    blind_spots: list[str] = []
    development_path: list[dict] = []
    action_power_after: int


class IndustryChainData(BaseModel):
    analysis_id: str
    industry: str
    chain_nodes: list[dict] = Field(description="产业链节点")
    opportunities: list[dict] = []
    risks: list[dict] = []
    my_position: dict | None = None
    action_power_after: int


class CoachDiagnoseData(BaseModel):
    diagnosis_id: str
    overall_score: int = Field(description="综合评分 0-100")
    dimensions: list[dict] = Field(description="各维度评分与分析")
    key_findings: list[str] = []
    action_plan: list[dict] = []
    action_power_after: int


class CoachDialogueData(BaseModel):
    session_id: str
    reply: str
    is_completed: bool = False
    turn_count: int
    action_power_after: int
