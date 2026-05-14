"""
商脉系统 — SKILL调度器 (SkillOrchestrator)

职责:
  - 管理技能注册表
  - 意图→SKILL映射 (技术规格 3.7)
  - 执行技能链 (顺序/条件/并行)
  - 处理技能间数据传递
  - SKILL联动矩阵 (技术规格 3.8)
  - 预算评估 + 大额确认
  - 错误处理与降级

参考技术规格样板 Chapter 3.7 & 3.8
"""
from typing import Optional, Callable
from app.skills.base import (
    BaseSkill, SkillType, SkillInput, SkillOutput
)
from app.skills.mckinsey_mece import McKinseyMeceSkill
from app.skills.mckinsey_seven_steps import McKinseySevenStepsSkill
from app.skills.role_match import RoleMatchSkill
from app.skills.industry_chain import IndustryChainSkill
from app.skills.coach import CoachSkill
from app.skills.secretary import SecretarySkill


# ============================================================
# 意图→SKILL映射 (技术规格 3.7)
# ============================================================
INTENT_SKILL_MAPPING: dict[str, SkillType] = {
    "精准匹配": SkillType.ROLE,
    "寻找伙伴": SkillType.ROLE,
    "找人": SkillType.ROLE,
    "问题拆解": SkillType.MCKINSEY,
    "策略规划": SkillType.MCKINSEY,
    "分析问题": SkillType.MCKINSEY,
    "产业链分析": SkillType.INDUSTRY_CHAIN,
    "合作评估": SkillType.INDUSTRY_CHAIN,
    "供应链": SkillType.INDUSTRY_CHAIN,
    "个人诊断": SkillType.COACH,
    "突破瓶颈": SkillType.COACH,
    "教练": SkillType.COACH,
    "困惑": SkillType.COACH,
    "查看进度": SkillType.GAMIFICATION,
    "破冰": SkillType.SECRETARY,
    "联络": SkillType.SECRETARY,
    "跟进": SkillType.SECRETARY,
    "秘书": SkillType.SECRETARY,
    "破冰方案": SkillType.SECRETARY,
    "联系": SkillType.SECRETARY,
}

# ============================================================
# SKILL联动矩阵 (技术规格 3.8)
# 行=调用方, 列=被调用方, 值=联动强度
# strong=强, medium=中, weak=弱, none=无
# ============================================================
SKILL_LINKAGE_MATRIX: dict[SkillType, dict[SkillType, str]] = {
    #           MCKINSEY    ROLE        INDUSTRY_CHAIN  GAMIFICATION  COACH
    SkillType.MCKINSEY: {
        SkillType.ROLE: "weak",
        SkillType.INDUSTRY_CHAIN: "medium",
        SkillType.GAMIFICATION: "medium",
        SkillType.COACH: "strong",
    },
    SkillType.ROLE: {
        SkillType.MCKINSEY: "weak",
        SkillType.INDUSTRY_CHAIN: "strong",
        SkillType.GAMIFICATION: "weak",
        SkillType.COACH: "medium",
    },
    SkillType.INDUSTRY_CHAIN: {
        SkillType.MCKINSEY: "medium",
        SkillType.ROLE: "strong",
        SkillType.GAMIFICATION: "medium",
        SkillType.COACH: "weak",
    },
    SkillType.GAMIFICATION: {
        SkillType.MCKINSEY: "weak",
        SkillType.ROLE: "weak",
        SkillType.INDUSTRY_CHAIN: "weak",
        SkillType.COACH: "weak",
    },
    SkillType.COACH: {
        SkillType.MCKINSEY: "strong",
        SkillType.ROLE: "medium",
        SkillType.INDUSTRY_CHAIN: "weak",
        SkillType.GAMIFICATION: "medium",
    },
}

# 强联动→自动构建执行链
STRONG_LINK_CHAINS: dict[SkillType, list[SkillType]] = {
    SkillType.MCKINSEY: [SkillType.COACH],         # 麦肯锡Step7→教练行动承诺
    SkillType.ROLE: [SkillType.INDUSTRY_CHAIN, SkillType.SECRETARY],  # 匹配→产业链→破冰
    SkillType.INDUSTRY_CHAIN: [SkillType.ROLE],   # 产业链→角色结构化复用
    SkillType.COACH: [SkillType.MCKINSEY, SkillType.SECRETARY],        # 教练→MECE→跟进
    SkillType.SECRETARY: [],                       # 商务秘书为终端节点
}

# 大额确认阈值
BUDGET_CONFIRM_THRESHOLD = 30


