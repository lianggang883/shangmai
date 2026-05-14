"""关系模块 Schema"""

from pydantic import BaseModel, Field


# ── Request ───────────────────────────────────────────
class IcebreakRequest(BaseModel):
    method: str = Field(default="ai_suggestion", description="破冰方式: ai_suggestion | custom")
    message: str | None = Field(default=None, max_length=500, description="自定义破冰话术(method=custom时必填)")
    channel: str = Field(default="wechat", description="互动渠道: wechat | offline | phone")


class InteractionRequest(BaseModel):
    type: str = Field(..., description="互动类型: meeting | call | message | meal | event | collaboration")
    channel: str = Field(default="wechat")
    content: str = Field(default="", max_length=1000, description="互动内容/备注")
    duration_minutes: int | None = Field(default=None, ge=0, description="互动时长(分钟)")


class FeedbackRequest(BaseModel):
    overall_rating: int = Field(..., ge=1, le=5, description="整体评分 1-5")
    value_level: int = Field(..., ge=1, le=5, description="价值度")
    relationship_change: str = Field(default="stable", description="关系变化: improved | stable | declined")
    notes: str | None = Field(default=None, max_length=500)
    next_action_plan: str | None = Field(default=None, max_length=500)


# ── Response data ─────────────────────────────────────
class IcebreakData(BaseModel):
    relation_id: str
    member_id: str | None = Field(default=None, description="会员ID(兼容旧前端保温功能)")
    suggestion: str = ""
    delivered: bool = True
    action_power_after: int = 0


class InteractionData(BaseModel):
    id: str
    relation_id: str
    type: str
    channel: str
    closeness_change: int = Field(description="亲密度变化值")
    closeness_after: int = Field(description="互动后亲密度")
    action_power_after: int


class FeedbackData(BaseModel):
    id: str
    relation_id: str
    ai_insight: str | None = None
    relationship_trend: str | None = None
    action_power_after: int


class DecayAlertItem(BaseModel):
    relation_id: str
    member_id: str
    nickname: str | None = None
    name: str | None = Field(default=None, description="昵称(兼容旧前端)")
    closeness: int = 0
    days_since_interaction: int = 0
    days_inactive: int | None = Field(default=None, description="未互动天数(兼容旧前端)")
    risk_level: str = Field(default="low", description="low | medium | high | critical")
    level: str | None = Field(default=None, description="预警级别 red|yellow(兼容旧前端)")
    suggestion: str | None = None
