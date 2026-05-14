"""
商脉系统 · 十维产业链协作 SKILL (v2.0 - LLM驱动)
"""
import json, re, logging
from app.skills.base import BaseSkill, SkillType, SkillInput, SkillOutput, ValidationResult

logger = logging.getLogger(__name__)

INDUSTRY_DIMENSIONS = {
    "supply_chain": {"name": "供应链", "weight": 0.15},
    "tech_exchange": {"name": "技术交流", "weight": 0.12},
    "capital": {"name": "资本", "weight": 0.12},
    "market": {"name": "市场", "weight": 0.15},
    "talent": {"name": "人才", "weight": 0.08},
    "brand": {"name": "品牌", "weight": 0.08},
    "data_sharing": {"name": "数据共享", "weight": 0.08},
    "policy": {"name": "政策", "weight": 0.07},
    "cross_industry": {"name": "跨界", "weight": 0.07},
    "ecosystem": {"name": "生态", "weight": 0.08},
}

class IndustryChainSkill(BaseSkill):
    @property
    def skill_type(self) -> SkillType: return SkillType.INDUSTRY_CHAIN
    @property
    def version(self) -> str: return "2.0.0"

    def validate(self, input_data: SkillInput) -> ValidationResult:
        errors = []
        if not input_data.context.get("member_ids"): errors.append("缺少member_ids")
        return ValidationResult(is_valid=len(errors)==0, errors=errors)

    def estimate_cost(self, input_data: SkillInput) -> int: return 8
    def get_required_skills(self) -> list[SkillType]: return [SkillType.MCKINSEY, SkillType.GAMIFICATION]

    async def execute(self, input_data: SkillInput) -> SkillOutput:
        member_ids = input_data.context["member_ids"]
        mode = input_data.context.get("mode", "full")

        try:
            from app.utils.llm import get_llm_client
            dims_desc = "\n".join(f"- {k}: {v['name']}" for k,v in INDUSTRY_DIMENSIONS.items())
            r = await get_llm_client().chat([
                {"role":"system","content":"你是产业链协作分析专家。分析两个企业的十维产业链协作潜力。只返回JSON。"},
                {"role":"user","content":f"""分析企业 {member_ids[0]} 和 {member_ids[1] if len(member_ids)>1 else '合作伙伴'} 的产业链协作潜力:

十维分析框架:
{dims_desc}

返回JSON:
{{"dimension_scores":{{"supply_chain":{{"score":0.8,"analysis":"分析"}},"tech_exchange":{{"score":0.6,"analysis":"分析"}},...}},"proximity_score":0.72,"top3":["supply_chain","market","capital"],"mvp_plan":{{"title":"MVP计划","steps":["步骤1","步骤2"],"expected_value":"预期价值"}}}}"""}
            ], temperature=0.5, max_tokens=2500)

            m = re.search(r'\{.*\}', r, re.DOTALL)
            if m:
                data = json.loads(m.group())
                return SkillOutput(success=True, data=data, action_power_used=8, next_skill_hint=SkillType.GAMIFICATION)

        except Exception as e: logger.warning(f"LLM industry_chain fail: {e}")

        # 后备
        ds = {k: {"score": v["weight"]*5, "analysis": "需LLM深入分析"} for k,v in INDUSTRY_DIMENSIONS.items()}
        return SkillOutput(success=True, data={"dimension_scores":ds,"proximity_score":0.5,"top3":["supply_chain","market","capital"],"mvp_plan":{"title":"待LLM生成","steps":[],"expected_value":""}}, action_power_used=8)
