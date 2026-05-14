"""
商脉系统 — 降级策略引擎

实现技术规格 Chapter 5.4 的异常处理和降级：

异常分类:
  - TASK_TIMEOUT: 任务超时
  - SKILL_CALL_FAILED: SKILL调用失败
  - ACTION_POWER_INSUFFICIENT: 行动力不足
  - DOWNSTREAM_DEPENDENCY_FAILED: 下游依赖失败
  - FULL_PIPELINE_FAILED: 全链路失败
  - DATA_INCONSISTENCY: 数据不一致

处理策略:
  - RETRY_TWICE_DEGRADE: 重试2次后降级
  - RETRY_ONCE_SKIP: 重试1次后跳过
  - TERMINATE_REFUND: 终止并退款
  - DEGRADE_INPUT: 降级输入继续执行
  - TERMINATE_REFUND_NOTIFY: 终止退款并通知
  - RECONCILE_ALERT: 对账修复并告警

降级方案:
  - MATCH: 使用缓存匹配结果(TTL=24h)
  - COACH: 返回预设教练话术模板
  - INDUSTRY_CHAIN: 返回行业通用产业链数据
  - SECRETARY: 使用规则模板生成破冰方案

参考技术规格样板 Chapter 5
"""
import hashlib
import json
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.agents.dag import AgentType, TaskResult, TaskStatus


# ===== 异常分类 =====

class ExceptionType(str, Enum):
    """异常类型枚举"""
    TASK_TIMEOUT = "TASK_TIMEOUT"                              # 任务超时
    SKILL_CALL_FAILED = "SKILL_CALL_FAILED"                    # SKILL调用失败
    ACTION_POWER_INSUFFICIENT = "ACTION_POWER_INSUFFICIENT"    # 行动力不足
    DOWNSTREAM_DEPENDENCY_FAILED = "DOWNSTREAM_DEPENDENCY_FAILED"  # 下游依赖失败
    FULL_PIPELINE_FAILED = "FULL_PIPELINE_FAILED"              # 全链路失败
    DATA_INCONSISTENCY = "DATA_INCONSISTENCY"                  # 数据不一致


class HandlingStrategy(str, Enum):
    """处理策略枚举"""
    RETRY_TWICE_DEGRADE = "RETRY_TWICE_DEGRADE"    # 重试2次后降级
    RETRY_ONCE_SKIP = "RETRY_ONCE_SKIP"            # 重试1次后跳过
    TERMINATE_REFUND = "TERMINATE_REFUND"          # 终止并退款
    DEGRADE_INPUT = "DEGRADE_INPUT"                # 降级输入继续执行
    TERMINATE_REFUND_NOTIFY = "TERMINATE_REFUND_NOTIFY"  # 终止退款并通知
    RECONCILE_ALERT = "RECONCILE_ALERT"            # 对账修复并告警


# ===== 异常→策略映射 =====

EXCEPTION_STRATEGY_MAP: dict[ExceptionType, HandlingStrategy] = {
    ExceptionType.TASK_TIMEOUT: HandlingStrategy.RETRY_TWICE_DEGRADE,
    ExceptionType.SKILL_CALL_FAILED: HandlingStrategy.RETRY_ONCE_SKIP,
    ExceptionType.ACTION_POWER_INSUFFICIENT: HandlingStrategy.TERMINATE_REFUND,
    ExceptionType.DOWNSTREAM_DEPENDENCY_FAILED: HandlingStrategy.DEGRADE_INPUT,
    ExceptionType.FULL_PIPELINE_FAILED: HandlingStrategy.TERMINATE_REFUND_NOTIFY,
    ExceptionType.DATA_INCONSISTENCY: HandlingStrategy.RECONCILE_ALERT,
}


# ===== 降级方案 =====

class DegradationType(str, Enum):
    """降级类型枚举"""
    MATCH_CACHE = "MATCH_CACHE"                    # MATCH: 缓存匹配结果
    COACH_TEMPLATE = "COACH_TEMPLATE"              # COACH: 预设话术模板
    INDUSTRY_GENERIC = "INDUSTRY_GENERIC"          # INDUSTRY: 通用产业链数据
    SECRETARY_RULE_TEMPLATE = "SECRETARY_RULE_TEMPLATE"  # SECRETARY: 规则模板
    NONE = "NONE"                                  # 无降级方案(不可降级)


