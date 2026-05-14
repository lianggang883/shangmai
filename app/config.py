"""
商脉系统 — 项目配置
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """全局配置，支持环境变量覆盖"""

    # ===== 应用 =====
    APP_NAME: str = "商脉系统"
    APP_VERSION: str = "v1.0.0"
    DEBUG: bool = True

    # ===== 数据库 =====
    DATABASE_URL: str = "postgresql+asyncpg://shangmai:shangmai@localhost:5432/shangmai"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # ===== 向量数据库 =====
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530
    MILVUS_COLLECTION: str = "member_vectors"
    VECTOR_DIM: int = 768

    # ===== 知识图谱 =====
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "shangmai"

    # ===== 缓存 =====
    REDIS_URL: str = "redis://localhost:6379/0"

    # ===== 认证 =====
    JWT_SECRET: str = "change-me-in-production-2026"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ===== 微信 =====
    WECHAT_APP_ID: str = ""
    WECHAT_APP_SECRET: str = ""
    WECHAT_MCH_ID: str = ""

    # ===== LLM =====
    LLM_PROVIDER: str = "openai"  # openai | claude | azure
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o"
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_EMBED_MODEL: str = "text-embedding-3-large"
    LLM_EMBED_DIM: int = 768

    # ===== 行动力计费 =====
    ACTION_POWER_MONTHLY_FREE_LV1: int = 1000
    ACTION_POWER_MONTHLY_FREE_LV2: int = 80
    ACTION_POWER_MONTHLY_FREE_LV3: int = 120
    ACTION_POWER_MONTHLY_FREE_LV4: int = 180
    ACTION_POWER_MONTHLY_FREE_LV5: int = 260
    ACTION_POWER_MONTHLY_FREE_LV6: int = 360
    ACTION_POWER_BIG_BUDGET_THRESHOLD: int = 500
    REFERRAL_DEFAULT_RATE: float = 0.10
    REFERRAL_MAX_RATE: float = 0.30

    # ===== 游戏化 =====
    EXP_TABLE_LV2: int = 100
    EXP_TABLE_LV3: int = 500
    EXP_TABLE_LV4: int = 2000
    EXP_TABLE_LV5: int = 8000
    EXP_TABLE_LV6: int = 30000

    POINTS_CHECKIN: int = 5
    POINTS_INTERACTION: int = 10
    POINTS_ICEBREAK: int = 20
    POINTS_MEETING: int = 50
    POINTS_COOPERATION: int = 100

    # ===== 关系衰退 =====
    DECAY_YELLOW_DAYS: int = 15
    DECAY_ORANGE_DAYS: int = 60
    DECAY_RED_DAYS: int = 90

    # ===== 日志 =====
    LOG_LEVEL: str = "INFO"

    # ===== 腾讯云COS =====
    COS_SECRET_ID: str = ""
    COS_SECRET_KEY: str = ""
    COS_BUCKET: str = ""
    COS_REGION: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# 行动力月度免费额度映射
MONTHLY_FREE_AP_MAP = {
    1: settings.ACTION_POWER_MONTHLY_FREE_LV1,
    2: settings.ACTION_POWER_MONTHLY_FREE_LV2,
    3: settings.ACTION_POWER_MONTHLY_FREE_LV3,
    4: settings.ACTION_POWER_MONTHLY_FREE_LV4,
    5: settings.ACTION_POWER_MONTHLY_FREE_LV5,
    6: settings.ACTION_POWER_MONTHLY_FREE_LV6,
}

# 等级经验表
EXP_TABLE = {
    2: settings.EXP_TABLE_LV2,
    3: settings.EXP_TABLE_LV3,
    4: settings.EXP_TABLE_LV4,
    5: settings.EXP_TABLE_LV5,
    6: settings.EXP_TABLE_LV6,
}
