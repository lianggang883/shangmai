"""
商脉系统 — SKILL引擎基类

五大SKILL的统一抽象：
  MCKINSEY  — 麦肯锡方法论 (MECE + 七步成诗法)
  ROLE      — 十维角色标识匹配
  INDUSTRY_CHAIN — 十维产业链协作
  GAMIFICATION   — 游戏化设计
  COACH     — 企业教练技术
  SECRETARY — 商务秘书（破冰方案/联络跟进）

参考技术规格样板 Chapter 3
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class SkillType(str, Enum):
    MCKINSEY = "MCKINSEY"
    ROLE = "ROLE"
    INDUSTRY_CHAIN = "INDUSTRY_CHAIN"
    GAMIFICATION = "GAMIFICATION"
    COACH = "COACH"
    SECRETARY = "SECRETARY"


class ValidationResult(BaseModel):
    """输入校验结果"""
    is_valid: bool = True
    errors: list[str] = Field(default_factory=list)


class SkillInput(BaseModel):
    """SKILL统一输入"""
    member_id: str
    session_id: Optional[str] = None
    context: dict[str, Any] = Field(default_factory=dict)


class SkillOutput(BaseModel):
    """SKILL统一输出"""
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    action_power_used: int = 0
    next_skill_hint: Optional[SkillType] = None
    error_message: Optional[str] = None


class SkillInvocation(BaseModel):
    """SKILL调用记录（用于持久化）"""
    id: Optional[str] = None
    member_id: str
    skill_type: SkillType
    sub_skill: Optional[str] = None
    input_params: dict = Field(default_factory=dict)
    output_result: dict = Field(default_factory=dict)
    action_power_cost: int = 0
    status: str = "COMPLETED"
    created_at: datetime = Field(default_factory=datetime.now)


class BaseSkill(ABC):
    """
    SKILL基类 — 所有技能的抽象模板

    生命周期:
      validate() → before_execute() → execute() → after_execute()

    关键设计:
      - estimate_cost(): 预估行动力，用于预算确认
      - get_required_skills(): 声明依赖，用于调度器编排
      - before_execute/after_execute: 钩子，处理计费和记录
    """

    @property
    @abstractmethod
    def skill_type(self) -> SkillType:
        """技能类型标识"""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """技能版本号"""
        ...

    @abstractmethod
    async def execute(self, input_data: SkillInput) -> SkillOutput:
        """
        核心执行方法：输入 → 输出

        子类必须实现此方法，包含完整的业务逻辑。
        """
        ...

    @abstractmethod
    def validate(self, input_data: SkillInput) -> ValidationResult:
        """输入校验：在execute前调用，不通过则拒绝执行"""
        ...

    @abstractmethod
    def estimate_cost(self, input_data: SkillInput) -> int:
        """预估行动力消耗（用于预算确认和大额拦截）"""
        ...

    @abstractmethod
    def get_required_skills(self) -> list[SkillType]:
        """声明依赖的其他SKILL（用于调度器编排执行顺序）"""
        ...

    async def before_execute(self, input_data: SkillInput) -> None:
        """
        执行前钩子：行动力预扣

        调用时机：validate通过后、execute之前
        作用：冻结预估行动力，防止超额消费
        """
        cost = self.estimate_cost(input_data)
        # 实际扣费由 BillingService 处理，这里只是声明
        # await billing_service.pre_deduct(input_data.member_id, cost)
        pass

    async def after_execute(self, input_data: SkillInput, output: SkillOutput) -> None:
        """
        执行后钩子：结算+记录

        调用时机：execute完成后（无论成功失败）
        作用：按实际消耗结算行动力，写入调用记录
        """
        # await billing_service.settle(input_data.member_id, output.action_power_used)
        # await skill_invocation_repo.save(...)
        pass

    async def run(self, input_data: SkillInput) -> SkillOutput:
        """
        完整执行流程：校验 → 预扣 → 执行 → 结算

        外部调用应使用此方法而非直接调用execute()
        """
        # Step 1: 校验
        validation = self.validate(input_data)
        if not validation.is_valid:
            return SkillOutput(
                success=False,
                error_message=f"输入校验失败: {', '.join(validation.errors)}"
            )

        # Step 2: 预扣
        await self.before_execute(input_data)

        # Step 3: 执行
        try:
            output = await self.execute(input_data)
        except Exception as e:
            output = SkillOutput(
                success=False,
                error_message=f"执行异常: {str(e)}"
            )

        # Step 4: 结算
        await self.after_execute(input_data, output)

        return output