class SkillOrchestrator:
    """
    SKILL调度器 — 编排多个SKILL的执行顺序

    三种执行模式:
      1. execute_chain: 顺序执行，前一步输出传入后一步
      2. execute_with_condition: 条件分支，基于上一步结果决定
      3. execute_parallel: 并行执行，结果合并

    额外能力:
      - orchestrate(): 意图→SKILL映射→构建执行链→预算确认→顺序执行
      - 联动矩阵驱动的自动链式调用
      - 大额行动力确认(>30点)
    """

    def __init__(self):
        self._skills: dict[SkillType, BaseSkill] = {}
        self._register_default_skills()

    def _register_default_skills(self):
        """注册内置SKILL"""
        self.register(SkillType.MCKINSEY, McKinseyMeceSkill())
        self.register(SkillType.ROLE, RoleMatchSkill())
        self.register(SkillType.INDUSTRY_CHAIN, IndustryChainSkill())
        self.register(SkillType.COACH, CoachSkill())
        self.register(SkillType.SECRETARY, SecretarySkill())
        # 七步成诗法也属于MCKINSEY类型，通过sub_skill区分

    def register(self, skill_type: SkillType, skill: BaseSkill):
        """注册SKILL实例"""
        self._skills[skill_type] = skill

    def get_skill(self, skill_type: SkillType) -> Optional[BaseSkill]:
        """获取SKILL实例"""
        return self._skills.get(skill_type)

    # ============================================================
    # 意图解析与执行链构建 (技术规格 3.7)
    # ============================================================

    def map_intent_to_skill(self, intent: str) -> SkillType:
        """
        意图→SKILL映射

        基于关键词匹配，将自然语言意图映射到对应SKILL类型。
        未匹配时默认返回MCKINSEY（通用问题分析）。
        """
        for keyword, skill_type in INTENT_SKILL_MAPPING.items():
            if keyword in intent:
                return skill_type
        return SkillType.MCKINSEY

    def build_execution_chain(self, primary_skill: SkillType) -> list[SkillType]:
        """
        构建执行链 — BFS遍历SKILL依赖图

        从primary_skill出发，沿着强联动边构建执行序列。
        避免循环（已访问的不重复添加）。
        """
        chain = [primary_skill]
        visited = {primary_skill}
        queue = [primary_skill]

        while queue:
            current = queue.pop(0)
            next_skills = STRONG_LINK_CHAINS.get(current, [])
            for ns in next_skills:
                if ns not in visited:
                    chain.append(ns)
                    visited.add(ns)
                    queue.append(ns)

        return chain

    async def orchestrate(self, intent: str, context: SkillInput) -> SkillOutput:
        """
        完整编排流程 — 意图→映射→执行链→预算→执行

        1. 意图→SKILL映射
        2. 构建执行链（BFS遍历SKILL依赖图）
        3. 预算评估 + 大额确认
        4. 顺序执行链
        """
        # Step 1: 意图→SKILL映射
        primary_skill = self.map_intent_to_skill(intent)

        # Step 2: 构建执行链
        execution_chain = self.build_execution_chain(primary_skill)

        # Step 3: 预算评估
        total_cost = 0
        cost_breakdown = []
        for skill_type in execution_chain:
            skill = self._skills.get(skill_type)
            if skill:
                cost = skill.estimate_cost(context)
                total_cost += cost
                cost_breakdown.append({
                    "skill": skill_type.value,
                    "estimated_cost": cost
                })

        # 大额确认标记
        requires_budget_confirm = total_cost > BUDGET_CONFIRM_THRESHOLD

        # Step 4: 顺序执行链
        results = await self.execute_chain(execution_chain, context)

        # 汇总
        total_used = sum(r.action_power_used for r in results)
        all_data = {}
        for i, r in enumerate(results):
            all_data[execution_chain[i].value] = r.data

        return SkillOutput(
            success=all(r.success for r in results),
            data={
                "intent": intent,
                "primary_skill": primary_skill.value,
                "execution_chain": [s.value for s in execution_chain],
                "cost_breakdown": cost_breakdown,
                "total_estimated_cost": total_cost,
                "requires_budget_confirm": requires_budget_confirm,
                "results": all_data
            },
            action_power_used=total_used,
            next_skill_hint=results[-1].next_skill_hint if results else None
        )

    # ============================================================
    # 执行模式
    # ============================================================

    async def execute_single(
        self,
        skill_type: SkillType,
        input_data: SkillInput
    ) -> SkillOutput:
        """执行单个SKILL"""
        skill = self._skills.get(skill_type)
        if not skill:
            return SkillOutput(
                success=False,
                error_message=f"未注册的SKILL: {skill_type}"
            )
        return await skill.run(input_data)

    async def execute_chain(
        self,
        skill_types: list[SkillType],
        initial_input: SkillInput
    ) -> list[SkillOutput]:
        """
        顺序执行链 — 前一步的输出数据传入后一步的context

        示例: [ROLE, INDUSTRY_CHAIN, COACH]
        → ROLE的输出写入context → INDUSTRY_CHAIN读取 → COACH读取
        """
        results = []
        current_input = initial_input

        for skill_type in skill_types:
            skill = self._skills.get(skill_type)
            if not skill:
                results.append(SkillOutput(
                    success=False,
                    error_message=f"未注册的SKILL: {skill_type}"
                ))
                break

            output = await skill.run(current_input)
            results.append(output)

            if not output.success:
                break

            # 将输出数据传入下一步的context
            current_input = SkillInput(
                member_id=current_input.member_id,
                session_id=current_input.session_id,
                context={**current_input.context, **output.data, "prev_skill": skill_type.value}
            )

        return results

    async def execute_with_condition(
        self,
        skill_type: SkillType,
        input_data: SkillInput,
        condition_fn: Callable[[SkillOutput], Optional[SkillType]]
    ) -> tuple[SkillOutput, Optional[SkillOutput]]:
        """
        条件分支执行

        1. 执行主SKILL
        2. 基于condition_fn决定是否执行下一个SKILL
        3. 返回 (主结果, 条件结果)
        """
        main_output = await self.execute_single(skill_type, input_data)

        next_skill_type = condition_fn(main_output)
        conditional_output = None
        if next_skill_type:
            next_input = SkillInput(
                member_id=input_data.member_id,
                session_id=input_data.session_id,
                context={**input_data.context, **main_output.data}
            )
            conditional_output = await self.execute_single(next_skill_type, next_input)

        return main_output, conditional_output

    async def execute_parallel(
        self,
        skill_types: list[SkillType],
        input_data: SkillInput
    ) -> dict[SkillType, SkillOutput]:
        """
        并行执行多个SKILL，结果合并

        使用场景: 匹配算法中同时计算角色分+产业链分+教练分
        """
        import asyncio
        tasks = {}
        for skill_type in skill_types:
            skill = self._skills.get(skill_type)
            if skill:
                tasks[skill_type] = skill.run(input_data)

        results = {}
        if tasks:
            done = await asyncio.gather(*tasks.values(), return_exceptions=True)
            for (skill_type, _), result in zip(tasks.items(), done):
                if isinstance(result, Exception):
                    results[skill_type] = SkillOutput(
                        success=False,
                        error_message=f"执行异常: {str(result)}"
                    )
                else:
                    results[skill_type] = result

        return results

    async def execute_matching_pipeline(self, input_data: SkillInput) -> SkillOutput:
        """
        匹配Pipeline — 精准发现核心流程

        5步:
          1. ROLE SKILL → 角色供需匹配 (权重0.4)
          2. INDUSTRY_CHAIN SKILL → 产业链近邻度 (权重0.3)
          3. COACH SKILL → 动力同频度 (权重0.2)
          4. 综合评分 → total = role*0.4 + chain*0.3 + motivation*0.2 + activity*0.1
          5. 生成日报 → 包含Top5-10推荐
        """
        parallel_results = await self.execute_parallel(
            [SkillType.ROLE, SkillType.INDUSTRY_CHAIN, SkillType.COACH],
            input_data
        )

        role_result = parallel_results.get(SkillType.ROLE, SkillOutput(success=False, data={}))
        chain_result = parallel_results.get(SkillType.INDUSTRY_CHAIN, SkillOutput(success=False, data={}))
        coach_result = parallel_results.get(SkillType.COACH, SkillOutput(success=False, data={}))

        role_score = role_result.data.get("total_score", 0) * 0.4 if role_result.success else 0
        chain_score = chain_result.data.get("proximity_score", 0) * 0.3 if chain_result.success else 0
        motivation_score = coach_result.data.get("motivation_similarity", 0) * 0.2 if coach_result.success else 0
        activity_score = 0.05

        total = role_score + chain_score + motivation_score + activity_score

        return SkillOutput(
            success=True,
            data={
                "total_score": round(total, 4),
                "score_breakdown": {
                    "role_score": round(role_score, 4),
                    "chain_score": round(chain_score, 4),
                    "motivation_score": round(motivation_score, 4),
                    "activity_score": round(activity_score, 4)
                },
                "role_detail": role_result.data,
                "chain_detail": chain_result.data,
                "coach_detail": coach_result.data
            },
            action_power_used=15,
            next_skill_hint=None
        )

    def list_skills(self) -> list[dict]:
        """列出所有已注册的SKILL"""
        return [
            {
                "type": st.value,
                "version": skill.version,
                "estimated_cost": skill.estimate_cost(SkillInput(member_id="dummy")),
                "required_skills": [s.value for s in skill.get_required_skills()]
            }
            for st, skill in self._skills.items()
        ]

    def get_linkage_matrix(self) -> dict:
        """获取SKILL联动矩阵（用于调试和展示）"""
        return {
            caller.value: {callee.value: strength for callee, strength in linkages.items()}
            for caller, linkages in SKILL_LINKAGE_MATRIX.items()
        }


