"""
SQLAlchemy 跨数据库兼容类型
同时支持 PostgreSQL (UUID/JSONB) 和 SQLite (TEXT)
"""
from sqlalchemy import String, Text, JSON
from sqlalchemy.dialects.postgresql import UUID as _PG_UUID, JSONB as _PG_JSONB

# ── UUID 兼容 ──────────────────────────────────────────
# PostgreSQL: 使用原生 UUID 类型
# SQLite: 使用 TEXT (UUID 存储为字符串)
GUID = _PG_UUID  # dialect-specific, handled by type compilation


def pg_uuid_as_primary():
    """返回适合作为主键的 UUID 列类型"""
    return _PG_UUID()


# ── JSONB 兼容 ──────────────────────────────────────────
# PostgreSQL: 使用 JSONB (二进制 JSON，支持索引)
# SQLite: 使用 JSON (文本 JSON，SQLite 原生支持)
JSONB = _PG_JSONB

JSON_COL = JSON  # 通用 JSON 类型，cross-dialect safe

# ── Server-default UUID 生成 ──────────────────────────
# 在 SQLite 下需要 Python 侧生成，PostgreSQL 用 server_default
UUID_SERVER_DEFAULT = "gen_random_uuid()"