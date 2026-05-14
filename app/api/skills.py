"""SKILL技能模块 - 对应需求 Chapter 2.6 + 3.7"""
from typing import Optional
from fastapi import APIRouter, Depends, Body
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.common import ApiResponse, success
from app.skills.orchestrator import orchestrator, SkillType
from app.skills.base import SkillInput
from app.dependencies.auth import get_current_member
from app.models.member import Member
from app.database import get_db

router = APIRouter()


# ===== Request Models =====
class OrchestrateRequest(BaseModel):
    intent: str = Field(description="用户意图")
    context: dict = Field(default={}, description="附加上下文")


class MeceRequest(BaseModel):
    problem: str = Field(description="待分解的问题")
    context: str = Field(default="", description="附加背景信息")


class SevenStepsRequest(BaseModel):
    problem: str = Field(description="待分析的问题")
    context: str = Field(default="", description="附加背景信息")


class RoleAnalysisRequest(BaseModel):
    member_b_id: str = Field(description="对方成员ID")


class IndustryChainRequest(BaseModel):
    member_ids: list[str] = Field(default=[], description="参与成员ID列表")
    focus_dimension: str | None = Field(default=None, description="聚焦维度")


class CoachDiagnoseRequest(BaseModel):
    context: str = Field(default="", description="诊断上下文")


class CoachDialogueRequest(BaseModel):
    member_response: str = Field(description="用户回复内容")
    session_id: str | None = Field(default=None, description="会话ID")


# ===== SKILL Types 端点 =====
SKILL_TYPES = [
    {"id": "mece", "name": "MECE拆解", "cost": 8, "description": "麦肯锡MECE分析法"},
    {"id": "seven_steps", "name": "七步成诗法", "cost": 15, "description": "麦肯锡七步成诗法"},
    {"id": "role", "name": "角色分析", "cost": 5, "description": "十维角色标识匹配"},
    {"id": "industry_chain", "name": "产业链分析", "cost": 8, "description": "十维产业链协作"},
    {"id": "coach", "name": "企业教练", "cost": 10, "description": "6层诊断+教练对话"},
]


@router.get("/types", response_model=ApiResponse)
async def get_skill_types():
    """获取所有SKILL类型列表"""
    return success(data=SKILL_TYPES)


