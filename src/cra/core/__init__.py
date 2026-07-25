"""核心配置：基于 pydantic-settings 的统一配置入口。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _load_env_file() -> None:
    """加载 .env 文件到 os.environ。

    必须在 Settings 实例化前调用，确保 litellm 能读到 ANTHROPIC_API_KEY 等变量。
    """
    try:
        from dotenv import load_dotenv  # noqa: PLC0415
    except ImportError:
        return
    # 从项目根目录加载（向上查找 pyproject.toml）
    root = Path(__file__).resolve().parents[3]
    for candidate in [root / ".env", root.parent / ".env"]:
        if candidate.exists():
            load_dotenv(candidate, override=False)
            break


# 模块导入时即加载（重要：早于 Settings 实例化）
_load_env_file()


class Settings(BaseSettings):
    """全局配置：环境变量 > .env 文件 > 默认值。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CRA_",
        extra="ignore",
    )

    # --- 环境 ---
    env: str = Field(default="dev", validation_alias="CRA_ENV")

    # --- LLM 配置 ---
    default_model: str = Field(
        default="deepseek/deepseek-chat",
        validation_alias="CRA_DEFAULT_MODEL",
    )
    deep_model: str = Field(
        default="claude-3-5-sonnet-20241022",
        validation_alias="CRA_DEEP_MODEL",
    )
    llm_timeout: int = Field(default=30, validation_alias="CRA_LLM_TIMEOUT")

    # --- API Keys（透传给 litellm）---
    # litellm 直接读 ANTHROPIC_API_KEY / OPENAI_API_KEY / DEEPSEEK_API_KEY
    # 这里不重复声明

    # --- 审查策略 ---
    confidence_threshold: float = Field(default=0.5, validation_alias="CRA_CONFIDENCE_THRESHOLD")
    max_findings_per_file: int = Field(default=5, validation_alias="CRA_MAX_FINDINGS_PER_FILE")
    max_cost_per_review: float = Field(default=5.0, validation_alias="CRA_MAX_COST_PER_REVIEW")

    # --- 日志 ---
    log_level: str = Field(default="INFO", validation_alias="CRA_LOG_LEVEL")
    log_format: str = Field(default="console", validation_alias="CRA_LOG_FORMAT")

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parents[3]

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"


@lru_cache
def get_settings() -> Settings:
    """单例获取配置。"""
    return Settings()
