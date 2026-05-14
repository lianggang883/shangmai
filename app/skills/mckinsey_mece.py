"""
商脉系统 · 麦肯锡MECE SKILL (v2.0 - LLM驱动)
"""
import json, re, logging
from typing import Optional
from app.skills.base import BaseSkill, SkillType, SkillInput, SkillOutput, ValidationResult

logger = logging.getLogger(__name__)

MECE_FRAMEWORKS = {
    "industry_chain": {"name": "产业链MECE", "dimensions": ["上游供应端", "中游生产端", "中游流通端", "终端客户"]},
    "organizational": {"name": "组织能力MECE", "dimensions": ["战略规划", "运营管理", "人才发展", "财务管控", "市场拓展"]},
    "market": {"name": "市场结构MECE", "dimensions": ["现有市场", "新兴市场", "替代市场", "潜在市场"]},
    "financial": {"name": "财务结构MECE", "dimensions": ["收入来源", "成本结构", "资产效率", "现金流"]},
}

class MeceInput(SkillInput):
    problem: str = ""
    framework_hint: Optional[str] = None
    max_branches: int = 7

class McKinseyMeceSkill(BaseSkill):
    @property
    def skill_type(self) -> SkillType: return SkillType.MCKINSEY
    @property
    def version(self) -> str: return "2.0.0"

    def validate(self, input_data: SkillInput) -> ValidationResult:
        mi = MeceInput(**input_data.model_dump())
        errors = []
        if not mi.problem or len(mi.problem.strip()) < 5: errors.append("问题至少5字")
        return ValidationResult(is_valid=len(errors)==0, errors=errors)

    def estimate_cost(self, input_data: SkillInput) -> int: return 8
    def get_required_skills(self) -> list[SkillType]: return [SkillType.INDUSTRY_CHAIN]

    async def execute(self, input_data: SkillInput) -> SkillOutput:
        mi = MeceInput(**input_data.model_dump())
        suitability = await self._assess_suitability(mi.problem, mi.context)
        if suitability["score"] < 0.3:
            return SkillOutput(success=False, data={"suitability": suitability, "reason": "不适合MECE"}, action_power_used=2, next_skill_hint=SkillType.COACH)
        framework = await self._select_framework(mi.problem, mi.context, mi.framework_hint)
        branches = await self._decompose(mi.problem, framework)
        validation = self._validate_mece(branches)
        retry = 0
        while not validation["is_mece"] and retry < 2:
            branches = await self._repair(mi.problem, branches, validation["issues"])
            validation = self._validate_mece(branches)
            retry += 1
        weighted = self._assign_weights(branches, mi.context)
        return SkillOutput(success=True, data={"framework": framework["name"], "branches": weighted, "completeness_check": validation["summary"], "suitability": suitability, "retry_count": retry}, action_power_used=8, next_skill_hint=SkillType.INDUSTRY_CHAIN)

    async def _assess_suitability(self, problem, context):
        try:
            from app.utils.llm import get_llm_client
            r = await get_llm_client().chat([
                {"role": "system", "content": "判断问题是否适合MECE拆解。返回JSON: {\"score\":0.0-1.0,\"reason\":\"原因\"}"},
                {"role": "user", "content": f"问题: {problem}"}
            ], temperature=0.3, max_tokens=200)
            m = re.search(r'\{[^}]+\}', r)
            if m: return json.loads(m.group())
        except Exception as e: logger.warning(f"LLM assess fail: {e}")
        score = 0.5
        if any(k in problem for k in ["如何","怎么","哪些"]): score += 0.2
        return {"score": min(score,1.0), "reason": "rule_assessed"}

    async def _select_framework(self, problem, context, hint=None):
        if hint and hint in MECE_FRAMEWORKS: return MECE_FRAMEWORKS[hint]
        try:
            from app.utils.llm import get_llm_client
            fwn = ", ".join(f"{k}:{v['name']}" for k,v in MECE_FRAMEWORKS.items())
            r = await get_llm_client().chat([
                {"role": "system", "content": "选择最适合的MECE框架。只返回框架key。"},
                {"role": "user", "content": f"可选: {fwn}\n问题: {problem}\n返回key:"}
            ], temperature=0.1, max_tokens=30)
            for k in MECE_FRAMEWORKS:
                if k in r.lower(): return MECE_FRAMEWORKS[k]
        except: pass
        return MECE_FRAMEWORKS["industry_chain"]

    async def _decompose(self, problem, framework):
        try:
            from app.utils.llm import get_llm_client
            r = await get_llm_client().chat([
                {"role": "system", "content": "你是麦肯锡MECE分析专家。只返回JSON数组。"},
                {"role": "user", "content": f"""对以下问题进行MECE拆解:
问题: {problem}
框架: {framework['name']}
维度: {', '.join(framework.get('dimensions',[]))}

返回JSON数组:
[{{"id":"branch_1","name":"维度","sub_items":["子项1","子项2"],"weight":0.25,"analysis":"分析"}}]"""}
            ], temperature=0.3, max_tokens=2000)
            m = re.search(r'\[.*\]', r, re.DOTALL)
            if m:
                branches = json.loads(m.group())
                for i,b in enumerate(branches):
                    b.setdefault("id",f"branch_{i+1}"); b.setdefault("sub_items",[]); b.setdefault("weight",0); b.setdefault("analysis","")
                return branches
        except Exception as e: logger.warning(f"LLM decompose fail: {e}")
        return [{"id":f"branch_{i+1}","name":d,"sub_items":[],"weight":0,"analysis":""} for i,d in enumerate(framework.get("dimensions",[]))]

    def _validate_mece(self, branches):
        issues = []
        subs = [s for b in branches for s in b.get("sub_items",[])]
        if len(subs) != len(set(subs)): issues.append("子项重叠")
        if len(branches) < 3: issues.append("分支不足3个")
        empty = [b["id"] for b in branches if not b.get("sub_items")]
        if empty: issues.append(f"空分支: {', '.join(empty)}")
        ok = len(issues)==0
        return {"is_mece":ok, "issues":issues, "summary":"MECE通过" if ok else f"未通过: {'; '.join(issues)}"}
        return [{"id":"branch_1","name":"默认分支","sub_items":[],"weight":1.0,"analysis":"LLM调用失败，使用默认分支"}]

    async def _repair(self, problem, branches, issues):
        try:
            from app.utils.llm import get_llm_client
            empty = [b["name"] for b in branches if not b.get("sub_items")]
            if empty:
                r = await get_llm_client().chat([
                    {"role":"system","content":"为空分支补充子项。返回JSON数组。"},
                    {"role":"user","content":f"问题:{problem}\n空分支:{','.join(empty)}\n返回:[{{\"name\":\"分支名\",\"sub_items\":[\"子项\"]}}]"}
                ], temperature=0.3, max_tokens=500)
                m = re.search(r'\[.*\]', r, re.DOTALL)
                if m:
                    repairs = {r2["name"]:r2.get("sub_items",[]) for r2 in json.loads(m.group())}
                    for b in branches:
                        if not b.get("sub_items") and b["name"] in repairs: b["sub_items"] = repairs[b["name"]]
                    return branches
        except: pass
        for b in branches:
            if not b.get("sub_items"): b["sub_items"] = [f"{b['name']}_方向1", f"{b['name']}_方向2"]
        return branches

    def _assign_weights(self, branches, context):
        if not any(b.get("weight",0)>0 for b in branches):
            for b in branches: b["weight"] = round(1.0/len(branches),2)
        branches.sort(key=lambda x: x.get("weight",0), reverse=True)
        return branches
