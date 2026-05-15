"""
共享 conftest — SQLite 内存数据库 + 测试客户端
"""
import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# 先导入 app.models.base 的 Base，再导入 AdminUser
# 这样 AdminUser 会注册到同一个 Base.metadata
from app.models.base import Base as _RealBase
# app.models 会创建第二个 Base，我们不用它
from app.models import Base  # noqa — 这是 conftest 实际用的 Base
# 确保所有模型加载
from app.models.admin_user import AdminUser  # noqa

# 问题是 AdminUser 注册到了 app.models.base.Base 而非 app.models.Base
# 修复：将 admin_users 表定义手动添加到 app.models.Base.metadata
# 或者更简单：直接用 app.models.base.Base 作为测试的 Base
Base = _RealBase  # 使用 AdminUser 注册到的那个 Base

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
    # 确保所有模型表被创建
    # 先导入所有 app.models 子模块让它们注册到 _RealBase
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
    # 这些模型注册到了 app.models.Base（第二个 Base），需要手动合并
    # 最简单的办法：用 _RealBase 的 metadata，把缺失的表补上
    from app.models import Base as AppBase  # noqa
    for table_name, table_obj in AppBase.metadata.tables.items():
        if table_name not in _RealBase.metadata.tables:
            _RealBase.metadata._add_table(table_name, table_obj.schema, table_obj)

    async with eng.begin() as conn:
        await conn.run_sync(_RealBase.metadata.create_all)
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
