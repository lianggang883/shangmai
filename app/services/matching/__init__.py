"""
商脉系统 — 匹配Pipeline统一入口

整合三阶段初筛 → 精筛Top-K → 二度推荐的完整匹配流程：
  1. CoarseMatcher: 三阶段初筛，100万→8000
  2. FineMatcher: 四维评分精筛，8000→Top-K
  3. SecondDegreeRecommender: 二度推荐补充，信任背书加权

参考技术规格样板 Chapter 4
"""

from typing import Optional

from app.services.matching.coarse_matcher import CoarseMatcher
from app.services.matching.fine_matcher import FineMatcher
from app.services.matching.second_degree import SecondDegreeRecommender


class MatchingPipeline:
    """
    匹配Pipeline — 统一入口，编排三阶段匹配流程

    使用方式：
      pipeline = MatchingPipeline(member_repo=..., relation_repo=...)
      result = await pipeline.trigger_matching(member_id, intent, top_k=10)

    流程编排：
      Step 1: CoarseMatcher.coarse_filter()  → 初筛候选人
      Step 2: FineMatcher.fine_rank()         → 精筛Top-K
      Step 3: SecondDegreeRecommender.find_second_degree() → 二度推荐补充
      Step 4: 合并去重 + 最终排序
    """

    def __init__(
        self,
        member_repo=None,
        relation_repo=None,
        skill_orchestrator=None,
    ):
        """
        初始化匹配Pipeline

        Args:
            member_repo: 会员数据仓库接口
            relation_repo: 关系数据仓库接口
            skill_orchestrator: SKILL调度器（用于调用产业链和教练SKILL）
        """
        self._coarse_matcher = CoarseMatcher(
            member_repo=member_repo,
            relation_repo=relation_repo,
        )
        self._fine_matcher = FineMatcher(
            member_repo=member_repo,
            skill_orchestrator=skill_orchestrator,
        )
        self._second_degree = SecondDegreeRecommender(
            member_repo=member_repo,
            relation_repo=relation_repo,
        )
        self._member_repo = member_repo
        self._relation_repo = relation_repo

    async def trigger_matching(
        self,
        member_id: str,
        intent: dict,
        top_k: int = 10,
        include_second_degree: bool = True,
        second_degree_top_k: int = 5,
    ) -> dict:
        """
        触发完整匹配流程

        Args:
            member_id: 发起匹配的会员ID
            intent: 匹配意图，格式:
                {
                    "provide_roles": ["partner", "supplier"],
                    "seek_roles": ["customer", "investor"],
                    "industry_zone": "tech",
                    "neighbor_zones": ["finance", "retail"],
                }
            top_k: 精筛返回的最大候选人数
            include_second_degree: 是否包含二度推荐
            second_degree_top_k: 二度推荐返回的最大人数

        Returns:
            {
                "match_id": str,
                "member_id": str,
                "primary_results": [...],     # 精筛Top-K结果
                "second_degree_results": [...], # 二度推荐结果
                "total_candidates": int,      # 初筛通过总数
                "returned": int,              # 最终返回总数
            }
        """
        import uuid

        match_id = f"match-{uuid.uuid4().hex[:12]}"

        # Step 1: 三阶段初筛
        coarse_candidates = await self._coarse_matcher.coarse_filter(
            member_id=member_id,
            intent=intent,
        )
        total_candidates = len(coarse_candidates)

        # Step 2: 精筛Top-K
        primary_results = await self._fine_matcher.fine_rank(
            source_member_id=member_id,
            candidates=coarse_candidates,
            intent=intent,
            top_k=top_k,
        )

        # Step 3: 二度推荐
        second_degree_results = []
        if include_second_degree:
            second_degree_results = await self._second_degree.find_second_degree(
                member_id=member_id,
                top_k=second_degree_top_k,
            )

        # Step 4: 合并去重
        # 从二度推荐中排除已在精筛结果中的会员
        primary_ids = {r["member_id"] for r in primary_results}
        filtered_second_degree = [
            r for r in second_degree_results
            if r["member_id"] not in primary_ids
        ]

        returned = len(primary_results) + len(filtered_second_degree)

        return {
            "match_id": match_id,
            "member_id": member_id,
            "primary_results": primary_results,
            "second_degree_results": filtered_second_degree,
            "total_candidates": total_candidates,
            "returned": returned,
        }

    async def rebuild_index(self) -> None:
        """
        重建初筛器的倒排索引

        在会员角色或产业链分区发生批量变更时调用。
        正常运行时索引自动维护，无需手动重建。
        """
        await self._coarse_matcher.build_index()

    def invalidate_index(self) -> None:
        """
        使索引缓存失效

        在单条会员数据变更时调用，下次查询时自动重建。
        """
        self._coarse_matcher.invalidate_index()
