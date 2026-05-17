"""商脉系统 - FastAPI 应用"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db, close_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()

app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION,
    description="AI原生商业关系赋能平台", lifespan=lifespan)

app.add_middleware(CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else [],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

from app.api import auth, roles, resources, members, matching, relations, cooperations, skills, game, agents, activities, billing, upload, reports, referral, notifications
from app.api import admin
app.include_router(roles.router)
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(admin.auth.router, prefix="/admin", tags=["管理员"])
app.include_router(admin.members.router, prefix="/admin/members", tags=["管理员-会员"])
app.include_router(admin.dashboard.router, prefix="/admin", tags=["管理员-仪表盘"])
app.include_router(admin.activities.router, prefix="/admin", tags=["管理员-活动"])
app.include_router(admin.notifications.router, prefix="/admin", tags=["管理员-通知"])
app.include_router(admin.skills.router, prefix="/admin", tags=["管理员-SKILL监控"])
app.include_router(members.router, prefix="/api/v1/members", tags=["Members"])
app.include_router(matching.router, prefix="/api/v1/matching", tags=["Matching"])
app.include_router(relations.router, prefix="/api/v1/relations", tags=["Relations"])
app.include_router(cooperations.router, prefix="/api/v1/cooperations", tags=["Cooperations"])
app.include_router(skills.router, prefix="/api/v1/skills", tags=["Skills"])
app.include_router(game.router, prefix="/api/v1/game", tags=["Game"])
app.include_router(agents.router, prefix="/api/v1/agents", tags=["Agents"])
app.include_router(resources.router, prefix="/api/v1/resources", tags=["Resources"])
app.include_router(activities.router, prefix="/api/v1/activities", tags=["Activities"])
app.include_router(billing.router, prefix="/api/v1/billing", tags=["Billing"])
app.include_router(upload.router, prefix="/api/v1/upload", tags=["Upload"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["Reports"])
app.include_router(notifications.router, prefix="/api/v1/notifications", tags=["Notifications"])
app.include_router(referral.router, prefix="/api/v1/referral", tags=["Referral"])

@app.get("/")
async def health_check():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}

@app.get("/health")
async def health():
    return {"status": "ok"}
