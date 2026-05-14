"""
商脉系统 — 二度推荐算法

实现技术规格 4.5 的二度推荐：
  - BFS两跳查找共同好友
  - 信任背书权重: path_trust = trust_ac * trust_cb + endorser_reputation * 0.1
  - 关系信任度: 0.4 * 关系类型权重 + 0.3 * 互动频率 + 0.3 * 合作历史

二度推荐的核心思想：通过共同好友的信任背书，发现一度关系无法覆盖的
高价值潜在伙伴。两人之间的信任路径越短、背书人声望越高，推荐越可信。

参考技术规格样板 Chapter 4.5
"""

from collections import deque
from typing import Optional

# ── 关系类型权重定义 ──────────────────────────────────
# 不同关系类型对信任度的贡献不同
RELATION_TYPE_WEIGHTS: dict[str, float] = {
    "COFOUNDER": 1.0,    # 联合创始人 — 最高信任
    "PARTNER": 0.9,      # 合伙人
    "INVESTOR": 0.85,    # 投资人
    "CUSTOMER": 0.7,     # 客户
    "SUPPLIER": 0.7,     # 供应商
    "MENTOR": 0.8,       # 导师
    "MENTEE": 0.75,      # 学员
    "TEAM": 0.85,        # 团队成员
    "FRIEND": 0.6,       # 好友
    "ACQUAINTANCE": 0.3, # 熟人
    "VERIFIED": 0.5,     # 已认证关系
    "POTENTIAL": 0.1,    # 潜在关系
}

# 默认关系类型权重（未在映射中的关系）
DEFAULT_RELATION_WEIGHT: float = 0.3


