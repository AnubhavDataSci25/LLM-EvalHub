"""Application configuration.

All settings are loaded from environment variables (or a local `.env` file).
Secrets never leave the backend process: the frontend receives only booleans
describing whether a provider has been configured.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Runtime settings for LLM-EvalHub."""

    model_config = SettingsConfigDict(
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application -----------------------------------------------------
    app_name: str = "LLM-EvalHub"
    app_env: str = Field(default="development")
    app_debug: bool = Field(default=True)
    api_prefix: str = "/api"
    secret_key: str = Field(default="dev-insecure-secret-key-change-in-production")
    encryption_key: str | None = None
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="text")  # text | json
    enable_metrics: bool = Field(default=False)

    # --- Authentication & Workspaces -------------------------------------
    auth_mode: str = Field(default="local")  # local | enabled
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    password_min_length: int = 8
    auth_rate_limit_requests: int = 5
    auth_rate_limit_window_seconds: int = 60
    redis_url: str | None = None

    # --- Background Jobs & Limits ----------------------------------------
    job_backend: str = Field(default="auto")  # auto | asyncio | arq
    workspace_max_concurrent_jobs: int = Field(default=2)
    workspace_daily_call_limit: int = Field(default=1000)

    # --- Persistence -----------------------------------------------------
    database_url: str = Field(default=f"sqlite:///{BACKEND_DIR / 'llm_evalhub.db'}")
    sql_echo: bool = False
    auto_migrate: bool = Field(default=True)

    # --- CORS ------------------------------------------------------------
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173"
    )

    # --- Provider credentials (server-side only) -------------------------
    gemini_api_key: str | None = None
    groq_api_key: str | None = None
    hf_api_key: str | None = None
    openrouter_api_key: str | None = None
    nvidia_nim_api_key: str | None = None
    ollama_enabled: bool = False

    # --- Provider base URLs (all overridable) ----------------------------
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    hf_base_url: str = "https://router.huggingface.co/v1"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    nvidia_nim_base_url: str = "https://integrate.api.nvidia.com/v1"
    ollama_base_url: str = "http://localhost:11434/v1"

    openrouter_site_url: str = "https://github.com/"
    openrouter_app_title: str = "LLM-EvalHub"

    # --- Evaluation defaults --------------------------------------------
    default_evaluator_provider: str | None = None
    default_evaluator_model: str | None = None
    enable_llm_judge: bool = True
    enable_ragas: bool = False
    enable_mock_provider: bool = True

    max_concurrent_requests: int = 3
    request_timeout_seconds: int = 60
    retry_attempts: int = 2
    retry_backoff_seconds: float = 1.5
    max_dataset_rows: int = 2000
    max_upload_bytes: int = 10 * 1024 * 1024

    # --- Model Audit Settings -------------------------------------------
    model_audit_ttl_hours: int = 6
    max_probes_per_provider: int = 15
    max_probe_concurrency: int = 3
    probe_timeout_seconds: float = 10.0

    # --- RAG -------------------------------------------------------------
    embedding_backend: str = Field(default="hashing")  # hashing | gemini | sentence-transformers
    embedding_model: str = "text-embedding-004"
    embedding_dimension: int = 512
    vector_store_backend: str = Field(default="auto")  # auto | faiss | numpy
    default_chunk_size: int = 800
    default_chunk_overlap: int = 120
    default_top_k: int = 4
    storage_dir: Path = BACKEND_DIR / "storage"

    @field_validator("app_env")
    @classmethod
    def _normalise_env(cls, value: str) -> str:
        return value.strip().lower()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env in {"production", "prod"}

    @property
    def is_auth_enabled(self) -> bool:
        return self.auth_mode == "enabled"

    @property
    def effective_job_backend(self) -> str:
        if self.job_backend in {"asyncio", "arq"}:
            return self.job_backend
        return "arq" if self.redis_url else "asyncio"

    def model_post_init(self, __context: Any) -> None:
        if self.auth_mode == "enabled":
            insecure_defaults = {
                "dev-secret-change-me",
                "dev-insecure-secret-key-change-in-production",
                "",
            }
            if not self.secret_key or self.secret_key in insecure_defaults:
                raise ValueError(
                    "SECRET_KEY must be set to a secure secret in 'enabled' auth mode. "
                    "Refusing to start with missing or default secret."
                )

    @property
    def uploads_dir(self) -> Path:
        return self.storage_dir / "uploads"

    @property
    def index_dir(self) -> Path:
        return self.storage_dir / "indexes"

    def ensure_dirs(self) -> None:
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)

    def provider_key(self, provider: str) -> str | None:
        return {
            "gemini": self.gemini_api_key,
            "groq": self.groq_api_key,
            "huggingface": self.hf_api_key,
            "openrouter": self.openrouter_api_key,
            "nvidia_nim": self.nvidia_nim_api_key,
        }.get(provider)

    def provider_base_url(self, provider: str) -> str:
        return {
            "gemini": self.gemini_base_url,
            "groq": self.groq_base_url,
            "huggingface": self.hf_base_url,
            "openrouter": self.openrouter_base_url,
            "nvidia_nim": self.nvidia_nim_base_url,
            "ollama": self.ollama_base_url,
        }.get(provider, "")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings


settings = get_settings()
