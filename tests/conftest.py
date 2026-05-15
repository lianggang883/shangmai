"""
共享 conftest — SQLite 内存数据库 + 测试客户端
"""
import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.models.base import Base  # 唯一的 Base 定义
from app.models.admin_user import AdminUser  # noqa — 确保加载
# 导入所有模型确保注册到 Base.metadata
from app.models import (  # noqa
    Member, MemberRole, MemberInterest, MemberDiagnosis,
    Relationship, Interaction,
    CooperationProject, ProjectTask,
    ActionPowerAccount, ActionPowerTransaction, Subscription,
    GameProfile, GameTask, GameTaskProgress, GameLeaderboard,
    SkillInvocation, AgentTask,
    KnowledgeGraphNode, KnowledgeGraphEdge,
    ReferralRecord, UploadedFile, Activity, ActivityParticipant,
)

from app.config import settings  # noqa: E402
from app.dependencies.auth import create_access_token  # noqa: E402


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:", echo=False,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def db_session(engine):
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def client(db_session):
    from app.database import get_db
    from app.main import app

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def user_token(client):
    """注册用户并返回 access_token"""
    resp = await client.post("/api/v1/auth/register", json={"phone": "13900139001"})
    data = resp.json()
    return data["data"]["access_token"] if data.get("data") else None
