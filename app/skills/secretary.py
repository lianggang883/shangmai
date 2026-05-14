"""
商脉系统 · 商务秘书 SKILL (v1.0.0)
小龙四 — 破冰方案 / 跟进提醒 / 会话摘要 / 联络建议
"""
import json
import re
import logging

from app.skills.base import BaseSkill, SkillType, SkillInput, SkillOutput, ValidationResult

logger = logging.getLogger(__name__)


class SecretarySkill(BaseSkill):
    @property
    def skill_type(self) -> SkillType:
        return SkillType.SECRETARY

    @property
    def version(self) -> str:
        return "1.0.0"

    def validate(self, input_data: SkillInput) -> ValidationResult:
        mode = input_data.context.get("mode", "")
        valid_modes = ("icebreak", "followup", "summary", "contact_advice")
        if mode not in valid_modes:
            return ValidationResult(
                is_valid=False,
                errors=[f"无效模式: {mode}，支持: {valid_modes}"]
            )
        return ValidationResult(is_valid=True, errors=[])

    def estimate_cost(self, input_data: SkillInput) -> int:
        return {
            "icebreak": 8,
            "followup": 5,
            "summary": 3,
            "contact_advice": 5,
        }.get(input_data.context.get("mode", ""), 5)

    def get_required_skills(self) -> list[SkillType]:
        return [SkillType.MCKINSEY, SkillType.COACH]

    async def execute(self, input_data: SkillInput) -> SkillOutput:
        mode = input_data.context.get("mode", "")
        if mode == "icebreak":
            return await self._icebreak(input_data)
        elif mode == "followup":
            return await self._followup(input_data)
        elif mode == "summary":
            return await self._summary(input_data)
        elif mode == "contact_advice":
            return await self._contact_advice(input_data)

    # ─────────────────────────────────────────────
    # 破冰方案
    # ─────────────────────────────────────────────
    async def _icebreak(self, input_data: SkillInput) -> SkillOutput:
        member_a = input_data.context.get("member_a", {})
        member_b = input_data.context.get("member_b", {})
        match_score = input_data.context.get("match_score", 0)
        common_points = input_data.context.get("common_points", [])

        try:
            from app.utils.llm import get_llm_client

            r = await get_llm_client().chat([
                {
                    "role": "system",
                    "content": "你是商脉平台的商务秘书，擅长设计破冰话术。只返回JSON。"
                },
                {
                    "role": "user",
                    "content": f"""【会员A】
姓名: {member_a.get('name','')}
行业: {member_a.get('industry','')}
职位: {member_a.get('title','')}
需求: {member_a.get('needs','')}

【会员B】
姓名: {member_b.get('name','')}
行业: {member_b.get('industry','')}
职位: {member_b.get('title','')}
需求: {member_b.get('needs','')}

匹配分: {match_score}
共同点: {', '.join(common_points) if common_points else '暂无'}

请设计一套破冰方案：
返回JSON: {{
  "icebreaker_script": "开场白话术（100字以内）",
  "conversation_topics": ["话题1", "话题2", "话题3"],
  "best_timing": "最佳破冰时机说明",
  "best_channel": "微信/电话/线下等",
  "tips": ["注意事项1", "注意事项2"],
  "follow_up_message": "跟进消息模板（可选）"
}}"""
                }
            ], temperature=0.7, max_tokens=1500)

            m = re.search(r'\{.*\}', r, re.DOTALL)
            if m:
                return SkillOutput(
                    success=True,
                    data=json.loads(m.group()),
                    action_power_used=8,
                    next_skill_hint=SkillType.COACH
                )
        except Exception as e:
            logger.warning(f"LLM icebreak fail: {e}")

        # Fallback
        return SkillOutput(
            success=True,
            data={
                "icebreaker_script": f"您好，我是{member_a.get('name', '双方')}，在商脉平台看到您的信息，觉得我们在{common_points[0] if common_points else '业务方向'}上很有契合点，想和您深入交流一下。",
                "conversation_topics": common_points or ["行业趋势", "合作机会"],
                "best_timing": "工作日 10:00-11:30 或 14:00-16:00",
                "best_channel": "微信优先",
                "tips": ["先表达欣赏而非直接求合作", "以请教姿态开场更易建立信任"],
                "follow_up_message": ""
            },
            action_power_used=8
        )

    # ─────────────────────────────────────────────
    # 跟进提醒
    # ─────────────────────────────────────────────
    async def _followup(self, input_data: SkillInput) -> SkillOutput:
        last_interaction = input_data.context.get("last_interaction", "")
        last_time = input_data.context.get("last_time", "")
        member_info = input_data.context.get("member_info", {})

        try:
            from app.utils.llm import get_llm_client

            r = await get_llm_client().chat([
                {
                    "role": "system",
                    "content": "你是商脉平台的商务秘书，擅长制定跟进计划。只返回JSON。"
                },
                {
                    "role": "user",
                    "content": f"""【上次互动】
时间: {last_time}
内容: {last_interaction}

【目标会员】
姓名: {member_info.get('name','')}
行业: {member_info.get('industry','')}
阶段: {member_info.get('stage','')}

请制定跟进计划：
返回JSON: {{
  "followup_plan": [
    {{"day": "Day 1-3", "action": "跟进动作", "channel": "渠道", "script": "话术"}},
    {{"day": "Day 4-7", "action": "跟进动作", "channel": "渠道", "script": "话术"}},
    {{"day": "Day 8-14", "action": "跟进动作", "channel": "渠道", "script": "话术"}}
  ],
  "reminder_time": "下次最佳跟进时间",
  "key_points": ["核心跟进要点1", "核心跟进要点2"],
  "red_flags": ["避免踩坑1", "避免踩坑2"]
}}"""
                }
            ], temperature=0.5, max_tokens=1200)

            m = re.search(r'\{.*\}', r, re.DOTALL)
            if m:
                return SkillOutput(
                    success=True,
                    data=json.loads(m.group()),
                    action_power_used=5
                )
        except Exception as e:
            logger.warning(f"LLM followup fail: {e}")

        # Fallback
        return SkillOutput(
            success=True,
            data={
                "followup_plan": [
                    {"day": "Day 1-3", "action": "发送价值型消息", "channel": "微信", "script": "上次聊到的话题延续 + 提供一个有帮助的资源"},
                    {"day": "Day 4-7", "action": "轻触达确认", "channel": "微信", "script": "分享相关行业动态或活动邀请"},
                    {"day": "Day 8-14", "action": "深度互动", "channel": "视情况", "script": "提出具体合作方向或邀请线下交流"}
                ],
                "reminder_time": "建议3天内完成首次跟进",
                "key_points": ["延续上次话题，展示持续关注", "提供对方感兴趣的价值"],
                "red_flags": ["避免连续催促造成压力", "避免目的性太强的话术"]
            },
            action_power_used=5
        )

    # ─────────────────────────────────────────────
    # 会话摘要
    # ─────────────────────────────────────────────
    async def _summary(self, input_data: SkillInput) -> SkillOutput:
        history = input_data.context.get("history", [])
        match_result = input_data.context.get("match_result", None)

        try:
            from app.utils.llm import get_llm_client

            history_text = "\n".join([
                f"[{h.get('speaker','?')}] {h.get('content','')}"
                for h in history[-10:]
            ]) if history else "（无历史对话）"

            r = await get_llm_client().chat([
                {
                    "role": "system",
                    "content": "你是商脉平台的商务秘书，擅长提炼关键信息，生成结构化摘要。只返回JSON。"
                },
                {
                    "role": "user",
                    "content": f"""【对话历史（最近10轮）】
{history_text}

【匹配结果摘要】
{match_result if match_result else '暂无'}

请生成结构化摘要：
返回JSON: {{
  "summary": "2-3句话概括核心内容",
  "key_decisions": ["决策1", "决策2"],
  "action_items": [
    {{"owner": "谁负责", "task": "任务", "deadline": "时间"}}
  ],
  "next_step": "下一步计划",
  "sentiment": "positive/neutral/negative",
  "notes": "补充备注（可选）"
}}"""
                }
            ], temperature=0.3, max_tokens=1000)

            m = re.search(r'\{.*\}', r, re.DOTALL)
            if m:
                return SkillOutput(
                    success=True,
                    data=json.loads(m.group()),
                    action_power_used=3
                )
        except Exception as e:
            logger.warning(f"LLM summary fail: {e}")

        # Fallback
        return SkillOutput(
            success=True,
            data={
                "summary": "对话已记录，请接入LLM获取详细摘要。",
                "key_decisions": [],
                "action_items": [],
                "next_step": "请补充对话内容后重试",
                "sentiment": "neutral",
                "notes": "LLM调用失败，使用默认摘要"
            },
            action_power_used=3
        )

    # ─────────────────────────────────────────────
    # 联络建议
    # ─────────────────────────────────────────────
    async def _contact_advice(self, input_data: SkillInput) -> SkillOutput:
        target = input_data.context.get("target_member", {})
        my_info = input_data.context.get("my_info", {})

        try:
            from app.utils.llm import get_llm_client

            r = await get_llm_client().chat([
                {
                    "role": "system",
                    "content": "你是商脉平台的商务秘书，擅长制定联络策略。只返回JSON。"
                },
                {
                    "role": "user",
                    "content": f"""【我的信息】
姓名: {my_info.get('name','')}
行业: {my_info.get('industry','')}
资源: {my_info.get('resources','')}

【目标会员画像】
姓名: {target.get('name','')}
行业: {target.get('industry','')}
职位: {target.get('title','')}
企业: {target.get('company','')}
痛点: {target.get('pain_points','')}
活跃时间: {target.get('active_time','')}
渠道偏好: {target.get('channel_preference','')}

请制定联络策略：
返回JSON: {{
  "contact_strategy": "整体策略一句话概括",
  "best_timing": "最佳联络时间段",
  "best_channel": "推荐渠道及理由",
  "opener_script": "开场话术（50字以内）",
  "value_hook": "为对方提供的价值点（让对方愿意回复的关键）",
  "objection_handling": [
    {{"objection": "对方可能顾虑", "response": "回应话术"}}
  ],
  "success_indicators": ["判断联络成功的信号1", "信号2"],
  "do_not_do": ["不要做的事1", "不要做的事2"]
}}"""
                }
            ], temperature=0.6, max_tokens=1500)

            m = re.search(r'\{.*\}', r, re.DOTALL)
            if m:
                return SkillOutput(
                    success=True,
                    data=json.loads(m.group()),
                    action_power_used=5,
                    next_skill_hint=SkillType.SECRETARY
                )
        except Exception as e:
            logger.warning(f"LLM contact_advice fail: {e}")

        # Fallback
        return SkillOutput(
            success=True,
            data={
                "contact_strategy": "以价值为导向，先建立信任再谈合作",
                "best_timing": f"工作日 {target.get('active_time', '10:00-11:30 / 14:00-16:00')}",
                "best_channel": target.get('channel_preference', '微信优先'),
                "opener_script": f"您好，我是{my_info.get('name','')}，在商脉平台了解到您在{target.get('industry','')}方向有丰富经验，想向您请教交流。",
                "value_hook": "展示自身资源优势，寻找互利合作点",
                "objection_handling": [
                    {"objection": "我很忙，没时间", "response": "只需10分钟，我想先分享一个可能对您有帮助的信息"},
                    {"objection": "暂时不需要", "response": "理解，先保持联系，后续有需要随时沟通"}
                ],
                "success_indicators": ["对方愿意继续对话", "交换了联系方式", "约定了下次沟通时间"],
                "do_not_do": ["不要上来就推产品", "不要群发模板消息", "不要频繁催促回复"]
            },
            action_power_used=5
        )
