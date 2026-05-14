"""
商脉系统 — 任务DAG与拓扑排序

实现技术规格 Chapter 5.1 的任务依赖图：
  - TaskNode: 任务节点定义
  - TaskDAG: 有向无环图管理
  - topological_sort(): 按层拓扑排序，同层可并行
  - get_parallel_layers(): 返回分层执行计划

参考技术规格样板 Chapter 5
"""
import uuid
from collections import deque
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AgentType(str, Enum):
    """智能体类型枚举"""
    MASTER = "MASTER"
    MATCH = "MATCH"
    NAMECARD = "NAMECARD"
    ACTIVITY = "ACTIVITY"
    SECRETARY = "SECRETARY"
    COACH = "COACH"
    INDUSTRY = "INDUSTRY"
    FINANCE = "FINANCE"
    CUSTOM = "CUSTOM"


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    DEGRADED = "DEGRADED"
    SKIPPED = "SKIPPED"


class TaskNode(BaseModel):
    """任务节点 — DAG中的单个任务"""
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_type: AgentType
    task_type: str = ""
    dependencies: list[str] = Field(default_factory=list)
    input_params: dict = Field(default_factory=dict)
    output_result: dict = Field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    estimated_duration: float = 30.0  # 预估执行时间(秒)
    estimated_cost: int = 0  # 预估行动力消耗
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 2
    error_message: Optional[str] = None


class TaskResult(BaseModel):
    """任务执行结果"""
    task_id: str
    success: bool
    data: dict = Field(default_factory=dict)
    action_power_used: int = 0
    error_message: Optional[str] = None
    degraded: bool = False  # 是否经过降级处理
    execution_time: float = 0.0  # 实际执行耗时(秒)


