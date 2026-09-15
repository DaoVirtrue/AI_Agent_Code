"""
Application configuration loaded from YAML files and environment variables.

Config loading strategy:
1. Load default.yaml as baseline
2. Merge {env}.yaml on top (development.yaml, production.yaml, etc.)
3. Environment variables take highest precedence (via pydantic-settings)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal, Optional

import yaml
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *override* into *base*. Returns a new dict."""
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file; return empty dict if file does not exist."""
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data or {}


def _flatten_dict(
    d: dict[str, Any], parent_key: str = "", sep: str = "__"
) -> dict[str, str]:
    """Flatten nested dict into dotted keys, converting all values to strings."""
    items: list[tuple[str, str]] = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key.upper(), str(v)))
    return dict(items)


# ---------------------------------------------------------------------------
# Nested settings models
# ---------------------------------------------------------------------------


class DatabaseSettings(BaseSettings):
    """Relational database (PostgreSQL-compatible) settings."""

    url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/llm_platform",
        description="Async database connection URL",
    )
    pool_size: int = Field(default=20, ge=1, description="Connection pool size")
    max_overflow: int = Field(
        default=10, ge=0, description="Max overflow connections beyond pool_size"
    )
    echo: bool = Field(default=False, description="Log all SQL statements (debug)")
    pool_pre_ping: bool = Field(
        default=True, description="Verify connections before use"
    )
    pool_recycle: int = Field(
        default=3600, description="Recycle connections after N seconds"
    )


class RedisSettings(BaseSettings):
    """Redis connection settings."""

    url: str = Field(
        default="redis://localhost:6379/0", description="Redis connection URL"
    )
    max_connections: int = Field(
        default=50, ge=1, description="Max connections in the pool"
    )
    socket_timeout: float = Field(
        default=5.0, description="Socket timeout in seconds"
    )
    decode_responses: bool = Field(
        default=True, description="Automatically decode bytes to str"
    )


class RabbitMQSettings(BaseSettings):
    """RabbitMQ / AMQP broker settings (used by Celery)."""

    url: str = Field(
        default="amqp://guest:guest@localhost:5672//",
        description="RabbitMQ broker URL",
    )
    heartbeat: int = Field(default=60, description="Broker heartbeat interval")
    connection_attempts: int = Field(default=5, description="Max connection retries")


class MilvusSettings(BaseSettings):
    """Milvus vector database settings."""

    host: str = Field(default="localhost", description="Milvus host")
    port: int = Field(default=19530, description="Milvus gRPC port")
    user: str = Field(default="", description="Milvus username")
    password: SecretStr = Field(
        default=SecretStr(""), description="Milvus password"
    )
    collection_prefix: str = Field(
        default="llm_", description="Prefix for collection names"
    )
    dimension: int = Field(
        default=1536, description="Default embedding dimension"
    )
    index_type: str = Field(
        default="IVF_FLAT", description="Default Milvus index type"
    )
    metric_type: str = Field(default="COSINE", description="Similarity metric")
    consistency_level: str = Field(
        default="Bounded", description="Milvus consistency level"
    )


class GatewaySettings(BaseSettings):
    """LLM Gateway settings – routing, circuit breaker, fallback, retry."""

    default_timeout: float = Field(
        default=60.0, description="Default request timeout seconds"
    )
    max_retries: int = Field(default=3, description="Max retry attempts")
    retry_backoff_factor: float = Field(
        default=0.5, description="Exponential backoff multiplier"
    )
    circuit_breaker_failure_threshold: int = Field(
        default=5, description="Failures before opening circuit"
    )
    circuit_breaker_recovery_timeout: float = Field(
        default=30.0, description="Seconds before half-open attempt"
    )
    rate_limit_burst_size: int = Field(default=100, description="Token bucket burst")
    rate_limit_refill_rate: float = Field(
        default=10.0, description="Tokens per second refill"
    )
    fallback_enabled: bool = Field(default=True, description="Enable fallback chain")
    fallback_providers: list[str] = Field(
        default_factory=lambda: ["openai", "azure", "anthropic"],
        description="Ordered fallback provider list",
    )


class RAGSettings(BaseSettings):
    """RAG (Retrieval-Augmented Generation) settings."""

    chunk_size: int = Field(default=1000, description="Default chunk size in chars")
    chunk_overlap: int = Field(default=200, description="Chunk overlap in chars")
    top_k: int = Field(default=5, description="Default number of retrieved chunks")
    similarity_threshold: float = Field(
        default=0.7, description="Minimum similarity score"
    )
    embedding_model: str = Field(
        default="text-embedding-3-small", description="Embedding model name"
    )
    embedding_provider: str = Field(
        default="openai", description="Embedding provider"
    )
    reranker_enabled: bool = Field(
        default=True, description="Enable cross-encoder reranking"
    )
    reranker_model: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        description="Reranker model name",
    )
    max_retrieval_size: int = Field(
        default=25, description="Max docs to retrieve before reranking"
    )
    hybrid_search_alpha: float = Field(
        default=0.5, description="Weight between dense (alpha) and sparse (1-alpha)"
    )
    default_collection_name: str = Field(
        default="default", description="Default Milvus collection"
    )


class AgentSettings(BaseSettings):
    """Autonomous agent execution settings."""

    max_steps: int = Field(default=50, description="Max agent loop iterations")
    loop_detection_window: int = Field(
        default=5, description="Recent messages to check for loops"
    )
    loop_detection_threshold: float = Field(
        default=0.95, description="Similarity threshold for loop detection"
    )
    tool_execution_timeout: float = Field(
        default=30.0, description="Max seconds per tool call"
    )
    agent_execution_timeout: float = Field(
        default=600.0, description="Max seconds for entire agent run"
    )
    max_tool_calls_per_turn: int = Field(
        default=10, description="Max tool calls per message"
    )
    default_model: str = Field(
        default="claude-sonnet-4-20250514", description="Default agent model"
    )
    thought_budget_tokens: int = Field(
        default=16000, description="Max thinking tokens per step"
    )
    sandbox_enabled: bool = Field(
        default=True, description="Execute tools in sandbox"
    )
    sandbox_image: str = Field(
        default="llm-platform/sandbox:latest", description="Sandbox Docker image"
    )


class MonitoringSettings(BaseSettings):
    """Observability and monitoring settings."""

    log_level: str = Field(default="INFO", description="Application log level")
    log_format: Literal["json", "text"] = Field(
        default="json", description="Log output format"
    )
    metrics_enabled: bool = Field(default=True, description="Enable Prometheus metrics")
    metrics_port: int = Field(default=9090, description="Metrics server port")
    tracing_enabled: bool = Field(default=True, description="Enable distributed tracing")
    tracing_exporter: str = Field(
        default="otlp", description="Tracing exporter type"
    )
    tracing_endpoint: str = Field(
        default="http://localhost:4317", description="OTLP collector endpoint"
    )
    sentry_dsn: Optional[str] = Field(default=None, description="Sentry DSN")
    health_check_path: str = Field(
        default="/health", description="Health check endpoint path"
    )
    request_log_retention_days: int = Field(
        default=90, description="Days to retain request logs"
    )


# ---------------------------------------------------------------------------
# Top-level settings
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """Root settings aggregating all nested configuration groups."""

    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Core identity ---
    app_name: str = Field(default="llm-platform", description="Application name")
    app_version: str = Field(default="1.0.0", description="Application version")
    environment: Literal["development", "staging", "production"] = Field(
        default="development", description="Deployment environment"
    )
    debug: bool = Field(default=False, description="Debug mode")
    secret_key: SecretStr = Field(
        default=SecretStr("change-me-in-production"),
        description="Secret key for signing",
    )

    # --- Server ---
    host: str = Field(default="0.0.0.0", description="Server bind address")
    port: int = Field(default=8000, description="Server port")
    workers: int = Field(default=4, description="Uvicorn worker count")

    # --- Nested settings groups ---
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    rabbitmq: RabbitMQSettings = Field(default_factory=RabbitMQSettings)
    milvus: MilvusSettings = Field(default_factory=MilvusSettings)
    gateway: GatewaySettings = Field(default_factory=GatewaySettings)
    rag: RAGSettings = Field(default_factory=RAGSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)

    @classmethod
    def from_yaml_files(cls, env: str = "development") -> "Settings":
        """Factory: load default.yaml, merge {env}.yaml, then apply env vars."""
        config_dir = Path(os.getenv("CONFIG_DIR", str(Path(__file__).resolve().parent.parent.parent / "config")))

        default_data = _load_yaml(config_dir / "default.yaml")
        env_data = _load_yaml(config_dir / f"{env}.yaml")
        merged = _deep_merge(default_data, env_data)

        # Flatten YAML values to env-var-style keys so pydantic-settings can pick them up
        flat = _flatten_dict(merged)
        for k, v in flat.items():
            if k not in os.environ:
                os.environ[k] = v

        return cls()


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_settings: Optional[Settings] = None


def load_settings(env: str = "development") -> Settings:
    """Load (and cache) application settings for the given environment."""
    global _settings
    if _settings is None:
        _settings = Settings.from_yaml_files(env=env)
    return _settings


def get_settings() -> Settings:
    """Return the currently cached settings. Raises RuntimeError if not loaded."""
    if _settings is None:
        raise RuntimeError("Settings not loaded. Call load_settings() first.")
    return _settings
