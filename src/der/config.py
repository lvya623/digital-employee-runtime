"""运行配置：环境变量优先，默认值保证零配置即可跑通 demo 与测试。"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    llm_provider: str = os.getenv("DER_LLM_PROVIDER", "mock")
    llm_base_url: str = os.getenv("DER_LLM_BASE_URL", "https://api.openai.com/v1")
    llm_api_key: str = os.getenv("DER_LLM_API_KEY", "")
    llm_model: str = os.getenv("DER_LLM_MODEL", "gpt-4o-mini")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./der.db")
    context_budget: int = _int("DER_CONTEXT_BUDGET", 2048)
    max_retries: int = _int("DER_MAX_RETRIES", 2)
    max_react_steps: int = _int("DER_MAX_REACT_STEPS", 12)
    reserved_output_tokens: int = _int("DER_RESERVED_OUTPUT_TOKENS", 512)


settings = Settings()
