"""
商脉系统 — 数据库连接 (SQLite 开发版)
支持 aiosqlite，在无 PostgreSQL 环境时自动降级
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.config import settings


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite") or "sqlite" in url.lower()


_sqlite_mode = _is_sqlite(settings.DATABASE_URL)

# ── Engine ─────────────────────────────────────────────
if _sqlite_mode:
    engine = create_async_engine(
        "sqlite+aiosqlite:///./shangmai_dev.db",
        echo=settings.DEBUG,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        echo=settings.DEBUG,
    )

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

DATABASE_DIALECT = "sqlite" if _sqlite_mode else "postgresql"


async def get_db() -> AsyncSession:
    """FastAPI 依赖注入：获取异步数据库会话"""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """初始化数据库（创建所有表）"""
    from app.models import Base as ModelsBase
    async with engine.begin() as conn:
        await conn.run_sync(ModelsBase.metadata.create_all)


async def close_db():
    """关闭数据库连接池"""
    await engine.dispose()
