"""
商脉系统 · 麦肯锡七步成诗法 SKILL (v2.0 - LLM驱动)
"""
import json, re, logging
from app.skills.base import BaseSkill, SkillType, SkillInput, SkillOutput, ValidationResult

logger = logging.getLogger(__name__)

SEVEN_STEPS = [
    {"id":"s1","name":"陈述问题","key":"state_problem"},
    {"id":"s2","name":"分解问题","key":"decompose"},
    {"id":"s3","name":"消除非关键","key":"eliminate"},
    {"id":"s4","name":"制定详细工作计划","key":"work_plan"},
    {"id":"s5","name":"关键分析","key":"key_analysis"},
    {"id":"s6","name":"综合结果","key":"synthesize"},
    {"id":"s7","name":"构建有说服力的故事","key":"story"},
]

class McKinseySevenStepsSkill(BaseSkill):
    @property
    def skill_type(self) -> SkillType: return SkillType.MCKINSEY
    @property
    def version(self) -> str: return "2.0.0"

    def validate(self, input_data: SkillInput) -> ValidationResult:
        errors = []
        if not input_data.context.get("problem"): errors.append("缺少problem")
        return ValidationResult(is_valid=len(errors)==0, errors=errors)

    def estimate_cost(self, input_data: SkillInput) -> int: return 12
    def get_required_skills(self) -> list[SkillType]: return [SkillType.COACH]

    async def execute(self, input_data: SkillInput) -> SkillOutput:
        problem = input_data.context.get("problem", "")
        current_step = input_data.context.get("current_step", 1)

        try:
            from app.utils.llm import get_llm_client
            steps_desc = "\n".join(f"{s['id']}. {s['name']}" for s in SEVEN_STEPS)
            r = await get_llm_client().chat([
                {"role":"system","content":"你是麦肯锡顾问，精通七步成诗法。只返回JSON。"},
                {"role":"user","content":f"""用七步成诗法分析问题:
问题: {problem}
当前步骤: 第{current_step}步

七步法:
{steps_desc}

返回JSON:
{{"current_step":{current_step},"step_name":"步骤名","analysis":"该步骤的详细分析","output":"该步骤的输出","next_action":"下一步建议","all_steps":{{"s1":{{"done":true,"summary":"摘要"}},"s2":{{"done":false,"summary":""}}}}}}"""}
            ], temperature=0.5, max_tokens=2000)

            m = re.search(r'\{.*\}', r, re.DOTALL)
            if m: return SkillOutput(success=True, data=json.loads(m.group()), action_power_used=12, next_skill_hint=SkillType.COACH)

        except Exception as e: logger.warning(f"LLM seven_steps fail: {e}")

        return SkillOutput(success=True, data={"current_step":current_step,"step_name":SEVEN_STEPS[min(current_step-1,6)]["name"],"analysis":"需LLM分析","output":"","next_action":"请接入LLM"}, action_power_used=12)
