"""API Layer - FastAPI application with dependency injection, middleware, and route registration."""

from src.api.app import create_app
from src.api.dependencies import (
    get_db,
    get_redis,
    get_gateway,
    get_rag_pipeline,
    get_token_counter,
    get_current_tenant,
    require_scope,
)

__all__ = [
    "create_app",
    "get_db",
    "get_redis",
    "get_gateway",
    "get_rag_pipeline",
    "get_token_counter",
    "get_current_tenant",
    "require_scope",
]
