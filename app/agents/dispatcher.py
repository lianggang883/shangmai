"""
商脉系统 — 智能体调度引擎 (DAG+Executor+Degradation架构)

重写调度器，基于新的三层架构：
  1. TaskDAG: 构建任务依赖图，拓扑排序
  2. AgentExecutor: 异步并行执行，超时重试
  3. DegradationHandler: 异常降级，容错处理

调度完整流程:
  1. 意图解析 (MASTER智能体)
  2. 预算评估 (行动力预估)
  3. 构建DAG (根据智能体依赖关系)
  4. 大额确认 (>500行动力需用户确认)
  5. 拓扑排序执行 (按层并行)
  6. 降级处理 (失败任务自动降级)
  7. 结果汇总 (聚合所有子任务结果)
  8. 结算行动力 (按实际消耗结算)
  9. 触发游戏化 (记录事件+积分)

参考技术规格样板 Chapter 5
"""
import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.agents.dag import AgentType, TaskDAG, TaskNode, TaskResult, TaskStatus
from app.agents.executor import AgentExecutor
from app.agents.degradation import (
    DegradationHandler,
    ExceptionType,
    HandlingStrategy,
)
from app.agents.agents_impl import (
    BaseAgent,
    MasterAgent,
    MatchAgent,
    NamecardAgent,
    ActivityAgent,
    SecretaryAgent,
    CoachAgent,
    IndustryAgent,
    FinanceAgent,
    CustomAgent,
    create_all_agents,
    AGENT_DEPENDENCY_MAP,
    AGENT_COST_MAP,
    AGENT_DURATION_MAP,
)


# ===== 调度结果模型 =====

class DispatchResult(BaseModel):
    """调度执行结果"""
    dispatch_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    success: bool = True
    intent: str = ""
    member_id: str = ""
    agent_plan: list[dict] = Field(default_factory=list)
    task_results: dict[str, dict] = Field(default_factory=dict)
    total_action_power_used: int = 0
    total_estimated_cost: int = 0
    degraded_tasks: list[str] = Field(default_factory=list)
    failed_tasks: list[str] = Field(default_factory=list)
    execution_time: float = 0.0
    requires_budget_confirm: bool = False
    budget_confirmed: bool = False
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


class BudgetConfirmRequest(BaseModel):
    """大额行动力确认请求"""
    dispatch_id: str
    total_estimated_cost: int
    breakdown: list[dict] = Field(default_factory=list)
    message: str = ""


