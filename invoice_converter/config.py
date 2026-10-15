"""
Centralized configuration. All environment-variable reads happen here, in
one place, so a missing/misnamed variable fails loudly at startup with a
clear message instead of surfacing as a confusing error deep in an API call.
"""
import os
from dataclasses import dataclass

from .exceptions import ConfigError


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    model: str
    request_timeout: int = 60
    max_retries: int = 2


def load_settings() -> Settings:
    """Load and validate settings from environment variables.

    Required:
        QWEN_API_KEY   - your API key for the vision endpoint
        QWEN_BASE_URL  - OpenAI-compatible base URL (OpenRouter, DashScope
                         compatible-mode, self-hosted vLLM, etc.)
    Optional:
        QWEN_MODEL           - defaults to "qwen/qwen3.7-plus"
        QWEN_TIMEOUT_SECONDS - defaults to 60
        QWEN_MAX_RETRIES     - defaults to 2

    Raises:
        ConfigError if a required variable is missing or empty.
    """
    api_key = os.environ.get("QWEN_API_KEY", "").strip()
    base_url = os.environ.get("QWEN_BASE_URL", "").strip()
    model = os.environ.get("QWEN_MODEL", "qwen/qwen3.7-plus").strip()

    missing = []
    if not api_key:
        missing.append("QWEN_API_KEY")
    if not base_url:
        missing.append("QWEN_BASE_URL")
    if missing:
        raise ConfigError(
            "Missing required environment variable(s): "
            + ", ".join(missing)
            + ". Set them (e.g. in a .env file or your shell) before running. "
            "See .env.example for the expected format."
        )

    try:
        timeout = int(os.environ.get("QWEN_TIMEOUT_SECONDS", "60"))
        retries = int(os.environ.get("QWEN_MAX_RETRIES", "2"))
    except ValueError as e:
        raise ConfigError(f"QWEN_TIMEOUT_SECONDS / QWEN_MAX_RETRIES must be integers: {e}")

    return Settings(
        api_key=api_key,
        base_url=base_url,
        model=model,
        request_timeout=timeout,
        max_retries=retries,
    )