# 智能体→降级类型映射
AGENT_DEGRADATION_MAP: dict[AgentType, DegradationType] = {
    AgentType.MATCH: DegradationType.MATCH_CACHE,
    AgentType.COACH: DegradationType.COACH_TEMPLATE,
    AgentType.INDUSTRY: DegradationType.INDUSTRY_GENERIC,
    AgentType.SECRETARY: DegradationType.SECRETARY_RULE_TEMPLATE,
}


class DegradationResult(BaseModel):
    """降级处理结果"""
    task_id: str
    degraded: bool = False
    degradation_type: Optional[DegradationType] = None
    result: Optional[TaskResult] = None
    message: str = ""


class DegradationHandler:
    """
    降级策略处理器 — 异常发生时的降级执行

    核心能力:
      1. 根据异常类型选择处理策略
      2. 根据智能体类型选择降级方案
      3. 提供各智能体的降级数据
      4. 维护MATCH缓存(TTL=24h)

    使用示例:
      handler = DegradationHandler()
      result = handler.handle(task, exception_type, error_message)
    """

    # MATCH缓存TTL(秒)
    MATCH_CACHE_TTL: int = 86400  # 24小时

    def __init__(self) -> None:
        """初始化降级处理器"""
        # MATCH缓存: cache_key → {"data": dict, "cached_at": float}
        self._match_cache: dict[str, dict] = {}
        # 降级日志
        self._degradation_log: list[dict] = []

    def handle(
        self,
        task_id: str,
        agent_type: AgentType,
        exception_type: ExceptionType,
        error_message: str,
        context: Optional[dict] = None,
    ) -> DegradationResult:
        """
        处理任务异常，执行降级策略

        Args:
            task_id: 任务ID
            agent_type: 智能体类型
            exception_type: 异常类型
            error_message: 错误信息
            context: 任务上下文(用于生成降级数据)

        Returns:
            降级处理结果
        """
        context = context or {}

        # 获取处理策略
        strategy = EXCEPTION_STRATEGY_MAP.get(exception_type)
        if not strategy:
            return DegradationResult(
                task_id=task_id,
                degraded=False,
                message=f"未知异常类型: {exception_type}",
            )

        # 记录降级日志
        self._log_degradation(task_id, agent_type, exception_type, strategy, error_message)

        # 按策略处理
        if strategy == HandlingStrategy.RETRY_TWICE_DEGRADE:
            return self._handle_retry_degrade(task_id, agent_type, context)

        elif strategy == HandlingStrategy.RETRY_ONCE_SKIP:
            return self._handle_retry_skip(task_id, agent_type, context)

        elif strategy == HandlingStrategy.TERMINATE_REFUND:
            return DegradationResult(
                task_id=task_id,
                degraded=False,
                message=f"行动力不足，终止执行并退款: {error_message}",
            )

        elif strategy == HandlingStrategy.DEGRADE_INPUT:
            return self._handle_degrade_input(task_id, agent_type, context)

        elif strategy == HandlingStrategy.TERMINATE_REFUND_NOTIFY:
            return DegradationResult(
                task_id=task_id,
                degraded=False,
                message=f"全链路失败，终止执行、退款并通知: {error_message}",
            )

        elif strategy == HandlingStrategy.RECONCILE_ALERT:
            return DegradationResult(
                task_id=task_id,
                degraded=False,
                message=f"数据不一致，需对账修复并告警: {error_message}",
            )

        return DegradationResult(
            task_id=task_id,
            degraded=False,
            message=f"未处理的策略: {strategy}",
        )

    def can_degrade(self, agent_type: AgentType) -> bool:
        """
        检查智能体是否有降级方案

        Args:
            agent_type: 智能体类型

        Returns:
            是否可降级
        """
        return agent_type in AGENT_DEGRADATION_MAP

    def get_degradation_type(self, agent_type: AgentType) -> Optional[DegradationType]:
        """
        获取智能体的降级类型

        Args:
            agent_type: 智能体类型

        Returns:
            降级类型，不可降级返回None
        """
        return AGENT_DEGRADATION_MAP.get(agent_type)

    # ===== 各智能体降级方案实现 =====

    def get_match_degradation(self, member_id: str, context: dict) -> TaskResult:
        """
        MATCH降级: 使用缓存匹配结果(TTL=24h)

        优先从缓存中查找该会员的匹配结果。
        缓存未命中时返回空结果但标记为降级成功。

        Args:
            member_id: 会员ID
            context: 上下文数据

        Returns:
            降级后的匹配结果
        """
        cache_key = self._make_match_cache_key(member_id, context)
        cached = self._match_cache.get(cache_key)

        if cached:
            age = time.time() - cached["cached_at"]
            if age < self.MATCH_CACHE_TTL:
                # 缓存命中且未过期
                return TaskResult(
                    task_id="",
                    success=True,
                    data={
                        **cached["data"],
                        "degraded": True,
                        "degradation_source": "cache",
                        "cache_age_seconds": int(age),
                    },
                    degraded=True,
                )

        # 缓存未命中，返回空匹配结果
        return TaskResult(
            task_id="",
            success=True,
            data={
                "matches": [],
                "total_score": 0,
                "degraded": True,
                "degradation_source": "empty_fallback",
                "message": "匹配服务暂不可用，已为您展示缓存的推荐结果",
            },
            degraded=True,
            action_power_used=0,
        )

    def get_coach_degradation(self, context: dict) -> TaskResult:
        """
        COACH降级: 返回预设教练话术模板

        根据会员的行业和阶段选择预设话术。
        无匹配模板时返回通用模板。

        Args:
            context: 上下文数据

        Returns:
            降级后的教练指导结果
        """
        # 预设教练话术模板
        templates = self._get_coach_templates()
        industry = context.get("industry", "通用")

        # 尝试匹配行业模板
        matched_template = templates.get(industry, templates.get("通用", {}))

        return TaskResult(
            task_id="",
            success=True,
            data={
                "diagnosis": matched_template.get("diagnosis", {}),
                "questions": matched_template.get("questions", []),
                "commitment": matched_template.get("commitment", {}),
                "degraded": True,
                "degradation_source": "template",
                "template_industry": industry,
                "message": "教练服务暂不可用，已为您展示通用指导建议",
            },
            degraded=True,
            action_power_used=0,
        )

    def get_industry_degradation(self, context: dict) -> TaskResult:
        """
        INDUSTRY_CHAIN降级: 返回行业通用产业链数据

        提供该行业的标准上下游结构数据。
        无对应行业时返回通用产业链框架。

        Args:
            context: 上下文数据

        Returns:
            降级后的产业链分析结果
        """
        industry = context.get("industry", "通用")
        generic_data = self._get_generic_industry_data(industry)

        return TaskResult(
            task_id="",
            success=True,
            data={
                **generic_data,
                "degraded": True,
                "degradation_source": "generic_data",
                "message": "产业链分析服务暂不可用，已为您展示行业通用数据",
            },
            degraded=True,
            action_power_used=0,
        )

    def get_secretary_degradation(self, context: dict) -> TaskResult:
        """
        SECRETARY降级: 使用规则模板生成破冰方案

        基于简单的规则引擎，根据对方的角色标签生成
        对应的破冰话术和方案。无需LLM调用。

        Args:
            context: 上下文数据

        Returns:
            降级后的秘书服务结果
        """
        target_role = context.get("target_role", "")
        target_industry = context.get("target_industry", "通用")
        icebreak_plans = self._generate_rule_based_icebreak(target_role, target_industry)

        return TaskResult(
            task_id="",
            success=True,
            data={
                "icebreak_plans": icebreak_plans,
                "degraded": True,
                "degradation_source": "rule_template",
                "message": "秘书服务暂不可用，已为您生成基础破冰方案",
            },
            degraded=True,
            action_power_used=0,
        )

    # ===== MATCH缓存管理 =====

    def cache_match_result(self, member_id: str, data: dict, context: dict = None) -> None:
        """
        缓存MATCH结果供降级使用

        Args:
            member_id: 会员ID
            data: 匹配结果数据
            context: 上下文(用于生成缓存键)
        """
        context = context or {}
        cache_key = self._make_match_cache_key(member_id, context)
        self._match_cache[cache_key] = {
            "data": data,
            "cached_at": time.time(),
        }

    def _make_match_cache_key(self, member_id: str, context: dict) -> str:
        """
        生成MATCH缓存键

        Args:
            member_id: 会员ID
            context: 上下文数据

        Returns:
            缓存键字符串
        """
        # 基于member_id + 关键上下文参数生成唯一键
        key_parts = [member_id]
        for k in sorted(context.keys()):
            if k in ("intent", "industry", "target_role"):
                key_parts.append(f"{k}={context[k]}")
        raw_key = "|".join(key_parts)
        return hashlib.md5(raw_key.encode()).hexdigest()

    # ===== 内部降级方案 =====

    def _handle_retry_degrade(
        self, task_id: str, agent_type: AgentType, context: dict
    ) -> DegradationResult:
        """
        处理「重试2次后降级」策略

        重试已由Executor完成，此处直接执行降级。

        Args:
            task_id: 任务ID
            agent_type: 智能体类型
            context: 上下文

        Returns:
            降级结果
        """
        degraded_result = self._apply_degradation(agent_type, context)

        if degraded_result:
            degraded_result.task_id = task_id
            return DegradationResult(
                task_id=task_id,
                degraded=True,
                degradation_type=AGENT_DEGRADATION_MAP.get(agent_type),
                result=degraded_result,
                message=f"任务重试耗尽，已降级处理({agent_type.value})",
            )

        return DegradationResult(
            task_id=task_id,
            degraded=False,
            message=f"任务重试耗尽且无降级方案({agent_type.value})",
        )

    def _handle_retry_skip(
        self, task_id: str, agent_type: AgentType, context: dict
    ) -> DegradationResult:
        """
        处理「重试1次后跳过」策略

        尝试降级，不可降级则跳过。

        Args:
            task_id: 任务ID
            agent_type: 智能体类型
            context: 上下文

        Returns:
            降级结果
        """
        degraded_result = self._apply_degradation(agent_type, context)

        if degraded_result:
            degraded_result.task_id = task_id
            return DegradationResult(
                task_id=task_id,
                degraded=True,
                degradation_type=AGENT_DEGRADATION_MAP.get(agent_type),
                result=degraded_result,
                message=f"SKILL调用失败，已降级跳过({agent_type.value})",
            )

        return DegradationResult(
            task_id=task_id,
            degraded=False,
            message=f"SKILL调用失败，已跳过({agent_type.value})",
        )

    def _handle_degrade_input(
        self, task_id: str, agent_type: AgentType, context: dict
    ) -> DegradationResult:
        """
        处理「降级输入继续执行」策略

        下游依赖失败时，用降级数据替代原始输入，
        让当前任务仍可执行。

        Args:
            task_id: 任务ID
            agent_type: 智能体类型
            context: 上下文

        Returns:
            降级结果(含降级后的输入数据)
        """
        degraded_result = self._apply_degradation(agent_type, context)

        if degraded_result:
            degraded_result.task_id = task_id
            return DegradationResult(
                task_id=task_id,
                degraded=True,
                degradation_type=AGENT_DEGRADATION_MAP.get(agent_type),
                result=degraded_result,
                message=f"下游依赖失败，已降级输入继续执行({agent_type.value})",
            )

        return DegradationResult(
            task_id=task_id,
            degraded=False,
            message=f"下游依赖失败且无降级方案({agent_type.value})",
        )

    def _apply_degradation(self, agent_type: AgentType, context: dict) -> Optional[TaskResult]:
        """
        执行智能体降级方案

        Args:
            agent_type: 智能体类型
            context: 上下文

        Returns:
            降级后的TaskResult，不可降级返回None
        """
        member_id = context.get("member_id", "")

        if agent_type == AgentType.MATCH:
            return self.get_match_degradation(member_id, context)
        elif agent_type == AgentType.COACH:
            return self.get_coach_degradation(context)
        elif agent_type == AgentType.INDUSTRY:
            return self.get_industry_degradation(context)
        elif agent_type == AgentType.SECRETARY:
            return self.get_secretary_degradation(context)

        return None

    # ===== 预设数据 =====

    @staticmethod
    def _get_coach_templates() -> dict[str, dict]:
        """获取教练话术模板库"""
        return {
            "通用": {
                "diagnosis": {
                    "level": "待诊断",
                    "focus_areas": ["资源整合", "人脉拓展", "商业模式"],
                },
                "questions": [
                    "您目前最迫切需要解决的业务问题是什么？",
                    "在拓展人脉方面，您遇到最大的障碍是什么？",
                    "如果有一个关键资源能帮到您，您希望是什么？",
                ],
                "commitment": {
                    "suggestion": "建议本周完成至少一次深度行业交流",
                    "follow_up": "7天后回顾进展",
                },
            },
            "科技": {
                "diagnosis": {
                    "level": "待诊断",
                    "focus_areas": ["技术创新", "产品市场匹配", "融资渠道"],
                },
                "questions": [
                    "您的核心技术壁垒是什么？",
                    "当前产品的主要用户群体特征是什么？",
                    "在技术团队建设上遇到什么挑战？",
                ],
                "commitment": {
                    "suggestion": "建议参加本月的技术创业者沙龙",
                    "follow_up": "7天后回顾技术路线进展",
                },
            },
            "金融": {
                "diagnosis": {
                    "level": "待诊断",
                    "focus_areas": ["资金配置", "风险管控", "合规发展"],
                },
                "questions": [
                    "您的资金使用效率是否达到预期？",
                    "在风险管理方面最大的隐忧是什么？",
                    "如何平衡创新业务与合规要求？",
                ],
                "commitment": {
                    "suggestion": "建议梳理核心业务的风险敞口",
                    "follow_up": "7天后评估风控措施效果",
                },
            },
        }

    @staticmethod
    def _get_generic_industry_data(industry: str) -> dict:
        """获取行业通用产业链数据"""
        return {
            "industry": industry,
            "proximity_score": 0.3,
            "top_dimensions": ["supply_chain", "market"],
            "upstream": [
                {"segment": "原材料", "representative_companies": ["待补充"]},
                {"segment": "核心零部件", "representative_companies": ["待补充"]},
            ],
            "midstream": [
                {"segment": "制造加工", "representative_companies": ["待补充"]},
                {"segment": "组装集成", "representative_companies": ["待补充"]},
            ],
            "downstream": [
                {"segment": "分销渠道", "representative_companies": ["待补充"]},
                {"segment": "终端客户", "representative_companies": ["待补充"]},
            ],
            "opportunity_areas": [
                "上游供应稳定性",
                "中游技术创新",
                "下游渠道拓展",
            ],
        }

    @staticmethod
    def _generate_rule_based_icebreak(target_role: str, target_industry: str) -> list[dict]:
        """
        基于规则生成破冰方案

        Args:
            target_role: 对方角色
            target_industry: 对方行业

        Returns:
            破冰方案列表
        """
        plans = [
            {
                "style": "务实型",
                "content": f"从{target_industry}行业数据和趋势切入，展示专业见解",
                "opening": f"您好，最近关注到{target_industry}行业有几个有趣的变化……",
            },
            {
                "style": "资源型",
                "content": "从资源互补角度切入，提出合作可能性",
                "opening": "了解到您在{target_industry}领域有深厚积累，我们在相关领域有些资源可以互补……",
            },
            {
                "style": "轻松型",
                "content": "从共同兴趣或行业活动切入，建立轻松氛围",
                "opening": f"最近有场{target_industry}领域的交流活动，不知道您是否关注到？",
            },
        ]

        # 根据角色微调
        if target_role in ("investor", "投资人"):
            plans.append({
                "style": "价值型",
                "content": "从投资回报和市场机会角度切入",
                "opening": "我们正在寻找在{target_industry}赛道的投资机会，想听听您的看法……",
            })
        elif target_role in ("supplier", "供应商"):
            plans.append({
                "style": "需求型",
                "content": "从采购需求和供应链优化角度切入",
                "opening": "我们在供应链方面有一些需求，正好和您的业务方向契合……",
            })

        return plans

    def _log_degradation(
        self,
        task_id: str,
        agent_type: AgentType,
        exception_type: ExceptionType,
        strategy: HandlingStrategy,
        error_message: str,
    ) -> None:
        """
        记录降级日志

        Args:
            task_id: 任务ID
            agent_type: 智能体类型
            exception_type: 异常类型
            strategy: 处理策略
            error_message: 错误信息
        """
        self._degradation_log.append({
            "task_id": task_id,
            "agent_type": agent_type.value,
            "exception_type": exception_type.value,
            "strategy": strategy.value,
            "error_message": error_message,
            "timestamp": datetime.now().isoformat(),
        })

    def get_degradation_log(self, task_id: Optional[str] = None) -> list[dict]:
        """
        获取降级日志

        Args:
            task_id: 可选，指定任务ID过滤

        Returns:
            降级日志列表
        """
        if task_id:
            return [
                log for log in self._degradation_log
                if log.get("task_id") == task_id
            ]
        return list(self._degradation_log)
