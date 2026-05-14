"""
商脉系统 — 十维角色匹配 SKILL (v2.0)

基于匹配Pipeline的角色匹配SKILL，替换原有的随机向量实现。
核心变更：
  - 使用 affinity_matrix 的10×10角色关联场权重矩阵替代随机嵌入
  - 调用 MatchingPipeline 完成完整匹配流程（初筛→精筛→二度推荐）
  - 保留原有SKILL接口兼容性

5步流程 (v2.0):
  1. 角色向量化 → 关联场权重矩阵调制，768维嵌入空间
  2. 供需对齐 → 基于关联场矩阵的PROVIDE-SEEK互补计算
  3. 产业链校验 → 调用INDUSTRY_CHAIN SKILL
  4. 教练调优 → 调用COACH SKILL (动力同频度)
  5. 活跃度信任 → 等级+互动+签到三维评分

评分公式:
  total = provide_seek_score * 0.4
       + seek_provide_score * 0.3
       + chain_score * 0.3
       + motivation_score * 0.2
       + activity_trust_score * 0.1

参考技术规格样板 Chapter 3.4 & 4.2
"""
from app.skills.base import (
    BaseSkill, SkillType, SkillInput, SkillOutput, ValidationResult
)
from app.services.matching.affinity_matrix import (
    ROLE_CODES,
    ROLE_INDEX,
    ROLE_AFFINITY_MATRIX,
    get_affinity,
    cosine_similarity,
    vectorize_member_roles,
)
from app.services.matching import MatchingPipeline