class AgentDispatcher:
    """
    智能体调度器 — 总控中心

    基于DAG+Executor+Degradation三层架构：
      - DAG层: 构建任务依赖图，确保执行顺序正确
      - Executor层: 异步并行执行，超时和重试机制
      - Degradation层: 异常降级，保证系统可用性

    调度流程:
      dispatch() → 意图解析 → 预算评估 → 构建DAG → 大额确认
                → 拓扑排序执行 → 降级处理 → 结果汇总 → 结算 → 游戏化

    使用示例:
      dispatcher = AgentDispatcher()
      result = await dispatcher.dispatch("我想找到供应链合作伙伴", "member_123")
    """

    # 大额确认阈值
    BIG_BUDGET_THRESHOLD: int = 500

    def __init__(self) -> None:
        """初始化调度器，注册所有智能体"""
        # 三大核心组件
        self._dag_builder = TaskDAG
        self._executor = AgentExecutor()
        self._degradation = DegradationHandler()

        # 智能体注册表
        self._agents: dict[AgentType, BaseAgent] = create_all_agents()

        # 为Executor注册处理器（适配签名：executor调用handler(task)，agent需要(task, context)）
        for agent_type, agent in self._agents.items():
            self._executor.register_handler(
                agent_type,
                self._make_handler(agent),
            )

        # 调度历史
        self._dispatch_history: list[DispatchResult] = []

        # 待确认的大额请求
        self._pending_confirmations: dict[str, BudgetConfirmRequest] = {}

    # ===== 核心调度入口 =====

    async def dispatch(
        self,
        intent: str,
        member_id: str,
        context: Optional[dict] = None,
        budget_confirmed: bool = False,
    ) -> DispatchResult:
        """
        调度入口 — 完整的意图处理流程

        流程:
          1. 意图解析 → MASTER生成子任务计划
          2. 预算评估 → 计算总行动力消耗
          3. 构建DAG → 根据智能体依赖关系构建任务图
          4. 大额确认 → >500行动力需用户确认
          5. 拓扑排序执行 → 按层并行执行
          6. 降级处理 → 失败任务自动降级
          7. 结果汇总 → 聚合所有子任务结果
          8. 结算行动力 → 按实际消耗结算
          9. 触发游戏化 → 记录事件和积分

        Args:
            intent: 用户意图描述(自然语言)
            member_id: 会员ID
            context: 附加上下文
            budget_confirmed: 用户是否已确认大额消耗

        Returns:
            DispatchResult 调度执行结果
        """
        import time as _time
        start_time = _time.monotonic()
        context = context or {}

        result = DispatchResult(
            intent=intent,
            member_id=member_id,
        )

        try:
            # ── Step 1: 意图解析 ──
            master_result = await self._parse_intent(intent, member_id, context)
            if not master_result.success:
                result.success = False
                result.error_message = f"意图解析失败: {master_result.error_message}"
                return result

            agent_plan = master_result.data.get("agent_plan", [])
            result.agent_plan = agent_plan

            # ── Step 2: 预算评估 ──
            total_cost = self._estimate_total_cost(agent_plan)
            result.total_estimated_cost = total_cost

            # ── Step 3: 大额确认 ──
            if total_cost >= self.BIG_BUDGET_THRESHOLD and not budget_confirmed:
                result.requires_budget_confirm = True
                result.budget_confirmed = False
                confirm_req = BudgetConfirmRequest(
                    dispatch_id=result.dispatch_id,
                    total_estimated_cost=total_cost,
                    breakdown=agent_plan,
                    message=f"本次操作预计消耗{total_cost}行动力，请确认",
                )
                self._pending_confirmations[result.dispatch_id] = confirm_req
                return result

            result.budget_confirmed = True

            # ── Step 4: 构建DAG ──
            dag = self._build_dag(agent_plan, member_id, context)

            # ── Step 5: 拓扑排序执行 ──
            layers = dag.get_parallel_layers()
            execution_context = {"MASTER": master_result}

            for layer_idx, layer_task_ids in enumerate(layers):
                # 构建当前层的任务节点列表
                layer_tasks = []
                for task_id in layer_task_ids:
                    node = dag.get_node(task_id)
                    if node:
                        # 将上游结果注入任务输入参数
                        node.input_params["_context"] = execution_context
                        layer_tasks.append(node)

                # 并行执行当前层
                layer_results = await self._executor.execute_layer(layer_tasks)

                # ── Step 6: 降级处理 ──
                for task_result in layer_results:
                    if not task_result.success:
                        # 判断异常类型
                        exception_type = self._classify_exception(task_result)
                        node = dag.get_node(task_result.task_id)

                        if node:
                            # 执行降级
                            degraded = self._degradation.handle(
                                task_id=task_result.task_id,
                                agent_type=node.agent_type,
                                exception_type=exception_type,
                                error_message=task_result.error_message or "",
                                context={
                                    **context,
                                    "member_id": member_id,
                                    **execution_context,
                                },
                            )

                            if degraded.degraded and degraded.result:
                                # 降级成功，用降级结果替代
                                task_result = degraded.result
                                result.degraded_tasks.append(task_result.task_id)
                            else:
                                # 降级失败，标记为失败任务
                                result.failed_tasks.append(task_result.task_id)

                    # 存入执行上下文供下游使用
                    node = dag.get_node(task_result.task_id)
                    if node:
                        execution_context[node.agent_type.value] = {
                            "data": task_result.data,
                            "success": task_result.success,
                            "action_power_used": task_result.action_power_used,
                        }

            # ── Step 7: 结果汇总 ──
            all_results = dict(self._executor.result_store)
            result.task_results = {
                tid: {
                    "success": tr.success,
                    "data": tr.data,
                    "action_power_used": tr.action_power_used,
                    "degraded": tr.degraded,
                    "execution_time": tr.execution_time,
                    "error_message": tr.error_message,
                }
                for tid, tr in all_results.items()
            }

            # ── Step 8: 结算行动力 ──
            total_used = sum(
                tr.action_power_used
                for tr in all_results.values()
            )
            result.total_action_power_used = total_used

            # TODO: 调用billing_service.settle(member_id, total_used)

            # ── Step 9: 触发游戏化 ──
            # TODO: 调用game_service.record_event(member_id, "INTERACTION")

        except Exception as e:
            result.success = False
            result.error_message = f"调度执行异常: {str(e)}"

        finally:
            result.execution_time = _time.monotonic() - start_time
            self._dispatch_history.append(result)
            # 清理Executor结果存储(为下次调度准备)
            self._executor.clear_results()

        return result

    # ===== Handler适配 =====

    @staticmethod
    def _make_handler(agent: BaseAgent) -> callable:
        """
        创建Executor处理器适配器

        Executor调用handler(task)，但Agent.execute需要(task, context)。
        此方法将agent.execute包装为executor期望的签名，
        从task.input_params["_context"]中提取执行上下文。

        Args:
            agent: 智能体实例

        Returns:
            异步处理函数 async (task: TaskNode) -> TaskResult
        """
        async def handler(task: TaskNode) -> TaskResult:
            context = task.input_params.get("_context", {})
            return await agent.execute(task, context)
        return handler

    # ===== 意图解析 =====

    async def _parse_intent(
        self, intent: str, member_id: str, context: dict
    ) -> TaskResult:
        """
        意图解析 — 调用MASTER智能体解析意图

        Args:
            intent: 用户意图
            member_id: 会员ID
            context: 上下文

        Returns:
            MASTER的解析结果
        """
        master_task = TaskNode(
            task_id="master_intent",
            agent_type=AgentType.MASTER,
            task_type="intent_parse",
            input_params={
                "intent": intent,
                "member_id": member_id,
                "context": context,
            },
            estimated_duration=5.0,
            estimated_cost=0,
        )

        master_agent = self._agents[AgentType.MASTER]
        return await master_agent.execute(master_task, context)

    # ===== 预算评估 =====

    def _estimate_total_cost(self, agent_plan: list[dict]) -> int:
        """
        预算评估 — 计算子任务计划的总行动力消耗

        Args:
            agent_plan: 子任务计划列表

        Returns:
            总预估行动力消耗
        """
        total = 0
        for step in agent_plan:
            agent_str = step.get("agent", "")
            try:
                agent_type = AgentType(agent_str)
                total += AGENT_COST_MAP.get(agent_type, step.get("estimated_cost", 0))
            except ValueError:
                total += step.get("estimated_cost", 0)
        return total

    # ===== DAG构建 =====

    def _build_dag(
        self,
        agent_plan: list[dict],
        member_id: str,
        context: dict,
    ) -> TaskDAG:
        """
        构建任务DAG — 根据子任务计划和智能体依赖关系

        依赖关系来源:
          1. 全局AGENT_DEPENDENCY_MAP: 智能体间的固有依赖
          2. agent_plan中的执行顺序: 计划中的顺序关系

        Args:
            agent_plan: 子任务计划列表
            member_id: 会员ID
            context: 上下文

        Returns:
            构建好的TaskDAG实例
        """
        dag = TaskDAG()

        # Step 1: 添加MASTER任务(始终存在)
        dag.add_task(
            task_id="master",
            agent_type=AgentType.MASTER,
            dependencies=[],
            task_type="intent_parse",
            input_params={"member_id": member_id, "context": context},
            estimated_duration=AGENT_DURATION_MAP[AgentType.MASTER],
            estimated_cost=AGENT_COST_MAP[AgentType.MASTER],
        )

        # Step 2: 根据计划添加任务
        task_id_map: dict[str, str] = {"MASTER": "master"}
        for idx, step in enumerate(agent_plan):
            agent_str = step.get("agent", "")
            try:
                agent_type = AgentType(agent_str)
            except ValueError:
                continue

            task_id = f"{agent_str.lower()}_{idx}"
            task_id_map[agent_str] = task_id

            # 确定依赖关系
            dep_task_ids: list[str] = []
            agent_deps = AGENT_DEPENDENCY_MAP.get(agent_type, [])

            for dep_agent in agent_deps:
                if dep_agent.value in task_id_map:
                    dep_task_ids.append(task_id_map[dep_agent.value])

            # 添加任务到DAG
            dag.add_task(
                task_id=task_id,
                agent_type=agent_type,
                dependencies=dep_task_ids,
                task_type=step.get("task", ""),
                input_params={
                    "member_id": member_id,
                    "step": step,
                },
                estimated_duration=AGENT_DURATION_MAP.get(
                    agent_type, step.get("estimated_duration", 20.0)
                ),
                estimated_cost=AGENT_COST_MAP.get(
                    agent_type, step.get("estimated_cost", 5)
                ),
            )

        return dag

    # ===== 异常分类 =====

    def _classify_exception(self, task_result: TaskResult) -> ExceptionType:
        """
        异常分类 — 根据任务结果判断异常类型

        Args:
            task_result: 失败的任务结果

        Returns:
            对应的异常类型
        """
        error_msg = task_result.error_message or ""

        if "超时" in error_msg or "timeout" in error_msg.lower():
            return ExceptionType.TASK_TIMEOUT

        if "行动力不足" in error_msg or "balance" in error_msg.lower():
            return ExceptionType.ACTION_POWER_INSUFFICIENT

        if "SKILL" in error_msg or "skill" in error_msg.lower():
            return ExceptionType.SKILL_CALL_FAILED

        if "下游" in error_msg or "dependency" in error_msg.lower():
            return ExceptionType.DOWNSTREAM_DEPENDENCY_FAILED

        if "数据不一致" in error_msg or "inconsist" in error_msg.lower():
            return ExceptionType.DATA_INCONSISTENCY

        # 默认按SKILL调用失败处理
        return ExceptionType.SKILL_CALL_FAILED

    # ===== 大额确认 =====

    def get_pending_confirmation(self, dispatch_id: str) -> Optional[BudgetConfirmRequest]:
        """
        获取待确认的大额请求

        Args:
            dispatch_id: 调度ID

        Returns:
            确认请求，不存在返回None
        """
        return self._pending_confirmations.get(dispatch_id)

    def confirm_budget(self, dispatch_id: str) -> bool:
        """
        确认大额消耗

        Args:
            dispatch_id: 调度ID

        Returns:
            是否确认成功
        """
        if dispatch_id in self._pending_confirmations:
            del self._pending_confirmations[dispatch_id]
            return True
        return False

    # ===== 查询接口 =====

    def get_dispatch_history(
        self, member_id: Optional[str] = None, limit: int = 20
    ) -> list[DispatchResult]:
        """
        获取调度历史

        Args:
            member_id: 可选，按会员ID过滤
            limit: 返回数量限制

        Returns:
            调度结果列表
        """
        history = self._dispatch_history
        if member_id:
            history = [r for r in history if r.member_id == member_id]
        return history[-limit:]

    def get_agent_info(self) -> list[dict]:
        """
        获取所有智能体信息

        Returns:
            智能体信息列表
        """
        return [
            {
                "agent_type": agent.agent_type.value,
                "description": agent.description,
                "dependencies": [d.value for d in agent.get_dependencies()],
                "required_skills": agent.get_required_skills(),
                "estimated_cost": AGENT_COST_MAP.get(agent.agent_type, 0),
                "estimated_duration": AGENT_DURATION_MAP.get(agent.agent_type, 0),
                "degradation_available": self._degradation.can_degrade(agent.agent_type),
            }
            for agent in self._agents.values()
        ]


# ===== 全局单例 =====

dispatcher = AgentDispatcher()