class TaskDAG:
    """
    任务有向无环图 — 管理任务节点和依赖关系

    核心能力:
      1. 添加任务节点及依赖边
      2. 检测环路（防止死锁）
      3. 拓扑排序（按层输出，同层可并行）
      4. 查询前置/后继任务

    示例:
      dag = TaskDAG()
      dag.add_task("master", AgentType.MASTER, dependencies=[])
      dag.add_task("match", AgentType.MATCH, dependencies=["master"])
      dag.add_task("namecard", AgentType.NAMECARD, dependencies=["match"])
      dag.add_task("industry", AgentType.INDUSTRY, dependencies=["match"])
      layers = dag.get_parallel_layers()
      # → [["master"], ["match"], ["namecard", "industry"]]
    """

    def __init__(self) -> None:
        """初始化DAG"""
        self._nodes: dict[str, TaskNode] = {}
        self._edges: dict[str, set[str]] = {}  # task_id → 依赖的task_id集合

    def add_task(
        self,
        task_id: str,
        agent_type: AgentType,
        dependencies: Optional[list[str]] = None,
        task_type: str = "",
        input_params: Optional[dict] = None,
        estimated_duration: float = 30.0,
        estimated_cost: int = 0,
    ) -> TaskNode:
        """
        添加任务节点到DAG

        Args:
            task_id: 任务唯一标识
            agent_type: 智能体类型
            dependencies: 依赖的任务ID列表（必须在这些任务完成后才能执行）
            task_type: 任务类型描述
            input_params: 任务输入参数
            estimated_duration: 预估执行时间(秒)
            estimated_cost: 预估行动力消耗

        Returns:
            创建的TaskNode实例

        Raises:
            ValueError: 如果依赖的任务不存在或检测到环路
        """
        dependencies = dependencies or []
        input_params = input_params or {}

        # 校验依赖任务是否存在
        for dep_id in dependencies:
            if dep_id not in self._nodes:
                raise ValueError(f"依赖任务不存在: {dep_id}")

        # 创建任务节点
        node = TaskNode(
            task_id=task_id,
            agent_type=agent_type,
            dependencies=dependencies,
            task_type=task_type,
            input_params=input_params,
            estimated_duration=estimated_duration,
            estimated_cost=estimated_cost,
        )
        self._nodes[task_id] = node
        self._edges[task_id] = set(dependencies)

        # 环路检测
        if self._has_cycle():
            # 回滚：移除刚添加的节点
            del self._nodes[task_id]
            del self._edges[task_id]
            raise ValueError(f"添加任务 {task_id} 后检测到环路，已回滚")

        return node

    def get_node(self, task_id: str) -> Optional[TaskNode]:
        """
        获取任务节点

        Args:
            task_id: 任务ID

        Returns:
            TaskNode实例，不存在时返回None
        """
        return self._nodes.get(task_id)

    def get_all_nodes(self) -> dict[str, TaskNode]:
        """获取所有任务节点"""
        return dict(self._nodes)

    def get_dependencies(self, task_id: str) -> list[str]:
        """
        获取任务的前置依赖列表

        Args:
            task_id: 任务ID

        Returns:
            依赖的task_id列表
        """
        return list(self._edges.get(task_id, set()))

    def get_dependents(self, task_id: str) -> list[str]:
        """
        获取依赖此任务的后继任务列表

        Args:
            task_id: 任务ID

        Returns:
            依赖此任务的task_id列表
        """
        dependents = []
        for tid, deps in self._edges.items():
            if task_id in deps:
                dependents.append(tid)
        return dependents

    def topological_sort(self) -> list[str]:
        """
        拓扑排序 — 返回合法的执行顺序

        使用Kahn算法，按入度递减顺序输出。

        Returns:
            排序后的task_id列表（线性顺序）

        Raises:
            ValueError: 如果图中存在环路
        """
        if not self._nodes:
            return []

        # 计算入度
        in_degree: dict[str, int] = {tid: 0 for tid in self._nodes}
        for tid, deps in self._edges.items():
            in_degree[tid] = len(deps)

        # 初始化队列（入度为0的节点）
        queue: deque[str] = deque()
        for tid, degree in in_degree.items():
            if degree == 0:
                queue.append(tid)

        result: list[str] = []
        while queue:
            task_id = queue.popleft()
            result.append(task_id)

            # 减少后继节点的入度
            for dependent_id in self.get_dependents(task_id):
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    queue.append(dependent_id)

        if len(result) != len(self._nodes):
            raise ValueError("DAG中存在环路，无法进行拓扑排序")

        return result

    def get_parallel_layers(self) -> list[list[str]]:
        """
        获取分层并行执行计划

        同一层的任务之间没有依赖关系，可以并行执行。
        基于BFS按层展开，每层包含所有入度为0的节点。

        Returns:
            分层任务ID列表，外层按顺序执行，内层可并行

        示例:
          MASTER → MATCH → [NAMECARD, INDUSTRY] → SECRETARY → ...
          结果: [["master"], ["match"], ["namecard", "industry"], ["secretary"], ...]
        """
        if not self._nodes:
            return []

        # 计算入度
        in_degree: dict[str, int] = {tid: 0 for tid in self._nodes}
        for tid, deps in self._edges.items():
            in_degree[tid] = len(deps)

        # 复制入度表（用于逐层消耗）
        remaining_degree = dict(in_degree)
        layers: list[list[str]] = []

        while True:
            # 当前层：所有入度为0的节点
            current_layer = [
                tid for tid, deg in remaining_degree.items() if deg == 0
            ]
            if not current_layer:
                break

            layers.append(current_layer)

            # 移除当前层节点，更新后继入度
            for task_id in current_layer:
                del remaining_degree[task_id]
                for dependent_id in self.get_dependents(task_id):
                    if dependent_id in remaining_degree:
                        remaining_degree[dependent_id] -= 1

        # 检查是否所有节点都被处理
        total_processed = sum(len(layer) for layer in layers)
        if total_processed != len(self._nodes):
            raise ValueError("DAG中存在环路，无法生成分层执行计划")

        return layers

    def get_total_estimated_cost(self) -> int:
        """获取所有任务预估行动力总消耗"""
        return sum(node.estimated_cost for node in self._nodes.values())

    def get_total_estimated_duration(self) -> float:
        """
        获取预估总执行时间(秒)

        按关键路径计算：每层取最大耗时，层间求和。
        """
        total = 0.0
        for layer in self.get_parallel_layers():
            layer_max = max(
                (self._nodes[tid].estimated_duration for tid in layer),
                default=0.0,
            )
            total += layer_max
        return total

    def _has_cycle(self) -> bool:
        """
        环路检测 — 使用DFS三色标记法

        Returns:
            True表示存在环路
        """
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {tid: WHITE for tid in self._nodes}

        def dfs(task_id: str) -> bool:
            """深度优先搜索检测环路，返回True表示发现环路"""
            color[task_id] = GRAY
            for dep_id in self._edges.get(task_id, set()):
                if dep_id not in color:
                    continue
                if color[dep_id] == GRAY:
                    return True  # 发现后向边（环路）
                if color[dep_id] == WHITE and dfs(dep_id):
                    return True
            color[task_id] = BLACK
            return False

        for tid in self._nodes:
            if color[tid] == WHITE:
                if dfs(tid):
                    return True
        return False

    def __len__(self) -> int:
        """返回DAG中的任务数量"""
        return len(self._nodes)

    def __repr__(self) -> str:
        """DAG的字符串表示"""
        layers = self.get_parallel_layers()
        layer_desc = []
        for i, layer in enumerate(layers):
            types = [self._nodes[tid].agent_type.value for tid in layer]
            layer_desc.append(f"  Layer {i}: {types}")
        return f"TaskDAG(nodes={len(self._nodes)}, layers={len(layers)})\n" + "\n".join(layer_desc)
