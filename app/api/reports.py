"""AI运营分析报告API"""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import text
from app.schemas.common import ApiResponse, success, fail
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
from app.schemas.common import ApiResponse, success, fail
from app.dependencies.auth import get_current_member
from app.models.member import Member
import os

from app.config import settings
from app.database import get_db

router = APIRouter()


class ReportRequest(BaseModel):
    report_type: str = "daily"


_report_store: dict = {}


async def call_llm(prompt: str) -> str:
    """调用DeepSeek-V3生成分析"""
    api_key = os.getenv("LLM_API_KEY", getattr(settings, "LLM_API_KEY", ""))
    base_url = os.getenv("LLM_BASE_URL", getattr(settings, "LLM_BASE_URL", "https://api.siliconflow.cn/v1"))
    model = os.getenv("LLM_MODEL", getattr(settings, "LLM_MODEL", "deepseek-ai/DeepSeek-V3"))

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 2000,
            },
        )
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def safe_scalar(db, sql, params=None):
    """安全执行查询，失败返回0"""
    try:
        result = await db.execute(text(sql), params or {})
        return result.scalar() or 0
    except Exception:
        return 0


async def safe_fetchall(db, sql, params=None):
    """安全执行查询，失败返回空列表"""
    try:
        result = await db.execute(text(sql), params or {})
        return result.fetchall()
    except Exception:
        return []


async def collect_metrics(db: AsyncSession, report_type: str) -> dict:
    """从数据库收集运营指标"""
    now = datetime.now(timezone.utc)
    if report_type == "daily":
        since = now - timedelta(days=1)
    elif report_type == "weekly":
        since = now - timedelta(weeks=1)
    else:
        since = now - timedelta(days=30)

    total_members = await safe_scalar(db, "SELECT COUNT(*) FROM members")
    new_members = await safe_scalar(db, "SELECT COUNT(*) FROM members WHERE created_at >= :since", {"since": since})
    total_relations = await safe_scalar(db, "SELECT COUNT(*) FROM relationships")
    total_activities = await safe_scalar(db, "SELECT COUNT(*) FROM activities")
    total_action_power = await safe_scalar(db, "SELECT COALESCE(SUM(ABS(amount)), 0) FROM action_power_transactions")
    skill_invocations = await safe_scalar(db, "SELECT COUNT(*) FROM skill_invocations")
    total_projects = await safe_scalar(db, "SELECT COUNT(*) FROM cooperation_projects")
    active_members = await safe_scalar(db, "SELECT COUNT(*) FROM members WHERE updated_at >= :since", {"since": now - timedelta(days=7)})

    rows = await safe_fetchall(db, "SELECT strength, COUNT(*) as cnt FROM relationships GROUP BY strength")
    strength_dist = {row[0]: row[1] for row in rows}

    rows = await safe_fetchall(db,
        "SELECT m.name, COALESCE(SUM(ABS(apt.amount)), 0) as total "
        "FROM members m JOIN action_power_transactions apt ON m.id = apt.member_id "
        "GROUP BY m.id ORDER BY total DESC LIMIT 10")
    top_consumers = [{"name": row[0], "amount": row[1]} for row in rows]

    active_rate = round(active_members / total_members * 100, 1) if total_members > 0 else 0
    strong_rate = round(strength_dist.get("strong", 0) / total_relations * 100, 1) if total_relations > 0 else 0

    return {
        "total_members": total_members,
        "new_members": new_members,
        "active_rate": active_rate,
        "total_relations": total_relations,
        "strong_relation_rate": strong_rate,
        "strength_distribution": strength_dist,
        "total_activities": total_activities,
        "total_action_power": int(total_action_power),
        "skill_invocations": skill_invocations,
        "total_projects": total_projects,
        "top_consumers": top_consumers,
    }


@router.post("/generate")
async def generate_report(req: ReportRequest, db: AsyncSession = Depends(get_db)):
    """生成AI运营分析报告"""
    metrics = await collect_metrics(db, req.report_type)

    prompt = f"""你是商脉平台运营分析师。基于以下运营数据，生成专业的分析报告。

## 平台运营数据（{req.report_type}报）
- 会员总数: {metrics['total_members']}
- 本期新增: {metrics['new_members']}
- 活跃率: {metrics['active_rate']}%
- 关系总数: {metrics['total_relations']}
- 强关系占比: {metrics['strong_relation_rate']}%
- 关系强度分布: {metrics['strength_distribution']}
- 活动总数: {metrics['total_activities']}
- 行动力总消耗: {metrics['total_action_power']}
- SKILL调用次数: {metrics['skill_invocations']}
- 协作项目数: {metrics['total_projects']}

请从以下维度分析，用中文回答：

### 一、用户增长趋势
分析会员增长和活跃情况，判断平台健康度。

### 二、关系网络健康度
分析关系数量、强度分布，评估网络连接质量。

### 三、活跃度分析
分析活动参与、行动力消耗、SKILL使用情况。

### 四、关键风险点
识别可能的问题和风险。

### 五、运营建议
提供3-5条可执行的具体运营建议。
"""

    try:
        ai_result = await call_llm(prompt)
    except Exception as e:
        ai_result = f"AI分析暂不可用，错误: {str(e)}"

    parts = ai_result.split("### 五、运营建议")
    insights = parts[0].strip() if len(parts) > 1 else ai_result
    recommendations = parts[1].strip() if len(parts) > 1 else "详见分析内容"

    report_id = f"rpt_{req.report_type}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    report = {
        "report_id": report_id,
        "report_type": req.report_type,
        "metrics": metrics,
        "insights": insights,
        "recommendations": recommendations,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    _report_store[report_id] = report
    return report


@router.get("/list")
async def list_reports():
    """获取历史报告列表"""
    reports = [
        {
            "report_id": r["report_id"],
            "report_type": r["report_type"],
            "generated_at": r["generated_at"],
            "total_members": r["metrics"].get("total_members", 0),
        }
        for r in _report_store.values()
    ]
    return {"reports": sorted(reports, key=lambda x: x["generated_at"], reverse=True)}


@router.get("/{report_id}")
async def get_report(report_id: str):
    """获取报告详情"""
    if report_id not in _report_store:
        raise HTTPException(status_code=404, detail="Report not found")
    return _report_store[report_id]

@router.get("/summary", response_model=ApiResponse)
async def get_reports_summary(
    db: AsyncSession = Depends(get_db),
    _member: Member = Depends(get_current_member),
):
    """获取报告摘要统计（需登录）"""
    from sqlalchemy import func, select
    from app.models.member import Member as MemberModel
    
    # 总数
    total = (await db.execute(select(func.count()).select_from(MemberModel))).scalar() or 0
    
    # 今日新增
    from datetime import date
    today = date.today()
    new_today = (await db.execute(
        select(func.count())
        .select_from(MemberModel)
        .where(func.date(MemberModel.created_at) == today)
    )).scalar() or 0
    
    return success(data={
        "total_members": total,
        "new_today": new_today,
        "active_relations": 0,
        "pending_reports": 0,
    })
