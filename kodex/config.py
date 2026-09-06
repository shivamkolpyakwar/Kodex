"""
Kodex Configuration Module.

Centralizes all application settings, environment variable loading,
and constants. Uses Pydantic Settings for validated configuration.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# =============================================================================
# Path Constants
# =============================================================================
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
DOTENV_PATH: Path = PROJECT_ROOT / ".env"


# =============================================================================
# Application Settings
# =============================================================================
class KodexSettings(BaseSettings):
    """
    Validated application settings loaded from environment variables.

    All settings can be overridden via a .env file at the project root
    or by setting environment variables directly.
    """

    model_config = SettingsConfigDict(
        env_file=str(DOTENV_PATH),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── LLM Provider ───────────────────────────────────────────────────
    openai_api_key: str = Field(
        default="",
        description="OpenAI API key for LLM and embedding calls.",
    )
    openai_model: str = Field(
        default="gpt-4o",
        description="Model name for reasoning tasks.",
    )
    openai_embedding_model: str = Field(
        default="text-embedding-3-small",
        description="Model name for embedding generation.",
    )

    # ─── Qdrant Vector Database ─────────────────────────────────────────
    qdrant_url: str = Field(
        default="http://localhost:6333",
        description="Qdrant server URL.",
    )
    qdrant_api_key: str = Field(
        default="",
        description="Qdrant API key (optional for local).",
    )
    qdrant_collection_name: str = Field(
        default="kodex_codebase",
        description="Name of the Qdrant collection.",
    )

    # ─── Docker Sandbox ─────────────────────────────────────────────────
    sandbox_image: str = Field(
        default="kodex-sandbox:latest",
        description="Docker image for sandbox execution.",
    )
    sandbox_timeout: int = Field(
        default=60,
        ge=10,
        le=300,
        description="Max seconds for sandbox execution.",
    )
    sandbox_memory_limit: str = Field(
        default="512m",
        description="Docker memory limit for sandbox containers.",
    )
    sandbox_cpu_quota: int = Field(
        default=50000,
        ge=10000,
        le=100000,
        description="Docker CPU quota (microseconds per 100ms period).",
    )

    # ─── Agent Configuration ────────────────────────────────────────────
    confidence_threshold: int = Field(
        default=60,
        ge=0,
        le=100,
        description="Min confidence (0-100) to auto-apply a fix.",
    )
    max_retries: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Max retries per error before skipping.",
    )
    default_mode: str = Field(
        default="review",
        description="Default agent mode: 'auto' or 'review'.",
    )

    # ─── Session & Logging ──────────────────────────────────────────────
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR).",
    )
    session_dir: str = Field(
        default="./sessions",
        description="Directory for saved sessions.",
    )
    audit_log_dir: str = Field(
        default="./audit_logs",
        description="Directory for audit log files.",
    )

    # ─── Token Cost Configuration (USD per 1K tokens) ───────────────────
    cost_per_1k_prompt_tokens: float = Field(
        default=0.0025,
        ge=0.0,
        description="Cost per 1,000 prompt tokens in USD.",
    )
    cost_per_1k_completion_tokens: float = Field(
        default=0.01,
        ge=0.0,
        description="Cost per 1,000 completion tokens in USD.",
    )
    cost_per_1k_embedding_tokens: float = Field(
        default=0.00002,
        ge=0.0,
        description="Cost per 1,000 embedding tokens in USD.",
    )

    # ─── Validators ─────────────────────────────────────────────────────
    @field_validator("default_mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        """Ensure mode is either 'auto' or 'review'."""
        allowed = {"auto", "review"}
        if v.lower() not in allowed:
            raise ValueError(f"Mode must be one of {allowed}, got '{v}'")
        return v.lower()

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure log level is valid."""
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in allowed:
            raise ValueError(f"Log level must be one of {allowed}, got '{v}'")
        return v.upper()


# =============================================================================
# Token Cost Lookup Table
# =============================================================================
MODEL_COSTS: dict[str, dict[str, float]] = {
    "gpt-4o": {"prompt": 0.0025, "completion": 0.01},
    "gpt-4o-mini": {"prompt": 0.00015, "completion": 0.0006},
    "gpt-4-turbo": {"prompt": 0.01, "completion": 0.03},
    "text-embedding-3-small": {"prompt": 0.00002, "completion": 0.0},
    "text-embedding-3-large": {"prompt": 0.00013, "completion": 0.0},
}

# =============================================================================
# Supported File Extensions for RAG Indexing
# =============================================================================
SUPPORTED_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".java", ".go", ".rs", ".rb", ".php",
    ".c", ".cpp", ".h", ".hpp", ".cs",
    ".yaml", ".yml", ".toml", ".json",
    ".md", ".txt", ".cfg", ".ini",
}

# =============================================================================
# Files / Directories to Exclude from Indexing
# =============================================================================
EXCLUDED_DIRS: set[str] = {
    "__pycache__", ".git", ".venv", "venv", "node_modules",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist",
    "build", "egg-info", ".tox", ".nox", ".eggs",
}

EXCLUDED_FILES: set[str] = {
    ".DS_Store", "Thumbs.db", ".gitignore",
}


# =============================================================================
# Singleton Settings Instance
# =============================================================================
def get_settings() -> KodexSettings:
    """
    Return the application settings singleton.

    Creates the settings instance on first call, loading from
    environment variables and .env file.

    Returns:
        KodexSettings: Validated application settings.
    """
    if not hasattr(get_settings, "_instance"):
        get_settings._instance = KodexSettings()  # type: ignore[attr-defined]
    return get_settings._instance  # type: ignore[attr-defined]


def ensure_directories(settings: KodexSettings | None = None) -> None:
    """
    Create required directories if they don't exist.

    Args:
        settings: Optional settings instance. Uses singleton if None.
    """
    s = settings or get_settings()
    for dir_path in [s.session_dir, s.audit_log_dir]:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
