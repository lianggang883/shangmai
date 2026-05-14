"""会员模块 Schema"""

from pydantic import BaseModel, Field


# ── Request ───────────────────────────────────────────
class UpdateProfileRequest(BaseModel):
    nickname: str | None = Field(default=None, max_length=32)
    avatar: str | None = Field(default=None, max_length=512)
    bio: str | None = Field(default=None, max_length=512)
    company: str | None = Field(default=None, max_length=128)
    title: str | None = Field(default=None, max_length=64)
    city: str | None = Field(default=None, max_length=64)
    wechat: str | None = Field(default=None, max_length=64)
    industries: list[str] | None = Field(default=None, max_length=10)
    resources_have: list[str] | None = Field(default=None, max_length=10)
    resources_need: list[str] | None = Field(default=None, max_length=10)


class UpdateRolesRequest(BaseModel):
    roles: list[str] = Field(..., min_length=1, max_length=5, description="角色列表")


# ── Response data ─────────────────────────────────────
class MemberProfile(BaseModel):
    id: str
    phone: str
    nickname: str | None = None
    name: str | None = Field(default=None, description="昵称(兼容旧前端)")
    avatar: str | None = None
    bio: str | None = None
    company: str | None = None
    title: str | None = None
    city: str | None = None
    wechat: str | None = None
    industries: list[str] = []
    resources_have: list[str] = []
    resources_need: list[str] = []
    roles: list[str] = []
    interests: list[str] = Field(default=[], description="兴趣标签(兼容旧前端)")
    action_power: int = 0
    action_power_balance: int | None = Field(default=None, description="行动力余额(兼容旧前端)")
    total_action_power: int = 0
    level: int = 1
    referral_code: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class NameCardData(BaseModel):
    member_id: str
    nickname: str
    avatar: str | None = None
    company: str | None = None
    title: str | None = None
    city: str | None = None
    industries: list[str] = []
    resources_have: list[str] = []
    resources_need: list[str] = []
    bio: str | None = None
    wechat: str | None = None
    match_score: int | None = Field(default=None, description="与当前用户的匹配度(0-100)")
    action_power_after: int = Field(description="查看后剩余行动力")


class CoachDiagnosisData(BaseModel):
    diagnosis_id: str
    status: str = "completed"  # pending | processing | completed
    summary: str | None = None
    strengths: list[str] = []
    weaknesses: list[str] = []
    suggestions: list[str] = []
    created_at: str | None = None


# ── Game / 赛季相关 Schema（兼容前端） ─────────────────────────────
class BadgeData(BaseModel):
    id: str
    name: str
    icon: str | None = None
    earned: bool = False


class GameProfileData(BaseModel):
    """GET /game/profile 响应（兼容前端 Profile.vue）"""
    action_power_balance: int | None = Field(default=None, description="行动力余额")
    exp_points: int | None = Field(default=None, description="经验积分")
    action_power: int | None = Field(default=None, description="行动力别名(兼容前端)")
    level: int | None = Field(default=None, description="等级")
    total_action_power: int | None = None


class GameBadgesData(BaseModel):
    """GET /game/badges 响应"""
    badges: list[BadgeData] = []


class SeasonData(BaseModel):
    """GET /game/season 响应"""
    season_id: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    rewards: list[str] = Field(default_factory=list)


class CheckinData(BaseModel):
    """POST /game/checkin 响应"""
    message: str = "签到成功"
    action_power_after: int = 0
