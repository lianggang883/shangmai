"""匹配模块 Schema"""

from pydantic import BaseModel, Field


# ── Request ───────────────────────────────────────────
class MatchTriggerRequest(BaseModel):
    """触发匹配的请求体"""
    target_role: str | None = Field(default=None, description="目标角色类型")
    industry_filter: list[str] | None = Field(default=None, description="行业筛选")
    criteria: dict | None = Field(default=None, description="额外匹配条件")
    limit: int = Field(default=10, ge=1, le=50, description="返回数量上限")
    # ── 兼容前端旧字段名 ──
    member_id: str | None = Field(default=None, description="会员ID(兼容旧前端)")
    top_k: int | None = Field(default=None, ge=1, le=50, description="返回数量(兼容旧前端)")
    # ──────────────────────


class TriggerMatchingRequest(BaseModel):
    target_role: str | None = Field(default=None, description="目标角色类型(兼容旧前端)")
    top_k: int | None = Field(default=None, ge=1, le=50, description="返回数量(兼容旧前端)")
    member_id: str | None = Field(default=None, description="会员ID(兼容旧前端)")
    criteria: dict | None = Field(default=None, description="额外匹配条件")
    limit: int = Field(default=10, ge=1, le=50, description="返回数量上限")


# ── Response data ─────────────────────────────────────
class PotentialMember(BaseModel):
    member_id: str
    nickname: str | None = None
    # ── 兼容前端旧字段名 ──
    name: str | None = Field(default=None, description="昵称(兼容旧前端)")
    avatar: str | None = None
    company: str | None = None
    title: str | None = None
    industries: list[str] = []
    # 兼容前端 total_score / score_breakdown
    match_score: int = Field(default=0, description="匹配度 0-100")
    total_score: float | None = Field(default=None, description="综合分数 0-1(兼容旧前端)")
    score_breakdown: dict | None = Field(default=None, description="分项分数(兼容旧前端)")
    match_reasons: list[str] = Field(default=[], description="匹配原因标签")
    ai_reason: str | None = Field(default=None, description="AI匹配理由(兼容旧前端)")
    top_dimension: str | None = Field(default=None, description="主要维度(兼容旧前端)")
    action_power_after: int = 0
    # ──────────────────────


class MatchingResultData(BaseModel):
    match_id: str
    matched_count: int
    potential_members: list[PotentialMember] = []
    results: list[PotentialMember] = Field(default=[], description="匹配结果(兼容旧前端)")
    total_candidates: int | None = Field(default=None, description="候选总数(兼容旧前端)")
    action_power_after: int


class DailyReportItem(BaseModel):
    member_id: str
    nickname: str | None = None
    name: str | None = Field(default=None, description="昵称(兼容旧前端)")
    match_score: int = 0
    score: float | None = Field(default=None, description="匹配分数(兼容旧前端)")
    company: str | None = None
    reason: str | None = Field(default=None, description="匹配原因(兼容旧前端)")
    new_interactions: int = 0
    recommendation: str | None = None


class DailyReportData(BaseModel):
    report_date: str
    total_potential: int
    highlights: list[DailyReportItem] = []
    recommendations: list[DailyReportItem] = Field(default=[], description="推荐列表(兼容旧前端)")
    decay_alerts: list = Field(default=[], description="衰减预警(兼容旧前端 Home.vue)")
    headline: str | None = Field(default=None, description="日报标题(兼容旧前端)")
    golden_quote: str | None = Field(default=None, description="金句(兼容旧前端)")
    action_power_after: int = 0


class MatchDetailData(BaseModel):
    member: PotentialMember
    shared_industries: list[str] = []
    complement_resources: list[str] = []
    mutual_connections: list[str] = []
    interaction_history: list[dict] = []
    action_power_after: int


class RelationBrief(BaseModel):
    id: str
    member_id: str
    nickname: str | None = None
    # ── 兼容前端旧字段名 ──
    name: str | None = Field(default=None, description="昵称(兼容旧前端)")
    avatar: str | None = None
    company: str | None = None
    closeness: int = Field(default=0, ge=0, le=100, description="亲密度")
    stage: str = Field(default="discovered", description="关系阶段")
    status: str | None = Field(default=None, description="关系状态(兼容旧前端): POTENTIAL|VERIFIED|ACTIVE|DECAYING")
    last_interaction_at: str | None = None
    match_score: int = 0
    total_score: float | None = Field(default=None, description="综合分数(兼容旧前端)")
    # ──────────────────────