class RoleMatchSkill(BaseSkill):
    """
    十维角色匹配 SKILL v2.0 — 基于匹配Pipeline的精准发现

    核心变更：
      - 使用10×10角色关联场权重矩阵替代随机向量
      - 调用MatchingPipeline完成完整匹配流程
      - 保留SKILL接口兼容性

    行动力消耗: 15点 (完整Pipeline) / 5点 (单对评分)
    下游SKILL: INDUSTRY_CHAIN, COACH
    """

    def __init__(self, member_repo=None, relation_repo=None, skill_orchestrator=None):
        """
        初始化角色匹配SKILL

        Args:
            member_repo: 会员数据仓库
            relation_repo: 关系数据仓库
            skill_orchestrator: SKILL调度器
        """
        self._pipeline = MatchingPipeline(
            member_repo=member_repo,
            relation_repo=relation_repo,
            skill_orchestrator=skill_orchestrator,
        )
        self._member_repo = member_repo
        self._skill_orchestrator = skill_orchestrator

    @property
    def skill_type(self) -> SkillType:
        """技能类型标识"""
        return SkillType.ROLE

    @property
    def version(self) -> str:
        """技能版本号"""
        return "2.0.0"

    def validate(self, input_data: SkillInput) -> ValidationResult:
        """
        输入校验

        支持两种模式：
          - pipeline模式: 需要 member_id + intent
          - pair模式: 需要 member_a_id + member_b_id
        """
        errors = []
        mode = input_data.context.get("mode", "pipeline")

        if mode == "pipeline":
            if not input_data.member_id:
                errors.append("缺少member_id")
            if not input_data.context.get("intent"):
                errors.append("缺少intent（匹配意图）")
        elif mode == "pair":
            if not input_data.context.get("member_a_id"):
                errors.append("缺少member_a_id")
            if not input_data.context.get("member_b_id"):
                errors.append("缺少member_b_id")
        else:
            errors.append(f"无效的匹配模式: {mode}")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors)

    def estimate_cost(self, input_data: SkillInput) -> int:
        """
        预估行动力消耗

        pipeline模式: 15点（完整三阶段匹配）
        pair模式: 5点（单对评分）
        """
        mode = input_data.context.get("mode", "pipeline")
        return 15 if mode == "pipeline" else 5

    def get_required_skills(self) -> list[SkillType]:
        """声明依赖的其他SKILL"""
        return [SkillType.INDUSTRY_CHAIN, SkillType.COACH]

    async def execute(self, input_data: SkillInput) -> SkillOutput:
        """
        核心执行方法

        根据模式分发到不同的匹配逻辑：
          - pipeline模式: 调用MatchingPipeline完成全量匹配
          - pair模式: 对指定两人计算匹配评分
        """
        mode = input_data.context.get("mode", "pipeline")

        if mode == "pipeline":
            return await self._execute_pipeline(input_data)
        elif mode == "pair":
            return await self._execute_pair(input_data)
        else:
            return SkillOutput(
                success=False,
                error_message=f"无效的匹配模式: {mode}",
            )

    # ── Pipeline模式：全量匹配 ────────────────────────

    async def _execute_pipeline(self, input_data: SkillInput) -> SkillOutput:
        """
        Pipeline模式：调用MatchingPipeline完成完整匹配流程

        Args:
            input_data: 包含 member_id 和 intent 的输入

        Returns:
            匹配结果，含初筛→精筛→二度推荐的完整输出
        """
        member_id = input_data.member_id
        intent = input_data.context.get("intent", {})
        top_k = input_data.context.get("top_k", 10)
        include_second_degree = input_data.context.get(
            "include_second_degree", True
        )

        try:
            result = await self._pipeline.trigger_matching(
                member_id=member_id,
                intent=intent,
                top_k=top_k,
                include_second_degree=include_second_degree,
            )

            # 生成AI推荐原因
            for candidate in result.get("primary_results", []):
                if "ai_reason" not in candidate:
                    candidate["ai_reason"] = self._generate_ai_reason(
                        candidate
                    )

            for candidate in result.get("second_degree_results", []):
                if "ai_reason" not in candidate:
                    candidate["ai_reason"] = candidate.get(
                        "recommendation_reason", "二度关系推荐"
                    )

            return SkillOutput(
                success=True,
                data=result,
                action_power_used=15,
                next_skill_hint=SkillType.INDUSTRY_CHAIN,
            )

        except Exception as e:
            return SkillOutput(
                success=False,
                error_message=f"Pipeline匹配异常: {str(e)}",
                action_power_used=0,
            )

    # ── Pair模式：单对评分 ────────────────────────────

    async def _execute_pair(self, input_data: SkillInput) -> SkillOutput:
        """
        Pair模式：对指定两人计算匹配评分

        使用角色关联场权重矩阵计算供需互补度，
        并调用产业链和教练SKILL获取协作分和动力同频度。

        Args:
            input_data: 包含 member_a_id 和 member_b_id 的输入

        Returns:
            两人的详细匹配评分
        """
        member_a = input_data.context["member_a_id"]
        member_b = input_data.context["member_b_id"]

        # Step 1: 角色向量化 — 使用关联场权重矩阵调制
        roles_a = await self._get_member_roles(member_a)
        roles_b = await self._get_member_roles(member_b)

        vec_provide_a, vec_seek_a = vectorize_member_roles(
            roles_a.get("provide", []), roles_a.get("seek", [])
        )
        vec_provide_b, vec_seek_b = vectorize_member_roles(
            roles_b.get("provide", []), roles_b.get("seek", [])
        )

        # Step 2: 供需对齐 — 基于关联场矩阵
        provide_seek_score = self._compute_provide_seek_from_matrix(
            roles_a, roles_b
        )

        # Step 3: 行为增强 — 基于历史互动调整
        interaction_boost = await self._behavior_enhancement(member_a, member_b)
        enhanced_score = (
            provide_seek_score["provide_seek"] * 0.4
            + provide_seek_score["seek_provide"] * 0.3
        ) * interaction_boost

        # Step 4: 产业链校验
        chain_score = await self._call_industry_chain(member_a, member_b)
        chain_weighted = chain_score * 0.3

        # Step 5: 教练调优
        motivation_score = await self._call_coach_motivation(member_a, member_b)
        motivation_weighted = motivation_score * 0.2

        # 活跃度信任分
        activity_trust_a = await self._compute_activity_trust(member_a)
        activity_trust_b = await self._compute_activity_trust(member_b)
        activity_trust = (activity_trust_a + activity_trust_b) / 2 * 0.1

        # 综合评分
        total = enhanced_score + chain_weighted + motivation_weighted + activity_trust

        # 角色匹配详情
        role_match_details = self._generate_match_details(
            roles_a, roles_b, provide_seek_score
        )

        return SkillOutput(
            success=True,
            data={
                "member_a": member_a,
                "member_b": member_b,
                "total_score": round(total, 4),
                "score_breakdown": {
                    "provide_seek_score": round(
                        provide_seek_score["provide_seek"], 4
                    ),
                    "seek_provide_score": round(
                        provide_seek_score["seek_provide"], 4
                    ),
                    "interaction_boost": round(interaction_boost, 4),
                    "enhanced_score": round(enhanced_score, 4),
                    "chain_score": round(chain_weighted, 4),
                    "motivation_score": round(motivation_weighted, 4),
                    "activity_trust_score": round(activity_trust, 4),
                },
                "role_match_details": role_match_details,
            },
            action_power_used=5,
            next_skill_hint=SkillType.INDUSTRY_CHAIN,
        )

    # ── 角色匹配核心计算 ──────────────────────────────

    def _compute_provide_seek_from_matrix(
        self, roles_a: dict, roles_b: dict
    ) -> dict:
        """
        基于关联场矩阵计算供需互补度

        替代原有的余弦相似度计算，直接使用10×10矩阵查表。

        Args:
            roles_a: 会员A的角色 {"provide": [...], "seek": [...]}
            roles_b: 会员B的角色

        Returns:
            {"provide_seek": float, "seek_provide": float}
        """
        # A的PROVIDE ↔ B的SEEK
        provide_seek_scores = []
        for sp in roles_a.get("provide", []):
            for ts in roles_b.get("seek", []):
                try:
                    w = get_affinity(sp, ts)
                    provide_seek_scores.append(w)
                except ValueError:
                    continue

        # A的SEEK ↔ B的PROVIDE
        seek_provide_scores = []
        for ss in roles_a.get("seek", []):
            for tp in roles_b.get("provide", []):
                try:
                    w = get_affinity(tp, ss)  # PROVIDE是行
                    seek_provide_scores.append(w)
                except ValueError:
                    continue

        provide_seek = (
            sum(provide_seek_scores) / len(provide_seek_scores)
            if provide_seek_scores
            else 0.0
        )
        seek_provide = (
            sum(seek_provide_scores) / len(seek_provide_scores)
            if seek_provide_scores
            else 0.0
        )

        return {"provide_seek": provide_seek, "seek_provide": seek_provide}

    # ── 行为增强 ──────────────────────────────────────

    async def _behavior_enhancement(
        self, member_a: str, member_b: str
    ) -> float:
        """
        行为增强 — 基于历史互动调整匹配分

        有互动记录 → boost > 1.0 (最高1.3)
        无互动记录 → boost = 1.0
        负面反馈   → boost < 1.0 (最低0.7)
        """
        # TODO: 查询interactions表
        return 1.0  # 默认无增强

    # ── 产业链SKILL调用 ──────────────────────────────

    async def _call_industry_chain(
        self, member_a: str, member_b: str
    ) -> float:
        """调用产业链SKILL获取近邻度评分"""
        if self._skill_orchestrator is not None:
            try:
                result = await self._skill_orchestrator.invoke(
                    "INDUSTRY_CHAIN",
                    {
                        "member_ids": [member_a, member_b],
                        "mode": "proximity",
                    },
                )
                if result and result.success:
                    return result.data.get("proximity_score", 0.3)
            except Exception:
                pass
        return 0.3  # 默认中等产业链关联

    # ── 教练SKILL调用 ────────────────────────────────

    async def _call_coach_motivation(
        self, member_a: str, member_b: str
    ) -> float:
        """调用教练SKILL获取动力同频度 (权重0.2)"""
        if self._skill_orchestrator is not None:
            try:
                result = await self._skill_orchestrator.invoke(
                    "COACH",
                    {
                        "mode": "motivation_similarity",
                        "member_a_id": member_a,
                        "member_b_id": member_b,
                    },
                )
                if result and result.success:
                    return result.data.get("motivation_similarity", 0.15)
            except Exception:
                pass
        return 0.15  # 默认低动力同频

    # ── 活跃度信任分 ──────────────────────────────────

    async def _compute_activity_trust(self, member_id: str) -> float:
        """
        计算活跃度信任分

        公式: 0.4 * (level/6) + 0.3 * min(interactions_30d/20, 1)
             + 0.3 * (checkin_streak/30)
        """
        level = 1
        interactions_30d = 0
        checkin_streak = 0

        if self._member_repo is not None:
            try:
                activity = await self._member_repo.get_member_activity(member_id)
                level = activity.get("level", 1)
                interactions_30d = activity.get("interactions_30d", 0)
                checkin_streak = activity.get("checkin_streak", 0)
            except Exception:
                pass

        return min(
            0.4 * (level / 6)
            + 0.3 * min(interactions_30d / 20, 1)
            + 0.3 * (checkin_streak / 30),
            1.0,
        )

    # ── 数据获取 ──────────────────────────────────────

    async def _get_member_roles(self, member_id: str) -> dict:
        """
        获取会员角色信息

        Args:
            member_id: 会员ID

        Returns:
            {"provide": ["partner", ...], "seek": ["customer", ...]}
        """
        if self._member_repo is not None:
            try:
                return await self._member_repo.get_member_roles(member_id)
            except Exception:
                pass
        return {"provide": [], "seek": []}

    # ── 详情生成 ──────────────────────────────────────

    def _generate_match_details(
        self,
        roles_a: dict,
        roles_b: dict,
        provide_seek_score: dict,
    ) -> dict:
        """
        生成可读的角色匹配详情

        Args:
            roles_a: 会员A角色
            roles_b: 会员B角色
            provide_seek_score: 供需互补分

        Returns:
            匹配详情字典
        """
        provide_seek = provide_seek_score.get("provide_seek", 0)
        seek_provide = provide_seek_score.get("seek_provide", 0)

        # 找出最佳匹配角色对
        best_match_pairs = []
        for sp in roles_a.get("provide", []):
            for ts in roles_b.get("seek", []):
                try:
                    w = get_affinity(sp, ts)
                    if w > 0.6:
                        best_match_pairs.append(
                            f"您提供{sp}↔对方需要{ts}({w:.2f})"
                        )
                except ValueError:
                    continue

        for ss in roles_a.get("seek", []):
            for tp in roles_b.get("provide", []):
                try:
                    w = get_affinity(tp, ss)
                    if w > 0.6:
                        best_match_pairs.append(
                            f"您需要{ss}↔对方提供{tp}({w:.2f})"
                        )
                except ValueError:
                    continue

        return {
            "complementarity": round(provide_seek, 4),
            "similarity": round(seek_provide, 4),
            "match_type": "互补型" if provide_seek > seek_provide else "同质型",
            "best_match_pairs": best_match_pairs[:5],
            "recommendation": (
                "建议优先在供需互补维度展开合作"
                if provide_seek > 0.5
                else "角色互补度偏低，建议关注产业链协作和动力同频维度"
            ),
        }

    def _generate_ai_reason(self, candidate: dict) -> str:
        """
        为Pipeline模式结果生成AI推荐原因

        Args:
            candidate: 候选人匹配结果

        Returns:
            AI推荐原因字符串
        """
        reasons = candidate.get("match_reasons", [])
        score = candidate.get("total_score", 0)

        if not reasons:
            if score > 0.7:
                return "综合匹配度高，建议优先联系"
            elif score > 0.4:
                return "有一定匹配度，值得关注"
            else:
                return "匹配度一般，可酌情了解"

        # 取前2个匹配原因组合
        top_reasons = reasons[:2]
        if score > 0.7:
            prefix = "高度匹配："
        elif score > 0.4:
            prefix = "值得关注："
        else:
            prefix = "潜在机会："

        return prefix + "、".join(top_reasons)