# 全局单例
async def orchestrate_dragon_chain(self, intent: str, context: SkillInput, member_profile: dict = None) -> SkillOutput:
        """
        四小龙协同链 — 完整商业智能分析流程
        
        链路: COACH(诊断) → INDUSTRY_CHAIN(产业链) → ROLE(匹配) → SECRETARY(破冰/跟进)
        
        每一步的输出会传入下一步的context，形成完整的推理链。
        """
        # Phase 1: 教练诊断 — 理解企业现状和瓶颈
        coach_input = SkillInput(
            member_id=context.member_id,
            session_id=context.session_id,
            context={**context.context, "mode": "diagnose", 
                     "situation": member_profile.get("situation", "") if member_profile else "",
                     "challenge": member_profile.get("challenge", "") if member_profile else ""}
        )
        coach_result = await self.execute_single(SkillType.COACH, coach_input)
        
        # Phase 2: 产业链分析 — 基于诊断结果分析协作潜力
        chain_input = SkillInput(
            member_id=context.member_id,
            session_id=context.session_id,
            context={**context.context, 
                     "coach_diagnosis": coach_result.data if coach_result.success else {},
                     "member_ids": context.context.get("member_ids", [context.member_id]),
                     "mode": "full"}
        )
        chain_result = await self.execute_single(SkillType.INDUSTRY_CHAIN, chain_input)
        
        # Phase 3: 精准匹配 — 结合诊断和产业链信息做匹配
        role_input = SkillInput(
            member_id=context.member_id,
            session_id=context.session_id,
            context={**context.context,
                     "coach_insight": coach_result.data.get("strategy", "") if coach_result.success else "",
                     "chain_insight": chain_result.data.get("top3", []) if chain_result.success else [],
                     "mode": "pipeline",
                     "intent": intent}
        )
        role_result = await self.execute_single(SkillType.ROLE, role_input)
        
        # Phase 4: 商务秘书 — 生成破冰方案和跟进计划
        sec_input = SkillInput(
            member_id=context.member_id,
            session_id=context.session_id,
            context={**context.context,
                     "match_results": role_result.data if role_result.success else {},
                     "coach_blocked_layer": coach_result.data.get("blocked_layer", "") if coach_result.success else "",
                     "mode": "icebreak"}
        )
        sec_result = await self.execute_single(SkillType.SECRETARY, sec_input)
        
        # 汇总四小龙协同结果
        total_cost = sum(r.action_power_used for r in [coach_result, chain_result, role_result, sec_result])
        
        return SkillOutput(
            success=all(r.success for r in [coach_result, chain_result, role_result, sec_result]),
            data={
                "chain_type": "dragon_four_synergy",
                "phase_results": {
                    "coach_diagnosis": coach_result.data if coach_result.success else {"error": coach_result.error_message},
                    "industry_chain": chain_result.data if chain_result.success else {"error": chain_result.error_message},
                    "role_match": role_result.data if role_result.success else {"error": role_result.error_message},
                    "secretary_action": sec_result.data if sec_result.success else {"error": sec_result.error_message},
                },
                "total_action_power": total_cost,
                "summary": {
                    "blocked_at": coach_result.data.get("blocked_layer", "unknown") if coach_result.success else None,
                    "top_collaboration_dims": chain_result.data.get("top3", []) if chain_result.success else [],
                    "best_matches": len(role_result.data.get("primary_results", [])) if role_result.success else 0,
                    "icebreak_ready": sec_result.success,
                }
            },
            action_power_used=total_cost,
        )
orchestrator = SkillOrchestrator()
