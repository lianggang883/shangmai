"""
商脉系统 — 角色关联场权重矩阵

实现技术规格 4.1 的10×10角色关联场权重矩阵和向量化功能：
  - ROLE_AFFINITY_MATRIX: 10×10矩阵（行=PROVIDE, 列=SEEK）
  - vectorize_member_roles(): 角色映射到768维向量，关联场权重调制，L2归一化
  - cosine_similarity: 余弦相似度工具函数

角色代码: partner, customer, investor, supplier, mentor, expert,
          cross_industry, team, media, ai_advisor

参考技术规格样板 Chapter 4.1
"""

import math
from typing import Optional

# ── 十维角色代码定义 ──────────────────────────────────
ROLE_CODES: list[str] = [
    "partner",        # 合伙人
    "customer",       # 客户
    "investor",       # 投资人
    "supplier",       # 供应商
    "mentor",         # 导师
    "expert",         # 专家
    "cross_industry", # 跨界合作者
    "team",           # 团队成员
    "media",          # 媒体
    "ai_advisor",     # AI顾问
]

# 角色代码到索引的映射
ROLE_INDEX: dict[str, int] = {code: idx for idx, code in enumerate(ROLE_CODES)}

# ── 10×10 角色关联场权重矩阵 ──────────────────────────
# 行 = PROVIDE（提供方角色），列 = SEEK（需求方角色）
# 含义：PROVIDE角色_i 对 SEEK角色_j 的关联场权重
# 值域 [0, 1]，1.0 = 完美互补，0.0 = 无关联
ROLE_AFFINITY_MATRIX: list[list[float]] = [
    # partner → SEEK:
    [0.95, 0.70, 0.60, 0.80, 0.55, 0.50, 0.65, 0.75, 0.40, 0.45],
    # customer → SEEK:
    [0.70, 0.30, 0.45, 0.85, 0.40, 0.35, 0.50, 0.55, 0.60, 0.40],
    # investor → SEEK:
    [0.60, 0.45, 0.25, 0.50, 0.60, 0.55, 0.70, 0.65, 0.50, 0.55],
    # supplier → SEEK:
    [0.80, 0.85, 0.50, 0.35, 0.30, 0.40, 0.45, 0.60, 0.35, 0.30],
    # mentor → SEEK:
    [0.55, 0.40, 0.60, 0.30, 0.25, 0.80, 0.55, 0.70, 0.45, 0.60],
    # expert → SEEK:
    [0.50, 0.35, 0.55, 0.40, 0.80, 0.25, 0.60, 0.65, 0.50, 0.75],
    # cross_industry → SEEK:
    [0.65, 0.50, 0.70, 0.45, 0.55, 0.60, 0.25, 0.50, 0.55, 0.50],
    # team → SEEK:
    [0.75, 0.55, 0.65, 0.60, 0.70, 0.65, 0.50, 0.30, 0.40, 0.45],
    # media → SEEK:
    [0.40, 0.60, 0.50, 0.35, 0.45, 0.50, 0.55, 0.40, 0.25, 0.45],
    # ai_advisor → SEEK:
    [0.45, 0.40, 0.55, 0.30, 0.60, 0.75, 0.50, 0.45, 0.45, 0.25],
]


