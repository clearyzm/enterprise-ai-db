from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    APP_ENV: Literal["development", "staging", "production"] = "development"
    APP_DEBUG: bool = False
    APP_HOST: str = "0.0.0.0"  # nosec B104 - intentional for Docker
    APP_PORT: int = 8000
    APP_WORKERS: int = 1

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    DATABASE_URL: str
    POSTGRES_DB: str = "enterprise_ai"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: SecretStr = SecretStr("postgres")

    # ------------------------------------------------------------------
    # Redis
    # ------------------------------------------------------------------
    REDIS_URL: str = "redis://localhost:6379/0"

    # ------------------------------------------------------------------
    # Celery
    # ------------------------------------------------------------------
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ------------------------------------------------------------------
    # JWT
    # ------------------------------------------------------------------
    JWT_SECRET_KEY: SecretStr
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ------------------------------------------------------------------
    # 生成模型（D1 · 必须独立，不与嵌入模型合并）
    # LLM_MODEL        → classify / guardrail 等轻量节点
    # LLM_STRONG_MODEL → synthesize 节点（最终回答）
    # ------------------------------------------------------------------
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_API_KEY: SecretStr
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_STRONG_MODEL: str = "gpt-4o"

    # ------------------------------------------------------------------
    # 嵌入模型（D1 · 独立配置，允许不同供应商）
    # EMBED_API_KEY 为空字符串时运行时 fallback 到 LLM_API_KEY（见 embeddings.py）
    # ⚠️  换嵌入模型必须同步修改 EMBED_DIM（pgvector 列向量维度需匹配）
    # ------------------------------------------------------------------
    EMBED_BASE_URL: str = "https://api.openai.com/v1"
    EMBED_API_KEY: SecretStr = SecretStr("")
    EMBED_MODEL: str = "text-embedding-3-small"
    EMBED_DIM: int = 1536

    # ------------------------------------------------------------------
    # Rate limiting (slowapi)
    # ------------------------------------------------------------------
    RATE_LIMIT_DEFAULT: str = "100/minute"

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    @model_validator(mode="after")
    def _validate_embed_dim(self) -> "Settings":
        if self.EMBED_DIM not in (768, 1024, 1536, 3072):
            raise ValueError(
                f"EMBED_DIM={self.EMBED_DIM} is unusual. "
                "Common values: 768 (BGE-base), 1024 (BGE-large), "
                "1536 (text-embedding-3-small), 3072 (text-embedding-3-large). "
                "If intentional, update this validator."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
