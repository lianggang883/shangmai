"""
商脉系统 — 9大智能体完整实现

实现技术规格 Chapter 5.2 的9大智能体依赖关系：

  MASTER    总控调度 — 意图解析，子任务分发，结果汇总
  MATCH     精准匹配Pipeline — 依赖MASTER，下游触发NAMECARD+INDUSTRY
  NAMECARD  名片生成 — 依赖MATCH，与INDUSTRY并行
  ACTIVITY  活动推荐 — 依赖MATCH，与SECRETARY并行
  SECRETARY 秘书服务 — 依赖NAMECARD+INDUSTRY
  COACH     教练指导 — 依赖SECRETARY+MASTER
  INDUSTRY  产业链分析 — 依赖MATCH，与NAMECARD并行
  FINANCE   金融服务 — 依赖INDUSTRY+COACH
  CUSTOM    定制服务 — 依赖MASTER，与MATCH并行

参考技术规格样板 Chapter 5
"""
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.agents.dag import AgentType, TaskNode, TaskResult, TaskStatus


# ===== 智能体基类 =====

class BaseAgent(ABC):
    """
    智能体基类 — 所有智能体的抽象模板

    生命周期:
      validate() → execute() → 返回TaskResult

    关键设计:
      - get_dependencies(): 声明上游依赖(用于DAG构建)
      - get_required_skills(): 声明SKILL依赖(用于编排)
      - estimate_cost(): 预估行动力消耗
      - estimate_duration(): 预估执行时间
    """

    @property
    @abstractmethod
    def agent_type(self) -> AgentType:
        """智能体类型标识"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """智能体功能描述"""
        ...

    @abstractmethod
    async def execute(self, task: TaskNode, context: dict) -> TaskResult:
        """
        执行智能体任务

        Args:
            task: 任务节点
            context: 执行上下文(包含上游结果等)

        Returns:
            任务执行结果
        """
        ...

    @abstractmethod
    def get_dependencies(self) -> list[AgentType]:
        """声明上游依赖的智能体类型(用于DAG构建)"""
        ...

    @abstractmethod
    def get_required_skills(self) -> list[str]:
        """声明依赖的SKILL类型(用于编排)"""
        ...

    @abstractmethod
    def estimate_cost(self, task: TaskNode) -> int:
        """预估行动力消耗"""
        ...

    @abstractmethod
    def estimate_duration(self, task: TaskNode) -> float:
        """预估执行时间(秒)"""
        ...

    def validate(self, task: TaskNode, context: dict) -> tuple[bool, str]:
        """
        输入校验

        Args:
            task: 任务节点
            context: 执行上下文

        Returns:
            (是否合法, 错误信息)
        """
        return True, ""


# ===== MASTER — 总控智能体 =====

class MasterAgent(BaseAgent):
    """
    总控智能体 — 解析意图、生成子任务计划、汇总结果

    职责:
      1. 接收自然语言意图
      2. 解析为结构化任务计划
      3. 分发子任务到对应智能体
      4. 汇总所有子任务结果

    依赖: 无(入口智能体)
    下游: MATCH, CUSTOM
    """

    @property
    def agent_type(self) -> AgentType:
        return AgentType.MASTER

    @property
    def description(self) -> str:
        return "总控调度 — 意图解析，子任务分发，结果汇总"

    def get_dependencies(self) -> list[AgentType]:
        return []

    def get_required_skills(self) -> list[str]:
        return []

    def estimate_cost(self, task: TaskNode) -> int:
        return 0  # Master本身不消耗行动力

    def estimate_duration(self, task: TaskNode) -> float:
        return 5.0

    def validate(self, task: TaskNode, context: dict) -> tuple[bool, str]:
        intent = task.input_params.get("intent", "")
        if not intent:
            return False, "缺少意图描述"
        return True, ""

    async def execute(self, task: TaskNode, context: dict) -> TaskResult:
        """
        执行意图解析和子任务规划

        Args:
            task: 包含intent的输入参数
            context: 用户上下文

        Returns:
            解析后的子任务计划
        """
        intent = task.input_params.get("intent", "")
        member_id = task.input_params.get("member_id", "")

        # 意图解析 → 子任务计划
        plan = self._parse_intent(intent, context)

        return TaskResult(
            task_id=task.task_id,
            success=True,
            data={
                "intent": intent,
                "member_id": member_id,
                "agent_plan": plan,
                "total_estimated_cost": sum(step.get("estimated_cost", 0) for step in plan),
            },
            action_power_used=0,
        )

    def _parse_intent(self, intent: str, context: dict) -> list[dict]:
        """
        意图解析 → 子任务计划

        基于关键词匹配生成计划（后续可替换为LLM解析）

        Args:
            intent: 用户意图描述
            context: 上下文

        Returns:
            子任务计划列表
        """
        plan = []

        # 匹配相关意图
        if any(kw in intent for kw in ["找", "匹配", "发现", "推荐", "寻找", "对接"]):
            plan.append({
                "agent": "MATCH",
                "task": "精准匹配",
                "estimated_cost": 15,
                "estimated_duration": 30,
            })

        # 产业链相关意图
        if any(kw in intent for kw in ["产业链", "供应链", "上下游", "行业分析"]):
            plan.append({
                "agent": "INDUSTRY",
                "task": "产业链分析",
                "estimated_cost": 10,
                "estimated_duration": 25,
            })

        # 破冰/联系相关意图
        if any(kw in intent for kw in ["破冰", "认识", "联系", "交流", "认识一下", "搭话"]):
            plan.append({
                "agent": "SECRETARY",
                "task": "生成破冰方案",
                "estimated_cost": 8,
                "estimated_duration": 20,
            })

        # 教练/诊断相关意图
        if any(kw in intent for kw in ["教练", "诊断", "困惑", "瓶颈", "方向", "迷茫"]):
            plan.append({
                "agent": "COACH",
                "task": "教练诊断",
                "estimated_cost": 10,
                "estimated_duration": 25,
            })

        # 活动相关意图
        if any(kw in intent for kw in ["活动", "聚会", "见面", "组局", "线下"]):
            plan.append({
                "agent": "ACTIVITY",
                "task": "智能组局",
                "estimated_cost": 5,
                "estimated_duration": 15,
            })

        # 金融相关意图
        if any(kw in intent for kw in ["融资", "贷款", "投资", "资金", "财务"]):
            plan.append({
                "agent": "FINANCE",
                "task": "金融服务",
                "estimated_cost": 12,
                "estimated_duration": 20,
            })

        # 定制相关意图
        if any(kw in intent for kw in ["定制", "专属", "特殊", "自定义"]):
            plan.append({
                "agent": "CUSTOM",
                "task": "定制服务",
                "estimated_cost": 8,
                "estimated_duration": 20,
            })

        # 无匹配时默认方案
        if not plan:
            plan.append({
                "agent": "MATCH",
                "task": "通用推荐",
                "estimated_cost": 10,
                "estimated_duration": 25,
            })
            plan.append({
                "agent": "SECRETARY",
                "task": "通用破冰建议",
                "estimated_cost": 5,
                "estimated_duration": 15,
            })

        return plan


# ===== MATCH — 匹配智能体 =====

class MatchAgent(BaseAgent):
    """
    匹配智能体 — 精准匹配Pipeline

    职责:
      1. 调用SKILL匹配Pipeline(ROLE + INDUSTRY_CHAIN + COACH)
      2. 综合评分与排序
      3. 生成匹配日报

    依赖: MASTER
    下游: NAMECARD, INDUSTRY
    """

    @property
    def agent_type(self) -> AgentType:
        return AgentType.MATCH

    @property
    def description(self) -> str:
        return "精准匹配Pipeline — 角色供需+产业链+动力同频"

    def get_dependencies(self) -> list[AgentType]:
        return [AgentType.MASTER]

    def get_required_skills(self) -> list[str]:
        return ["ROLE", "INDUSTRY_CHAIN", "COACH"]

    def estimate_cost(self, task: TaskNode) -> int:
        return 15

    def estimate_duration(self, task: TaskNode) -> float:
        return 30.0

    async def execute(self, task: TaskNode, context: dict) -> TaskResult:
        """
        执行匹配Pipeline

        Args:
            task: 包含member_id的输入参数
            context: 上游MASTER的解析结果

        Returns:
            匹配结果(评分、推荐列表)
        """
        member_id = task.input_params.get("member_id", "")

        # TODO: 调用SkillOrchestrator.execute_matching_pipeline
        # 当前返回模拟匹配结果
        return TaskResult(
            task_id=task.task_id,
            success=True,
            data={
                "matches": [
                    {
                        "member_id": f"member_{i}",
                        "name": f"推荐用户{i}",
                        "total_score": round(0.85 - i * 0.05, 4),
                        "score_breakdown": {
                            "role_score": 0.4,
                            "chain_score": 0.3,
                            "motivation_score": 0.15,
                            "activity_score": 0.05,
                        },
                    }
                    for i in range(5)
                ],
                "total_score": 0.85,
                "score_breakdown": {
                    "role_score": 0.4,
                    "chain_score": 0.3,
                    "motivation_score": 0.15,
                    "activity_score": 0.05,
                },
            },
            action_power_used=15,
        )


# ===== NAMECARD — 名片智能体 =====

class NamecardAgent(BaseAgent):
    """
    名片智能体 — 动态名片生成

    职责:
      1. 基于匹配结果生成动态名片
      2. 融合角色标签+产业链定位+互动数据
      3. 支持多维度名片展示

    依赖: MATCH
    并行: 与INDUSTRY并行
    """

    @property
    def agent_type(self) -> AgentType:
        return AgentType.NAMECARD

    @property
    def description(self) -> str:
        return "动态名片生成 — 角色+产业链+互动数据融合"

    def get_dependencies(self) -> list[AgentType]:
        return [AgentType.MATCH]

    def get_required_skills(self) -> list[str]:
        return ["ROLE"]

    def estimate_cost(self, task: TaskNode) -> int:
        return 5

    def estimate_duration(self, task: TaskNode) -> float:
        return 15.0

    async def execute(self, task: TaskNode, context: dict) -> TaskResult:
        """
        执行名片生成

        Args:
            task: 包含目标member_id
            context: 上游MATCH的匹配结果

        Returns:
            生成的名片数据
        """
        member_id = task.input_params.get("member_id", "")
        match_data = context.get("MATCH", {})

        # TODO: 调用角色SKILL生成名片
        matches = match_data.get("data", {}).get("matches", [])

        namecards = []
        for match in matches[:3]:
            namecards.append({
                "member_id": match.get("member_id", ""),
                "display_name": match.get("name", ""),
                "role_tags": ["资源方", "需求方"],
                "industry_position": "中游-制造加工",
                "strength_highlight": "供应链管理经验丰富",
                "icebreaker_hint": "从供应链优化话题切入",
            })

        return TaskResult(
            task_id=task.task_id,
            success=True,
            data={
                "namecards": namecards,
                "generated_count": len(namecards),
            },
            action_power_used=5,
        )


# ===== ACTIVITY — 活动智能体 =====

class ActivityAgent(BaseAgent):
    """
    活动智能体 — 智能组局

    职责:
      1. 推荐合适的活动类型
      2. 匹配活动参与者
      3. 生成活动方案

    依赖: MATCH
    并行: 与SECRETARY并行
    """

    @property
    def agent_type(self) -> AgentType:
        return AgentType.ACTIVITY

    @property
    def description(self) -> str:
        return "智能组局 — 活动推荐与参与者匹配"

    def get_dependencies(self) -> list[AgentType]:
        return [AgentType.MATCH]

    def get_required_skills(self) -> list[str]:
        return ["ROLE", "GAMIFICATION"]

    def estimate_cost(self, task: TaskNode) -> int:
        return 5

    def estimate_duration(self, task: TaskNode) -> float:
        return 15.0

    async def execute(self, task: TaskNode, context: dict) -> TaskResult:
        """
        执行活动推荐

        Args:
            task: 包含活动相关参数
            context: 上游MATCH的匹配结果

        Returns:
            推荐的活动列表
        """
        match_data = context.get("MATCH", {})
        matches = match_data.get("data", {}).get("matches", [])

        # 基于匹配结果推荐活动
        activities = [
            {
                "type": "行业沙龙",
                "title": "产业链协同创新沙龙",
                "suggested_participants": [m.get("member_id", "") for m in matches[:3]],
                "format": "线下圆桌",
                "estimated_attendees": 8,
                "topics": ["供应链协同", "技术创新", "市场拓展"],
            },
            {
                "type": "一对一交流",
                "title": "精准对接会",
                "suggested_participants": [matches[0].get("member_id", "")] if matches else [],
                "format": "线上/线下",
                "estimated_attendees": 2,
                "topics": ["资源互补", "合作探索"],
            },
        ]

        return TaskResult(
            task_id=task.task_id,
            success=True,
            data={
                "activities": activities,
                "recommended_count": len(activities),
            },
            action_power_used=5,
        )


# ===== SECRETARY — 秘书智能体 =====

class SecretaryAgent(BaseAgent):
    """
    秘书智能体 — 破冰方案、会面安排

    职责:
      1. 生成个性化破冰方案
      2. 调用MCKINSEY SKILL提供方法论支撑
      3. 安排会面计划

    依赖: NAMECARD + INDUSTRY
    """

    @property
    def agent_type(self) -> AgentType:
        return AgentType.SECRETARY

    @property
    def description(self) -> str:
        return "破冰方案与会面安排 — 个性化社交策略"

    def get_dependencies(self) -> list[AgentType]:
        return [AgentType.NAMECARD, AgentType.INDUSTRY]

    def get_required_skills(self) -> list[str]:
        return ["MCKINSEY", "ROLE"]

    def estimate_cost(self, task: TaskNode) -> int:
        return 8

    def estimate_duration(self, task: TaskNode) -> float:
        return 20.0

    async def execute(self, task: TaskNode, context: dict) -> TaskResult:
        """
        执行破冰方案生成

        Args:
            task: 包含目标信息
            context: 上游NAMECARD+INDUSTRY的结果

        Returns:
            破冰方案列表
        """
        namecard_data = context.get("NAMECARD", {})
        industry_data = context.get("INDUSTRY", {})

        namecards = namecard_data.get("data", {}).get("namecards", [])
        industry_info = industry_data.get("data", {}).get("opportunity_areas", [])

        # 基于名片和产业链信息生成破冰方案
        icebreak_plans = []
        for card in namecards[:3]:
            hint = card.get("icebreaker_hint", "从行业趋势话题切入")
            icebreak_plans.append({
                "target_member_id": card.get("member_id", ""),
                "target_name": card.get("display_name", ""),
                "style": "务实型",
                "content": hint,
                "opening": f"您好，了解到您在{card.get('industry_position', '该领域')}的深厚积累……",
                "opportunity_areas": industry_info[:2],
            })

        # 添加通用方案
        icebreak_plans.append({
            "target_member_id": "通用",
            "target_name": "通用破冰",
            "style": "轻松型",
            "content": "从共同兴趣和行业动态切入",
            "opening": "最近行业里有些新变化，想和您交流一下看法……",
            "opportunity_areas": industry_info,
        })

        return TaskResult(
            task_id=task.task_id,
            success=True,
            data={
                "icebreak_plans": icebreak_plans,
                "generated_count": len(icebreak_plans),
            },
            action_power_used=8,
        )


# ===== COACH — 教练智能体 =====

class CoachAgent(BaseAgent):
    """
    教练智能体 — 诊断、对话、行动承诺

    职责:
      1. 六层次需求诊断
      2. 苏格拉底式引导对话
      3. 行动承诺与跟踪

    依赖: SECRETARY + MASTER
    """

    @property
    def agent_type(self) -> AgentType:
        return AgentType.COACH

    @property
    def description(self) -> str:
        return "教练指导 — 需求诊断+引导对话+行动承诺"

    def get_dependencies(self) -> list[AgentType]:
        return [AgentType.SECRETARY, AgentType.MASTER]

    def get_required_skills(self) -> list[str]:
        return ["COACH"]

    def estimate_cost(self, task: TaskNode) -> int:
        return 10

    def estimate_duration(self, task: TaskNode) -> float:
        return 25.0

    async def execute(self, task: TaskNode, context: dict) -> TaskResult:
        """
        执行教练诊断和指导

        Args:
            task: 包含诊断需求
            context: 上游SECRETARY+MASTER的结果

        Returns:
            诊断结果和行动建议
        """
        secretary_data = context.get("SECRETARY", {})
        master_data = context.get("MASTER", {})

        intent = master_data.get("data", {}).get("intent", "")

        # TODO: 调用CoachSkill进行深度诊断
        # 当前返回模拟诊断结果
        return TaskResult(
            task_id=task.task_id,
            success=True,
            data={
                "diagnosis": {
                    "level": "战略层",
                    "focus_areas": ["资源整合", "人脉拓展", "商业模式"],
                    "current_stage": "成长期",
                    "pain_points": ["核心伙伴不足", "行业资源分散"],
                },
                "questions": [
                    "您目前最迫切需要解决的业务问题是什么？",
                    "在拓展人脉方面，最大的障碍是什么？",
                    "如果有一个关键资源能帮到您，您希望是什么？",
                ],
                "commitment": {
                    "action": "本周完成至少一次深度行业交流",
                    "follow_up_date": "7天后",
                    "milestone": "建立2个高价值人脉连接",
                },
                "motivation_similarity": 0.72,
            },
            action_power_used=10,
        )


# ===== INDUSTRY — 产业链智能体 =====

class IndustryAgent(BaseAgent):
    """
    产业链智能体 — 产业链分析

    职责:
      1. 十维产业链近邻度分析
      2. 上下游定位
      3. 合作机会发现

    依赖: MATCH
    并行: 与NAMECARD并行
    """

    @property
    def agent_type(self) -> AgentType:
        return AgentType.INDUSTRY

    @property
    def description(self) -> str:
        return "产业链分析 — 十维近邻度+上下游定位"

    def get_dependencies(self) -> list[AgentType]:
        return [AgentType.MATCH]

    def get_required_skills(self) -> list[str]:
        return ["INDUSTRY_CHAIN"]

    def estimate_cost(self, task: TaskNode) -> int:
        return 10

    def estimate_duration(self, task: TaskNode) -> float:
        return 25.0

    async def execute(self, task: TaskNode, context: dict) -> TaskResult:
        """
        执行产业链分析

        Args:
            task: 包含分析参数
            context: 上游MATCH的匹配结果

        Returns:
            产业链分析结果
        """
        match_data = context.get("MATCH", {})
        # TODO: 调用IndustryChainSkill进行深度分析

        return TaskResult(
            task_id=task.task_id,
            success=True,
            data={
                "proximity_score": 0.68,
                "top_dimensions": ["supply_chain", "technology", "market"],
                "upstream": [
                    {"segment": "原材料供应", "companies": ["供应商A", "供应商B"]},
                    {"segment": "核心零部件", "companies": ["制造商C"]},
                ],
                "midstream": [
                    {"segment": "制造加工", "companies": ["加工厂D"]},
                    {"segment": "系统集成", "companies": ["集成商E"]},
                ],
                "downstream": [
                    {"segment": "渠道分销", "companies": ["分销商F"]},
                    {"segment": "终端客户", "companies": ["客户G", "客户H"]},
                ],
                "opportunity_areas": [
                    "上游供应稳定性优化",
                    "中游技术创新突破",
                    "下游渠道整合拓展",
                ],
                "collaboration_potential": "high",
            },
            action_power_used=10,
        )


# ===== FINANCE — 金融智能体 =====

class FinanceAgent(BaseAgent):
    """
    金融智能体 — 行动力计费与金融服务

    职责:
      1. 行动力消耗计算与结算
      2. 融资/投资匹配
      3. 财务健康度评估

    依赖: INDUSTRY + COACH
    """

    @property
    def agent_type(self) -> AgentType:
        return AgentType.FINANCE

    @property
    def description(self) -> str:
        return "金融服务 — 融资匹配+行动力结算+财务评估"

    def get_dependencies(self) -> list[AgentType]:
        return [AgentType.INDUSTRY, AgentType.COACH]

    def get_required_skills(self) -> list[str]:
        return []

    def estimate_cost(self, task: TaskNode) -> int:
        return 3  # FINANCE本身收费低，主要是结算功能

    def estimate_duration(self, task: TaskNode) -> float:
        return 10.0

    async def execute(self, task: TaskNode, context: dict) -> TaskResult:
        """
        执行金融服务

        Args:
            task: 包含金融需求参数
            context: 上游INDUSTRY+COACH的结果

        Returns:
            金融服务结果
        """
        industry_data = context.get("INDUSTRY", {})
        coach_data = context.get("COACH", {})

        collaboration = industry_data.get("data", {}).get("collaboration_potential", "medium")
        stage = coach_data.get("data", {}).get("diagnosis", {}).get("current_stage", "成长期")

        # 根据产业链和教练诊断推荐金融方案
        finance_plans = []
        if collaboration == "high":
            finance_plans.append({
                "type": "供应链金融",
                "description": "基于产业链协作的供应链融资方案",
                "estimated_amount": "50-200万",
                "conditions": ["有稳定上下游关系", "交易记录良好"],
            })

        finance_plans.append({
            "type": "信用评估",
            "description": f"基于{stage}阶段的企业信用评估",
            "credit_suggestion": "建议先完善企业信息以获得更精准的评估",
        })

        return TaskResult(
            task_id=task.task_id,
            success=True,
            data={
                "finance_plans": finance_plans,
                "billing_summary": {
                    "total_action_power_used": sum(
                        context.get(k, {}).get("action_power_used", 0)
                        for k in ["MATCH", "NAMECARD", "ACTIVITY", "SECRETARY", "COACH", "INDUSTRY"]
                        if isinstance(context.get(k), dict)
                    ),
                },
            },
            action_power_used=3,
        )


# ===== CUSTOM — 定制智能体 =====

class CustomAgent(BaseAgent):
    """
    定制智能体 — 扩展用

    职责:
      1. 处理非标准化的用户需求
      2. 可扩展的定制逻辑
      3. 支持用户自定义流程

    依赖: MASTER
    并行: 与MATCH并行
    """

    @property
    def agent_type(self) -> AgentType:
        return AgentType.CUSTOM

    @property
    def description(self) -> str:
        return "定制服务 — 非标准需求处理与扩展"

    def get_dependencies(self) -> list[AgentType]:
        return [AgentType.MASTER]

    def get_required_skills(self) -> list[str]:
        return []

    def estimate_cost(self, task: TaskNode) -> int:
        return 8

    def estimate_duration(self, task: TaskNode) -> float:
        return 20.0

    async def execute(self, task: TaskNode, context: dict) -> TaskResult:
        """
        执行定制服务

        Args:
            task: 包含定制需求参数
            context: 上游MASTER的解析结果

        Returns:
            定制服务结果
        """
        master_data = context.get("MASTER", {})
        intent = master_data.get("data", {}).get("intent", "")

        # TODO: 根据具体定制需求执行逻辑
        return TaskResult(
            task_id=task.task_id,
            success=True,
            data={
                "custom_result": {
                    "request": intent,
                    "status": "已记录定制需求",
                    "next_steps": [
                        "需求确认与细化",
                        "方案设计与评估",
                        "执行与交付",
                    ],
                },
            },
            action_power_used=8,
        )


# ===== 智能体注册表 =====

def create_all_agents() -> dict[AgentType, BaseAgent]:
    """
    创建并注册所有9大智能体

    Returns:
        智能体类型→实例的映射字典
    """
    agents: dict[AgentType, BaseAgent] = {
        AgentType.MASTER: MasterAgent(),
        AgentType.MATCH: MatchAgent(),
        AgentType.NAMECARD: NamecardAgent(),
        AgentType.ACTIVITY: ActivityAgent(),
        AgentType.SECRETARY: SecretaryAgent(),
        AgentType.COACH: CoachAgent(),
        AgentType.INDUSTRY: IndustryAgent(),
        AgentType.FINANCE: FinanceAgent(),
        AgentType.CUSTOM: CustomAgent(),
    }
    return agents


# 智能体依赖关系定义(用于DAG构建)
AGENT_DEPENDENCY_MAP: dict[AgentType, list[AgentType]] = {
    AgentType.MASTER: [],
    AgentType.MATCH: [AgentType.MASTER],
    AgentType.NAMECARD: [AgentType.MATCH],
    AgentType.ACTIVITY: [AgentType.MATCH],
    AgentType.SECRETARY: [AgentType.NAMECARD, AgentType.INDUSTRY],
    AgentType.COACH: [AgentType.SECRETARY, AgentType.MASTER],
    AgentType.INDUSTRY: [AgentType.MATCH],
    AgentType.FINANCE: [AgentType.INDUSTRY, AgentType.COACH],
    AgentType.CUSTOM: [AgentType.MASTER],
}

# 智能体行动力消耗映射
AGENT_COST_MAP: dict[AgentType, int] = {
    AgentType.MASTER: 0,
    AgentType.MATCH: 15,
    AgentType.NAMECARD: 5,
    AgentType.ACTIVITY: 5,
    AgentType.SECRETARY: 8,
    AgentType.COACH: 10,
    AgentType.INDUSTRY: 10,
    AgentType.FINANCE: 3,
    AgentType.CUSTOM: 8,
}

# 智能体预估耗时映射(秒)
AGENT_DURATION_MAP: dict[AgentType, float] = {
    AgentType.MASTER: 5.0,
    AgentType.MATCH: 30.0,
    AgentType.NAMECARD: 15.0,
    AgentType.ACTIVITY: 15.0,
    AgentType.SECRETARY: 20.0,
    AgentType.COACH: 25.0,
    AgentType.INDUSTRY: 25.0,
    AgentType.FINANCE: 10.0,
    AgentType.CUSTOM: 20.0,
}
