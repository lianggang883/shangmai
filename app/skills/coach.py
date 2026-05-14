"""
商脉系统 · 企业教练 SKILL (v2.0 - LLM驱动)
"""
import json, re, logging
from app.skills.base import BaseSkill, SkillType, SkillInput, SkillOutput, ValidationResult

logger = logging.getLogger(__name__)

COACHING_LAYERS = {
    "environment": {"name": "环境", "level": 1, "strategy": "环境重构"},
    "behavior": {"name": "行为", "level": 2, "strategy": "行为预设"},
    "capability": {"name": "能力", "level": 3, "strategy": "能力突破"},
    "belief": {"name": "信念", "level": 4, "strategy": "信念重构"},
    "identity": {"name": "身份", "level": 5, "strategy": "身份重塑"},
    "spirit": {"name": "愿景", "level": 6, "strategy": "愿景唤醒"},
}

class CoachSkill(BaseSkill):
    @property
    def skill_type(self) -> SkillType: return SkillType.COACH
    @property
    def version(self) -> str: return "2.0.0"

    def validate(self, input_data: SkillInput) -> ValidationResult:
        mode = input_data.context.get("mode", "diagnose")
        if mode not in ("diagnose", "dialogue", "commitment", "motivation_similarity"):
            return ValidationResult(is_valid=False, errors=[f"无效模式: {mode}"])
        return ValidationResult(is_valid=True, errors=[])

    def estimate_cost(self, input_data: SkillInput) -> int:
        return {"diagnose":10,"dialogue":5,"commitment":5,"motivation_similarity":3}.get(input_data.context.get("mode","diagnose"),5)

    def get_required_skills(self) -> list[SkillType]: return [SkillType.MCKINSEY]

    async def execute(self, input_data: SkillInput) -> SkillOutput:
        mode = input_data.context.get("mode", "diagnose")
        if mode == "diagnose": return await self._diagnose(input_data)
        elif mode == "dialogue": return await self._dialogue(input_data)
        elif mode == "commitment": return await self._commitment(input_data)
        else: return await self._motivation(input_data)

    async def _diagnose(self, input_data):
        situation = input_data.context.get("situation", "")
        challenge = input_data.context.get("challenge", "")
        try:
            from app.utils.llm import get_llm_client
            r = await get_llm_client().chat([
                {"role":"system","content":"你是资深企业教练，擅长NLP神经逻辑层级6层诊断。只返回JSON。"},
                {"role":"user","content":f"""企业情况: {situation}
核心挑战: {challenge}
从6层诊断(环境/行为/能力/信念/身份/愿景)，判断企业卡在哪层:
返回JSON: {{"blocked_layer":"key","diagnosis":{{"environment":{{"status":"green/yellow/red","insight":"洞察"}},...}},"strategy":"策略","key_question":"教练提问"}}"""}
            ], temperature=0.5, max_tokens=2000)
            m = re.search(r'\{.*\}', r, re.DOTALL)
            if m: return SkillOutput(success=True, data=json.loads(m.group()), action_power_used=10, next_skill_hint=SkillType.MCKINSEY)
        except Exception as e: logger.warning(f"LLM diagnose fail: {e}")
        return SkillOutput(success=True, data={"blocked_layer":"capability","diagnosis":{k:{"status":"yellow","insight":"需LLM分析"} for k in COACHING_LAYERS},"strategy":"接入LLM","key_question":"你最大的能力瓶颈是什么?"}, action_power_used=10)

    async def _dialogue(self, input_data):
        message = input_data.context.get("message", "")
        history = input_data.context.get("history", [])
        try:
            from app.utils.llm import get_llm_client
            msgs = [{"role":"system","content":"你是资深企业教练。用提问引导深度思考，回答简洁有力，200字以内。"}]
            for h in history[-6:]:
                msgs.append({"role":"user","content":h.get("user","")})
                msgs.append({"role":"assistant","content":h.get("coach","")})
            msgs.append({"role":"user","content":message})
            r = await get_llm_client().chat(msgs, temperature=0.7, max_tokens=500)
            return SkillOutput(success=True, data={"response":r,"mode":"dialogue"}, action_power_used=5)
        except Exception as e: logger.warning(f"LLM dialogue fail: {e}")
        return SkillOutput(success=True, data={"response":"请描述您当前面临的具体挑战，我来帮您深入分析。","mode":"dialogue"}, action_power_used=5)

    async def _commitment(self, input_data):
        goal = input_data.context.get("goal", "")
        try:
            from app.utils.llm import get_llm_client
            r = await get_llm_client().chat([
                {"role":"system","content":"你是企业教练。帮用户制定SMART行动计划。返回JSON。"},
                {"role":"user","content":f"目标: {goal}\n制定SMART行动计划:\n返回: {{\"goal\":\"具体目标\",\"steps\":[\"步骤1\",\"步骤2\"],\"deadline\":\"时间线\",\"checkpoints\":[\"检查点\"]}}"}
            ], temperature=0.3, max_tokens=1000)
            m = re.search(r'\{.*\}', r, re.DOTALL)
            if m: return SkillOutput(success=True, data=json.loads(m.group()), action_power_used=5)
        except Exception as e: logger.warning(f"LLM commitment fail: {e}")
        return SkillOutput(success=True, data={"goal":goal,"steps":["请接入LLM获取个性化计划"],"deadline":"待定","checkpoints":[]}, action_power_used=5)

    async def _motivation(self, input_data):
        query = input_data.context.get("query", "")
        try:
            from app.utils.llm import get_llm_client
            r = await get_llm_client().chat([
                {"role":"system","content":"你是商业动机分析专家。返回JSON。"},
                {"role":"user","content":f"分析企业动机: {query}\n返回: {{\"primary_motivation\":\"\",\"secondary\":[\"\"],\"alignment_score\":0.8,\"suggestion\":\"\"}}"}
            ], temperature=0.3, max_tokens=500)
            m = re.search(r'\{.*\}', r, re.DOTALL)
            if m: return SkillOutput(success=True, data=json.loads(m.group()), action_power_used=3)
        except: pass
        return SkillOutput(success=True, data={"primary_motivation":"需LLM分析","secondary":[],"alignment_score":0.5,"suggestion":"请接入LLM"}, action_power_used=3)
