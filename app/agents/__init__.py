"""
商脉系统 — 智能体模块

9大智能体:
  MASTER    总控智能体 — 解析意图、拆解子任务
  MATCH     匹配智能体 — 精准匹配Pipeline
  NAMECARD  名片智能体 — 动态名片生成
  ACTIVITY  活动智能体 — 智能组局
  SECRETARY 秘书智能体 — 破冰方案、会面安排
  COACH     教练智能体 — 诊断、对话、行动承诺
  INDUSTRY  产业链智能体 — 产业链分析
  FINANCE   财务智能体 — 行动力计费
  CUSTOM    自定义智能体 — 扩展用

架构:
  dag.py          — 任务DAG与拓扑排序
  executor.py     — 异步执行引擎(超时+重试)
  degradation.py  — 降级策略引擎(异常处理)
  agents_impl.py  — 9大智能体实现
  dispatcher.py   — 调度器(DAG+Executor+Degradation)

参考技术规格样板 Chapter 5
"""

from app.agents.dag import (
    AgentType,
    TaskDAG,
    TaskNode,
    TaskResult,
    TaskStatus,
)
from app.agents.executor import AgentExecutor
from app.agents.degradation import (
    DegradationHandler,
    DegradationType,
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
from app.agents.dispatcher import (
    AgentDispatcher,
    DispatchResult,
    BudgetConfirmRequest,
    dispatcher,
)

__all__ = [
    # DAG
    "AgentType",
    "TaskDAG",
    "TaskNode",
    "TaskResult",
    "TaskStatus",
    # Executor
    "AgentExecutor",
    # Degradation
    "DegradationHandler",
    "DegradationType",
    "ExceptionType",
    "HandlingStrategy",
    # Agents
    "BaseAgent",
    "MasterAgent",
    "MatchAgent",
    "NamecardAgent",
    "ActivityAgent",
    "SecretaryAgent",
    "CoachAgent",
    "IndustryAgent",
    "FinanceAgent",
    "CustomAgent",
    "create_all_agents",
    "AGENT_DEPENDENCY_MAP",
    "AGENT_COST_MAP",
    "AGENT_DURATION_MAP",
    # Dispatcher
    "AgentDispatcher",
    "DispatchResult",
    "BudgetConfirmRequest",
    "dispatcher",
]