# ===== Endpoints =====
@router.post("/orchestrate", response_model=ApiResponse)
async def orchestrate_skills(
    req: OrchestrateRequest = Body(default=OrchestrateRequest(intent="general")),
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """SKILL编排 - 依意图映射、调度、预执行"""
    input_data = SkillInput(member_id=member.id, context=req.context or {})
    result = await orchestrator.orchestrate(req.intent, input_data)
    return ApiResponse(
        data=result.data,
        meta={"action_power_consumed": result.action_power_used}
    )


@router.post("/mece", response_model=ApiResponse)
async def mece_analysis(
    req: MeceRequest = Body(default=MeceRequest(problem="")),
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """MECE拆解 - 花费8币"""
    input_data = SkillInput(
        member_id=member.id,
        context={"problem": req.problem, "context": req.context}
    )
    result = await orchestrator.execute_single(SkillType.MCKINSEY, input_data)
    return ApiResponse(data=result.data, meta={"action_power_consumed": 8})


@router.post("/seven-steps", response_model=ApiResponse)
async def seven_steps_analysis(
    req: SevenStepsRequest = Body(default=SevenStepsRequest(problem="")),
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """七步成诗法 - 花费15币"""
    from app.skills.mckinsey_seven_steps import McKinseySevenStepsSkill
    skill = McKinseySevenStepsSkill()
    input_data = SkillInput(
        member_id=member.id,
        context={"problem": req.problem, "context": req.context}
    )
    result = await skill.run(input_data)
    return ApiResponse(data=result.data, meta={"action_power_consumed": result.action_power_used})


@router.post("/role-analysis", response_model=ApiResponse)
async def role_analysis(
    req: RoleAnalysisRequest = Body(...),
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """角色分析 - 花费5币"""
    input_data = SkillInput(
        member_id=member.id,
        context={"member_a_id": member.id, "member_b_id": req.member_b_id}
    )
    result = await orchestrator.execute_single(SkillType.ROLE, input_data)
    return ApiResponse(data=result.data, meta={"action_power_consumed": result.action_power_used})


@router.post("/industry-chain-analysis", response_model=ApiResponse)
async def industry_chain_analysis(
    req: IndustryChainRequest = Body(default=IndustryChainRequest()),
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """产业链分析 - 花费8币"""
    member_ids = req.member_ids or [member.id]
    input_data = SkillInput(
        member_id=member_ids[0] if member_ids else member.id,
        context={"member_ids": member_ids, "focus_dimension": req.focus_dimension}
    )
    result = await orchestrator.execute_single(SkillType.INDUSTRY_CHAIN, input_data)
    return ApiResponse(data=result.data, meta={"action_power_consumed": result.action_power_used})


@router.post("/coach-diagnose", response_model=ApiResponse)
async def coach_diagnose(
    req: CoachDiagnoseRequest = Body(default=CoachDiagnoseRequest()),
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """教练诊断 - 花费10币"""
    input_data = SkillInput(
        member_id=member.id,
        context={"diagnose_mode": True, "context": req.context}
    )
    result = await orchestrator.execute_single(SkillType.COACH, input_data)
    return ApiResponse(data=result.data, meta={"action_power_consumed": result.action_power_used})


@router.post("/coach-dialogue", response_model=ApiResponse)
async def coach_dialogue(
    req: CoachDialogueRequest = Body(...),
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """教练对话 - 花费5币/轮"""
    input_data = SkillInput(
        member_id=member.id,
        session_id=req.session_id,
        context={"dialogue_mode": True, "member_response": req.member_response}
    )
    result = await orchestrator.execute_single(SkillType.COACH, input_data)
    return ApiResponse(data=result.data, meta={"action_power_consumed": result.action_power_used})


@router.get("/linkage-matrix", response_model=ApiResponse)
async def get_linkage_matrix():
    """获取SKILL联动矩阵"""
    return ApiResponse(data=orchestrator.get_linkage_matrix())


@router.get("/list", response_model=ApiResponse)
async def list_skills():
    """列出所有已注册SKILL"""
    return ApiResponse(data=orchestrator.list_skills())


# ===== 2026-05-10 新增端点 =====

@router.get("/my-matches", response_model=ApiResponse)
async def get_my_skill_matches(
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """我的技能匹配 - 根据用户角色推荐技能"""
    from sqlalchemy import select
    from app.models.member import MemberRole
    result = await db.execute(
        select(MemberRole).where(MemberRole.member_id == member.id)
    )
    user_roles = result.scalars().all()
    role_codes = [r.role_code for r in user_roles] if user_roles else []

    ROLE_SKILL_MAP = {
        "partner": ["mece", "industry_chain"],
        "customer": ["role", "coach"],
        "mentor": ["seven_steps", "coach"],
        "investor": ["industry_chain", "mece"],
        "supplier": ["industry_chain"],
        "expert": ["seven_steps", "mece"],
        "cross_industry": ["role", "industry_chain"],
        "team": ["coach"],
        "media": ["role"],
        "ai_advisor": ["coach", "mece"],
    }

    recommended = set()
    for rc in role_codes:
        if rc in ROLE_SKILL_MAP:
            recommended.update(ROLE_SKILL_MAP[rc])

    if not recommended:
        recommended = {"mece", "role", "coach"}

    skill_ids = {s["id"] for s in SKILL_TYPES}
    final = [s for s in SKILL_TYPES if s["id"] in recommended and s["id"] in skill_ids]

    return success(data={
        "my_roles": role_codes,
        "recommended_skills": final,
    })


@router.get("/{skill_type}/recommend", response_model=ApiResponse)
async def get_skill_recommend(
    skill_type: str,
    member: Member = Depends(get_current_member),
):
    """技能推荐 - 获取指定类型技能的推荐内容"""
    valid_types = {s["id"] for s in SKILL_TYPES}
    if skill_type not in valid_types:
        return ApiResponse(code=-1, message=f"不支持的技能类型: {skill_type}")

    RECOMMEND_CONTENT = {
        "mece": {
            "title": "MECE分析法",
            "tips": ["相互独立，不重叠", "完全穷尽，无遗漏", "适用于问题拆解和分类"],
            "example": "如何提升客户满意度？→ 拆解为：产品质量、服务态度、价格竞争力..."
        },
        "seven_steps": {
            "title": "七步成诗法",
            "tips": ["定义问题 → 分解 → 排序 → 计划 → 分析 → 汇总 → 阐述"],
            "example": "收入下降怎么办？→ 先定义问题，再分解为客户数×客单价×复购率"
        },
        "role": {
            "title": "十维角色匹配",
            "tips": ["我是谁（我能提供什么）", "我需要谁（我在找什么）", "精准对接，双向赋能"],
            "example": "如果你是 mentor，寻找 customer/team 角色的人"
        },
        "industry_chain": {
            "title": "产业链协作",
            "tips": ["横向集约（同业联盟）", "纵向集成（上下游）", "需求链接，痛点协同"],
            "example": "餐饮+食材供应链+物流 = 完整产业链协同"
        },
        "coach": {
            "title": "企业教练",
            "tips": ["NLP理解六层次：环境→行为→能力→信念→身份→精神", "从上层往下拉，或从下层往上提"],
            "example": "反复抱怨外部？→ 环境层；说不会做？→ 能力层"
        },
    }

    content = RECOMMEND_CONTENT.get(skill_type, {"title": skill_type, "tips": [], "example": ""})
    return success(data={
        "skill_type": skill_type,
        **content
    })