class SecondDegreeRecommender:
    """
    二度推荐器 — 通过信任路径发现高价值潜在伙伴

    核心算法：
      1. 从发起人出发，BFS两跳查找所有二度联系人
      2. 对每个二度联系人，计算信任背书权重
      3. 去重已有一度关系
      4. 按信任背书权重排序返回

    信任背书公式：
      path_trust = trust_ac * trust_cb + endorser_reputation * 0.1

    关系信任度公式：
      relation_trust = 0.4 * relation_type_weight
                     + 0.3 * interaction_frequency
                     + 0.3 * cooperation_history
    """

    def __init__(self, member_repo=None, relation_repo=None):
        """
        初始化二度推荐器

        Args:
            member_repo: 会员数据仓库接口，需实现：
                - get_member_endorser_reputation(member_id) -> float
            relation_repo: 关系数据仓库接口，需实现：
                - get_first_degree_relations(member_id) -> list[dict]
                - get_relation_detail(member_a, member_b) -> dict
                - get_interaction_frequency(member_a, member_b, days) -> float
                - get_cooperation_history(member_a, member_b) -> float
        """
        self._member_repo = member_repo
        self._relation_repo = relation_repo

    # ── 公开接口 ──────────────────────────────────────

    async def find_second_degree(
        self,
        member_id: str,
        top_k: int = 20,
        min_path_trust: float = 0.3,
    ) -> list[dict]:
        """
        二度推荐完整流程

        Args:
            member_id: 发起人ID
            top_k: 返回的最大推荐人数
            min_path_trust: 最低信任背书阈值，低于此值的路径不推荐

        Returns:
            按信任背书权重降序排列的二度推荐列表，每项:
            {
                "member_id": str,            # 推荐人ID
                "path_trust": float,         # 路径信任度
                "paths": [                   # 所有信任路径
                    {
                        "via_member_id": str,      # 中间人ID
                        "trust_ac": float,         # A到中间人的信任度
                        "trust_cb": float,         # 中间人到B的信任度
                        "endorser_reputation": float,  # 中间人声望
                        "relation_types": [str, str],  # 两段关系类型
                    }
                ],
                "best_path_via": str,         # 最佳路径的中间人ID
                "recommendation_reason": str, # 推荐原因
            }
        """
        # 获取一度关系集合（用于去重）
        first_degree_ids = await self._get_first_degree_ids(member_id)
        first_degree_ids.add(member_id)  # 排除自己

        # BFS两跳查找二度联系人
        second_degree_map = await self._bfs_two_hop(
            member_id, first_degree_ids
        )

        if not second_degree_map:
            return []

        # 对每个二度联系人计算信任背书
        recommendations = []
        for target_id, paths in second_degree_map.items():
            path_trust, best_path = self._compute_path_trust(paths)

            if path_trust < min_path_trust:
                continue

            # 生成推荐原因
            reason = self._generate_recommendation_reason(
                best_path, path_trust
            )

            recommendations.append({
                "member_id": target_id,
                "path_trust": round(path_trust, 4),
                "paths": [
                    {
                        "via_member_id": p["via_member_id"],
                        "trust_ac": round(p["trust_ac"], 4),
                        "trust_cb": round(p["trust_cb"], 4),
                        "endorser_reputation": round(p["endorser_reputation"], 4),
                        "relation_types": p["relation_types"],
                    }
                    for p in paths
                ],
                "best_path_via": best_path["via_member_id"],
                "recommendation_reason": reason,
            })

        # 按 path_trust 降序排序
        recommendations.sort(key=lambda x: x["path_trust"], reverse=True)

        return recommendations[:top_k]

    # ── BFS两跳查找 ──────────────────────────────────

    async def _bfs_two_hop(
        self,
        member_id: str,
        exclude_ids: set[str],
    ) -> dict[str, list[dict]]:
        """
        BFS两跳查找二度联系人

        算法：
          1. 获取 member_id 的所有一度关系（第一跳）
          2. 对每个一度联系人，获取其一度关系（第二跳）
          3. 过滤掉已有一度关系和自身
          4. 收集所有到同一目标的路径

        Args:
            member_id: 发起人ID
            exclude_ids: 需要排除的ID集合（一度关系 + 自身）

        Returns:
            {target_id: [path_info, ...]} 二度联系人及其所有路径
        """
        second_degree_map: dict[str, list[dict]] = {}

        # 第一跳：获取发起人的一度关系
        first_degree = await self._get_first_degree_relations(member_id)

        for relation_a in first_degree:
            via_id = relation_a["member_id"]
            if via_id in exclude_ids:
                continue

            # 计算 A → 中间人 的关系信任度
            trust_ac = self._compute_relation_trust(relation_a)

            # 第二跳：获取中间人的一度关系
            second_degree = await self._get_first_degree_relations(via_id)

            for relation_b in second_degree:
                target_id = relation_b["member_id"]
                if target_id in exclude_ids:
                    continue
                if target_id == via_id:
                    continue

                # 计算 中间人 → B 的关系信任度
                trust_cb = self._compute_relation_trust(relation_b)

                # 获取中间人的声望
                endorser_reputation = await self._get_endorser_reputation(via_id)

                # 构建路径信息
                path_info = {
                    "via_member_id": via_id,
                    "trust_ac": trust_ac,
                    "trust_cb": trust_cb,
                    "endorser_reputation": endorser_reputation,
                    "relation_types": [
                        relation_a.get("relation_type", "ACQUAINTANCE"),
                        relation_b.get("relation_type", "ACQUAINTANCE"),
                    ],
                }

                if target_id not in second_degree_map:
                    second_degree_map[target_id] = []
                second_degree_map[target_id].append(path_info)

        return second_degree_map

    # ── 信任计算 ──────────────────────────────────────

    def _compute_path_trust(self, paths: list[dict]) -> tuple[float, dict]:
        """
        计算到目标的所有路径的信任背书权重

        公式: path_trust = trust_ac * trust_cb + endorser_reputation * 0.1

        对于多条路径，取最高信任背书值。

        Args:
            paths: 到目标的所有路径信息

        Returns:
            (最高路径信任度, 最佳路径信息)
        """
        best_trust = 0.0
        best_path = paths[0] if paths else {}

        for path in paths:
            trust_ac = path.get("trust_ac", 0.0)
            trust_cb = path.get("trust_cb", 0.0)
            endorser_rep = path.get("endorser_reputation", 0.0)

            path_trust = trust_ac * trust_cb + endorser_rep * 0.1

            if path_trust > best_trust:
                best_trust = path_trust
                best_path = path

        return best_trust, best_path

    def _compute_relation_trust(self, relation: dict) -> float:
        """
        计算单条关系的信任度

        公式: relation_trust = 0.4 * relation_type_weight
                             + 0.3 * interaction_frequency
                             + 0.3 * cooperation_history

        Args:
            relation: 关系信息，含:
                - relation_type: str (关系类型)
                - interaction_frequency: float [0,1] (互动频率)
                - cooperation_history: float [0,1] (合作历史评分)

        Returns:
            关系信任度 [0, 1]
        """
        relation_type = relation.get("relation_type", "ACQUAINTANCE")
        interaction_freq = relation.get("interaction_frequency", 0.0)
        cooperation_hist = relation.get("cooperation_history", 0.0)

        type_weight = RELATION_TYPE_WEIGHTS.get(
            relation_type, DEFAULT_RELATION_WEIGHT
        )

        trust = (
            0.4 * type_weight
            + 0.3 * min(max(interaction_freq, 0.0), 1.0)
            + 0.3 * min(max(cooperation_hist, 0.0), 1.0)
        )

        return min(trust, 1.0)

    # ── 数据获取 ──────────────────────────────────────

    async def _get_first_degree_ids(self, member_id: str) -> set[str]:
        """
        获取会员的一度关系ID集合

        Args:
            member_id: 会员ID

        Returns:
            一度关系会员ID集合
        """
        relations = await self._get_first_degree_relations(member_id)
        return {r["member_id"] for r in relations}

    async def _get_first_degree_relations(
        self, member_id: str
    ) -> list[dict]:
        """
        获取会员的一度关系列表

        Args:
            member_id: 会员ID

        Returns:
            关系列表，每项:
            {
                "member_id": str,
                "relation_type": str,
                "interaction_frequency": float,
                "cooperation_history": float,
            }
        """
        if self._relation_repo is not None:
            try:
                return await self._relation_repo.get_first_degree_relations(member_id)
            except Exception:
                pass

        return []

    async def _get_endorser_reputation(self, member_id: str) -> float:
        """
        获取会员的声望值（用于信任背书）

        Args:
            member_id: 会员ID

        Returns:
            声望值 [0, 1]
        """
        if self._member_repo is not None:
            try:
                return await self._member_repo.get_member_endorser_reputation(member_id)
            except Exception:
                pass

        return 0.3  # 默认中等声望

    # ── 推荐原因生成 ──────────────────────────────────

    def _generate_recommendation_reason(
        self, best_path: dict, path_trust: float
    ) -> str:
        """
        生成二度推荐的中文原因

        Args:
            best_path: 最佳路径信息
            path_trust: 路径信任度

        Returns:
            推荐原因字符串
        """
        via_id = best_path.get("via_member_id", "未知")
        relation_types = best_path.get("relation_types", ["", ""])

        # 关系类型中文映射
        type_names = {
            "COFOUNDER": "联合创始人",
            "PARTNER": "合伙人",
            "INVESTOR": "投资人",
            "CUSTOMER": "客户",
            "SUPPLIER": "供应商",
            "MENTOR": "导师",
            "MENTEE": "学员",
            "TEAM": "团队成员",
            "FRIEND": "好友",
            "ACQUAINTANCE": "熟人",
            "VERIFIED": "已认证联系人",
            "POTENTIAL": "潜在联系人",
        }

        type_a = type_names.get(relation_types[0], relation_types[0])
        type_b = type_names.get(relation_types[1], relation_types[1])

        if path_trust > 0.7:
            strength = "强"
        elif path_trust > 0.4:
            strength = "中"
        else:
            strength = "弱"

        return f"通过您的{type_a}({via_id[:8]}...)的{type_b}连接，信任背书{strength}({path_trust:.2f})"
