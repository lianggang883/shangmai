"""游戏化模块 Schema"""

from pydantic import BaseModel, Field


# ── Request ───────────────────────────────────────────
class CompleteGameTaskRequest(BaseModel):
    proof: str | None = Field(default=None, max_length=500, description="完成凭证/备注")


# ── Response data ─────────────────────────────────────
class GameProfileData(BaseModel):
    member_id: str
    level: int
    title: str
    exp: int = Field(description="当前经验值")
    exp_to_next: int = Field(description="升级所需经验")
    badges: list[dict] = Field(description="已获徽章列表")
    streak_days: int = Field(description="连续活跃天数")
    total_connections: int = Field(description="累计连接数")
    total_cooperations: int = Field(description="累计合作数")
    action_power: int = Field(description="当前行动力")
    action_power_max: int = Field(description="行动力上限")
    last_checkin: str | None = None
    today_checkin: bool = False


class CheckinData(BaseModel):
    success: bool
    action_power_gained: int
    exp_gained: int
    streak_days: int
    new_badge: dict | None = None


class GameTaskItem(BaseModel):
    id: str
    title: str
    description: str = ""
    category: str = Field(description="daily | weekly | achievement")
    reward_action_power: int = 0
    reward_exp: int = 0
    progress: int = Field(default=0, ge=0)
    target: int = Field(default=1, ge=1)
    completed: bool = False
    expires_at: str | None = None


class LeaderboardItem(BaseModel):
    rank: int
    member_id: str
    nickname: str
    avatar: str | None = None
    level: int
    score: int
    badges_count: int
