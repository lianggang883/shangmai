"""
商脉系统 — 精筛Top-K算法

实现技术规格 4.4 的精筛算法，对初筛候选人进行四维评分并排序：
  维度1: 基础匹配分 (权重0.4+0.3) — PROVIDE-SEEK互补对齐
  维度2: 产业链协作分 (权重0.3) — 产业链近邻度
  维度3: 动力同频度 (权重0.2) — 教练六层次匹配
  维度4: 活跃度信任分 (权重0.1) — 等级+互动+签到

活跃度信任分公式:
  activity_trust = 0.4 * (level / 6)
                 + 0.3 * min(interactions_30d / 20, 1)
                 + 0.3 * (checkin_streak / 30)

参考技术规格样板 Chapter 4.4
"""

import math
from typing import Optional

from app.services.matching.affinity_matrix import (
    ROLE_CODES,
    ROLE_INDEX,
    ROLE_AFFINITY_MATRIX,
    get_affinity,
    cosine_similarity,
    vectorize_member_roles,
)


class FineMatcher:
    """
    精筛Top-K排序器 — 四维评分精排

    对初筛通过的候选人进行精确评分，返回Top-K排序结果。
    每个维度独立计算0-1分值，按权重加权求和得到总分。

    评分公式：
      total = provide_seek_score * 0.4
            + seek_provide_score * 0.3
            + chain_score * 0.3
            + motivation_score * 0.2
            + activity_trust_score * 0.1
    """

    def __init__(self, member_repo=None, skill_orchestrator=None):
        """
        初始化精筛器

        Args:
            member_repo: 会员数据仓库接口，需实现：
                - get_member_roles(member_id) -> dict
                - get_member_industry_info(member_id) -> dict
                - get_member_coach_diagnosis(member_id) -> dict
                - get_member_activity(member_id) -> dict
                - get_member_interaction_count(member_a, member_b, days) -> int
            skill_orchestrator: SKILL调度器，用于调用产业链和教练SKILL
        """
        self._member_repo = member_repo
        self._skill_orchestrator = skill_orchestrator

    # ── 公开接口 ──────────────────────────────────────

    async def fine_rank(
        self,
        source_member_id: str,
        candidates: list[dict],
        intent: dict,
        top_k: int = 10,
    ) -> list[dict]:
        """
        对候选人进行精筛评分并返回Top-K

        Args:
            source_member_id: 发起匹配的会员ID
            candidates: 初筛通过的候选人列表，每项需含 member_id
            intent: 匹配意图
            top_k: 返回的最大候选人数

        Returns:
            按总分降序排列的Top-K候选人列表，每项含:
            {
                "member_id": str,
                "total_score": float,
                "score_breakdown": {
                    "provide_seek_score": float,   # 0-1, 权重0.4
                    "seek_provide_score": float,   # 0-1, 权重0.3
                    "chain_score": float,          # 0-1, 权重0.3
                    "motivation_score": float,     # 0-1, 权重0.2
                    "activity_trust_score": float, # 0-1, 权重0.1
                },
                "match_reasons": list[str],
                "role_match_tags": list[str],
            }
        """
        if not candidates:
            return []

        # 获取发起人的角色信息
        source_roles = await self._get_member_roles(source_member_id)

        # 逐候选人评分
        scored_candidates = []
        for candidate in candidates:
            target_id = candidate["member_id"]
            scores = await self._score_candidate(
                source_member_id, source_roles, target_id, intent, candidate
            )
            scored_candidates.append({
                **candidate,
                "total_score": scores["total_score"],
                "score_breakdown": scores["breakdown"],
                "match_reasons": scores["reasons"],
            })

        # 按 total_score 降序排序
        scored_candidates.sort(key=lambda x: x["total_score"], reverse=True)

        return scored_candidates[:top_k]

    # ── 四维评分 ──────────────────────────────────────

    async def _score_candidate(
        self,
        source_id: str,
        source_roles: dict,
        target_id: str,
        intent: dict,
        candidate: dict,
    ) -> dict:
        """
        对单个候选人进行四维评分

        Args:
            source_id: 发起人ID
            source_roles: 发起人角色信息
            target_id: 候选人ID
            intent: 匹配意图
            candidate: 候选人基础信息

        Returns:
            {
                "total_score": float,
                "breakdown": {
                    "provide_seek_score": float,
                    "seek_provide_score": float,
                    "chain_score": float,
                    "motivation_score": float,
                    "activity_trust_score": float,
                },
                "reasons": list[str],
            }
        """
        # 获取候选人角色
        target_roles = await self._get_member_roles(target_id)

        # 维度1: 基础匹配分 — PROVIDE-SEEK互补
        provide_seek_score = self._compute_provide_seek_score(
            source_roles, target_roles
        )

        # 维度2: 产业链协作分
        chain_score = await self._compute_chain_score(
            source_id, target_id, intent
        )

        # 维度3: 动力同频度
        motivation_score = await self._compute_motivation_score(
            source_id, target_id
        )

        # 维度4: 活跃度信任分
        activity_trust_score = await self._compute_activity_trust_score(target_id)

        # 加权求和
        total_score = (
            provide_seek_score["provide_seek"] * 0.4
            + provide_seek_score["seek_provide"] * 0.3
            + chain_score * 0.3
            + motivation_score * 0.2
            + activity_trust_score * 0.1
        )

        # 生成匹配原因
        reasons = self._generate_match_reasons(
            provide_seek_score, chain_score, motivation_score, activity_trust_score
        )

        return {
            "total_score": round(total_score, 4),
            "breakdown": {
                "provide_seek_score": round(provide_seek_score["provide_seek"], 4),
                "seek_provide_score": round(provide_seek_score["seek_provide"], 4),
                "chain_score": round(chain_score, 4),
                "motivation_score": round(motivation_score, 4),
                "activity_trust_score": round(activity_trust_score, 4),
            },
            "reasons": reasons,
        }

    def _compute_provide_seek_score(
        self, source_roles: dict, target_roles: dict
    ) -> dict:
        """
        维度1: 基础匹配分 — PROVIDE-SEEK互补对齐

        计算逻辑：
          provide_seek: 发起人的PROVIDE角色与候选人的SEEK角色的关联场权重
          seek_provide: 发起人的SEEK角色与候选人的PROVIDE角色的关联场权重

        使用角色关联场矩阵查表，取所有角色对的最高权重。

        Args:
            source_roles: 发起人角色 {"provide": [...], "seek": [...]}
            target_roles: 候选人角色 {"provide": [...], "seek": [...]}

        Returns:
            {"provide_seek": float, "seek_provide": float}
        """
        source_provide = source_roles.get("provide", [])
        source_seek = source_roles.get("seek", [])
        target_provide = target_roles.get("provide", [])
        target_seek = target_roles.get("seek", [])

        # 发起人PROVIDE ↔ 候选人SEEK
        provide_seek_scores = []
        for sp in source_provide:
            for ts in target_seek:
                try:
                    w = get_affinity(sp, ts)
                    provide_seek_scores.append(w)
                except ValueError:
                    continue

        # 发起人SEEK ↔ 候选人PROVIDE
        seek_provide_scores = []
        for ss in source_seek:
            for tp in target_provide:
                try:
                    w = get_affinity(tp, ss)  # 注意：PROVIDE是行
                    seek_provide_scores.append(w)
                except ValueError:
                    continue

        # 取最高权重（最佳匹配对）的平均值
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

    async def _compute_chain_score(
        self, source_id: str, target_id: str, intent: dict
    ) -> float:
        """
        维度2: 产业链协作分

        通过产业链SKILL或分区信息计算两人的产业链近邻度。
        同分区 = 高分(0.8-1.0)，近邻分区 = 中分(0.4-0.7)，
        无关联 = 低分(0.0-0.3)。

        Args:
            source_id: 发起人ID
            target_id: 候选人ID
            intent: 匹配意图

        Returns:
            产业链协作分 [0, 1]
        """
        if self._skill_orchestrator is not None:
            # 调用产业链SKILL获取精确评分
            try:
                result = await self._skill_orchestrator.invoke(
                    "INDUSTRY_CHAIN",
                    {
                        "member_ids": [source_id, target_id],
                        "mode": "proximity",
                    },
                )
                if result and result.success:
                    return result.data.get("proximity_score", 0.3)
            except Exception:
                pass

        # 降级：基于意图中的分区信息估算
        my_zone = intent.get("industry_zone", "")
        neighbor_zones = intent.get("neighbor_zones", [])

        # 从候选人信息中获取分区
        target_zone = None
        if self._member_repo is not None:
            try:
                info = await self._member_repo.get_member_industry_info(target_id)
                target_zone = info.get("industry_zone")
            except Exception:
                pass

        if target_zone is None:
            return 0.3  # 无分区信息时返回默认值

        if target_zone == my_zone:
            return 0.85  # 同分区
        elif target_zone in neighbor_zones:
            return 0.55  # 近邻分区
        else:
            return 0.15  # 无关联

    async def _compute_motivation_score(
        self, source_id: str, target_id: str
    ) -> float:
        """
        维度3: 动力同频度

        通过教练SKILL比较两人的六层次诊断结果，
        相同瓶颈层次和相近评分 = 高同频度。

        Args:
            source_id: 发起人ID
            target_id: 候选人ID

        Returns:
            动力同频度 [0, 1]
        """
        if self._skill_orchestrator is not None:
            try:
                result = await self._skill_orchestrator.invoke(
                    "COACH",
                    {
                        "mode": "motivation_similarity",
                        "member_a_id": source_id,
                        "member_b_id": target_id,
                    },
                )
                if result and result.success:
                    return result.data.get("motivation_similarity", 0.15)
            except Exception:
                pass

        # 降级：基于六层次诊断的简单比较
        if self._member_repo is not None:
            try:
                diag_a = await self._member_repo.get_member_coach_diagnosis(source_id)
                diag_b = await self._member_repo.get_member_coach_diagnosis(target_id)
                if diag_a and diag_b:
                    return self._compare_diagnoses(diag_a, diag_b)
            except Exception:
                pass

        return 0.15  # 默认低同频度

    def _compare_diagnoses(self, diag_a: dict, diag_b: dict) -> float:
        """
        比较两人的六层次诊断结果

        使用余弦相似度比较六层次评分向量。

        Args:
            diag_a: 会员A的诊断 {"layers": {"environment": 5, ...}, "bottleneck": "behavior"}
            diag_b: 会员B的诊断

        Returns:
            动力同频度 [0, 1]
        """
        layers_a = diag_a.get("layers", {})
        layers_b = diag_b.get("layers", {})

        # 构建评分向量
        layer_order = ["environment", "behavior", "capability", "belief", "identity", "spirit"]
        vec_a = [layers_a.get(l, 5) for l in layer_order]
        vec_b = [layers_b.get(l, 5) for l in layer_order]

        # 余弦相似度
        sim = cosine_similarity(vec_a, vec_b)

        # 额外加分：瓶颈层次相同
        if diag_a.get("bottleneck") == diag_b.get("bottleneck"):
            sim = min(sim + 0.1, 1.0)

        # 映射到 [0, 1]，余弦相似度可能为负
        return max(0.0, (sim + 1.0) / 2.0)

    async def _compute_activity_trust_score(self, member_id: str) -> float:
        """
        维度4: 活跃度信任分

        公式: activity_trust = 0.4 * (level / 6)
                              + 0.3 * min(interactions_30d / 20, 1)
                              + 0.3 * (checkin_streak / 30)

        Args:
            member_id: 候选人ID

        Returns:
            活跃度信任分 [0, 1]
        """
        # 默认值
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

        score = (
            0.4 * (level / 6)
            + 0.3 * min(interactions_30d / 20, 1)
            + 0.3 * (checkin_streak / 30)
        )

        return min(score, 1.0)  # 上限截断

    # ── 辅助方法 ──────────────────────────────────────

    async def _get_member_roles(self, member_id: str) -> dict:
        """
        获取会员的角色信息

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

        # 降级：返回空角色
        return {"provide": [], "seek": []}

    def _generate_match_reasons(
        self,
        provide_seek_score: dict,
        chain_score: float,
        motivation_score: float,
        activity_trust_score: float,
    ) -> list[str]:
        """
        根据评分生成可读的匹配原因

        Args:
            provide_seek_score: 基础匹配分
            chain_score: 产业链协作分
            motivation_score: 动力同频度
            activity_trust_score: 活跃度信任分

        Returns:
            匹配原因标签列表
        """
        reasons = []

        if provide_seek_score.get("provide_seek", 0) > 0.6:
            reasons.append("供需高度互补")
        elif provide_seek_score.get("provide_seek", 0) > 0.4:
            reasons.append("供需基本互补")

        if provide_seek_score.get("seek_provide", 0) > 0.6:
            reasons.append("需求-供给匹配")

        if chain_score > 0.7:
            reasons.append("产业链高度关联")
        elif chain_score > 0.4:
            reasons.append("产业链近邻")

        if motivation_score > 0.6:
            reasons.append("动力同频")
        elif motivation_score > 0.4:
            reasons.append("动力部分同频")

        if activity_trust_score > 0.7:
            reasons.append("高活跃度")
        elif activity_trust_score > 0.4:
            reasons.append("活跃会员")

        if not reasons:
            reasons.append("综合匹配")

        return reasons