def get_affinity(provide_role: str, seek_role: str) -> float:
    """
    查询角色关联场权重

    Args:
        provide_role: 提供方角色代码
        seek_role: 需求方角色代码

    Returns:
        关联场权重值 [0, 1]

    Raises:
        ValueError: 角色代码无效时
    """
    if provide_role not in ROLE_INDEX:
        raise ValueError(f"无效的提供方角色代码: {provide_role}")
    if seek_role not in ROLE_INDEX:
        raise ValueError(f"无效的需求方角色代码: {seek_role}")
    return ROLE_AFFINITY_MATRIX[ROLE_INDEX[provide_role]][ROLE_INDEX[seek_role]]


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    计算两个向量的余弦相似度

    Args:
        vec_a: 向量A
        vec_b: 向量B

    Returns:
        余弦相似度 [-1, 1]，维度不匹配时返回 0.0
    """
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def vectorize_member_roles(
    provide_roles: list[str],
    seek_roles: list[str],
    embedding_dim: int = 768,
    base_embedding_fn: Optional[callable] = None,
) -> tuple[list[float], list[float]]:
    """
    角色映射到768维向量，关联场权重调制，L2归一化

    将会员的 PROVIDE/SEEK 角色标签映射为768维向量。
    使用角色关联场权重矩阵对基础嵌入进行调制，增强角色间互补性表达。

    算法流程：
      1. 对每个PROVIDE角色，计算其在该角色上的关联场权重向量（10维）
      2. 将10维权重视为该角色在嵌入空间中的"注意力权重"
      3. 调制基础嵌入：对每个角色维度，用对应权重缩放嵌入分量
      4. L2归一化输出

    Args:
        provide_roles: 会员的PROVIDE角色代码列表
        seek_roles: 会员的SEEK角色代码列表
        embedding_dim: 嵌入向量维度，默认768
        base_embedding_fn: 可选的基础嵌入生成函数，
            签名 (role_code: str) -> list[float]。
            未提供时使用确定性哈希伪随机生成。

    Returns:
        (provide_vector, seek_vector) 两个L2归一化的768维浮点向量
    """
    provide_vec = _build_role_vector(
        provide_roles, "provide", embedding_dim, base_embedding_fn
    )
    seek_vec = _build_role_vector(
        seek_roles, "seek", embedding_dim, base_embedding_fn
    )
    return provide_vec, seek_vec


def _build_role_vector(
    roles: list[str],
    direction: str,
    embedding_dim: int,
    base_embedding_fn: Optional[callable],
) -> list[float]:
    """
    构建单个方向（PROVIDE或SEEK）的角色向量

    算法：
      1. 初始化零向量 [0.0] * embedding_dim
      2. 对每个角色：
         a. 获取基础嵌入（768维）
         b. 计算该角色对其他9个角色的关联场权重作为调制因子
         c. 将关联场权重视为注意力，缩放基础嵌入的分区
         d. 累加到结果向量
      3. L2归一化

    Args:
        roles: 角色代码列表
        direction: "provide" 或 "seek"
        embedding_dim: 嵌入维度
        base_embedding_fn: 基础嵌入生成函数

    Returns:
        L2归一化的embedding_dim维向量
    """
    if not roles:
        # 无角色时返回均匀分布的归一化向量
        val = 1.0 / math.sqrt(embedding_dim)
        return [val] * embedding_dim

    result = [0.0] * embedding_dim

    # 每个角色分到 embedding_dim // len(ROLE_CODES) 个维度分区
    partition_size = embedding_dim // len(ROLE_CODES)

    for role in roles:
        if role not in ROLE_INDEX:
            continue
        role_idx = ROLE_INDEX[role]

        # 获取基础嵌入
        if base_embedding_fn is not None:
            base_embed = base_embedding_fn(role)
        else:
            base_embed = _pseudo_embedding(role, embedding_dim)

        # 获取关联场权重行（PROVIDE方向）或列（SEEK方向）
        if direction == "provide":
            # PROVIDE方向：取矩阵行，表示该角色提供时对各方需求的影响力
            affinity_weights = ROLE_AFFINITY_MATRIX[role_idx]
        else:
            # SEEK方向：取矩阵列，表示该角色寻求时各方供给的匹配度
            affinity_weights = [
                ROLE_AFFINITY_MATRIX[i][role_idx]
                for i in range(len(ROLE_CODES))
            ]

        # 用关联场权重调制基础嵌入
        # 每个分区对应一个目标角色，用该目标的关联场权重缩放
        for target_idx, weight in enumerate(affinity_weights):
            start = target_idx * partition_size
            end = start + partition_size
            if end > embedding_dim:
                end = embedding_dim
            for i in range(start, end):
                result[i] += base_embed[i] * weight

        # 处理剩余维度（如果 embedding_dim 不能被 10 整除）
        remaining_start = len(ROLE_CODES) * partition_size
        if remaining_start < embedding_dim:
            avg_weight = sum(affinity_weights) / len(affinity_weights)
            for i in range(remaining_start, embedding_dim):
                result[i] += base_embed[i] * avg_weight

    # L2归一化
    norm = math.sqrt(sum(x * x for x in result))
    if norm > 0:
        result = [x / norm for x in result]

    return result


def _pseudo_embedding(role_code: str, dim: int) -> list[float]:
    """
    基于角色代码的确定性伪随机嵌入生成

    在没有外部embedding模型时使用，保证相同角色总是产生相同向量。

    Args:
        role_code: 角色代码
        dim: 向量维度

    Returns:
        L2归一化的dim维伪随机向量
    """
    import hashlib

    seed = int(hashlib.sha256(role_code.encode("utf-8")).hexdigest()[:16], 16)
    # 线性同余生成器 (LCG) 参数
    a, c, m = 6364136223846793005, 1442695040888963407, 2**64
    state = seed

    vec = []
    for _ in range(dim):
        state = (a * state + c) % m
        # 映射到 [-1, 1] 的正态分布近似值（Box-Muller变体）
        val = ((state >> 33) / (2**31)) - 1.0
        vec.append(val * 0.1)  # 缩放防止溢出

    # L2归一化
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]

    return vec
