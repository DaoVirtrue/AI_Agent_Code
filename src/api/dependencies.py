"""FastAPI dependency injection functions for database, Redis, gateway, and auth."""

from typing import Optional, Callable

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from redis.asyncio import Redis

from src.observability.logging_setup import get_logger

logger = get_logger(__name__)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class TenantContext:
    """Holds the current tenant information extracted from the request."""

    def __init__(
        self,
        tenant_id: str,
        user_id: str = "anonymous",
        role: str = "viewer",
        scopes: Optional[list[str]] = None,
    ):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.role = role
        self.scopes = scopes or []

    def __repr__(self) -> str:
        return (
            f"TenantContext(tenant_id={self.tenant_id!r}, "
            f"user_id={self.user_id!r}, role={self.role!r})"
        )


async def get_db(request: Request) -> AsyncSession:
    """Get an async database session from the connection pool.

    Yields an AsyncSession that is automatically closed after the request.
    """
    session_factory: async_sessionmaker = request.app.state.db_session_factory
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_redis(request: Request) -> Redis:
    """Get the Redis client from application state.

    Returns the shared Redis client instance.

    Raises:
        HTTPException: 503 if Redis was not initialized (e.g. unavailable
            at startup), instead of failing with a bare AttributeError.
    """
    redis_client = getattr(request.app.state, "redis", None)
    if redis_client is None:
        raise HTTPException(
            status_code=503,
            detail="Redis service not initialized",
        )
    return redis_client


async def get_gateway(request: Request):
    """Get the GatewayRouter singleton from application state.

    Returns:
        GatewayRouter instance used for routing LLM requests.
    """
    gateway = getattr(request.app.state, "gateway", None)
    if gateway is None:
        raise HTTPException(
            status_code=503,
            detail="Gateway service not initialized",
        )
    return gateway


async def get_rag_pipeline(request: Request):
    """Get the RAGPipeline singleton from application state.

    Returns:
        RAGPipeline instance for retrieval-augmented generation.
    """
    pipeline = getattr(request.app.state, "rag_pipeline", None)
    if pipeline is None:
        raise HTTPException(
            status_code=503,
            detail="RAG pipeline not initialized",
        )
    return pipeline


async def get_token_counter(request: Request):
    """Get the TokenCounter singleton from application state.

    Returns:
        TokenCounter instance for estimating token usage.
    """
    counter = getattr(request.app.state, "token_counter", None)
    if counter is None:
        raise HTTPException(
            status_code=503,
            detail="Token counter not initialized",
        )
    return counter


async def _resolve_tenant_from_api_key(
    request: Request,
    api_key: Optional[str],
    redis: Redis,
) -> TenantContext:
    """Resolve tenant context from an API key.

    Checks Redis cache first, then falls back to database lookup.
    """
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-API-Key header. API key is required for authentication.",
        )

    # Check Redis cache for API key -> tenant mapping
    cache_key = f"apikey:{api_key}"
    cached_data = await redis.hgetall(cache_key)

    if cached_data:
        return TenantContext(
            tenant_id=cached_data.get("tenant_id", "unknown"),
            user_id=cached_data.get("user_id", "anonymous"),
            role=cached_data.get("role", "viewer"),
            scopes=cached_data.get("scopes", "").split(",") if cached_data.get("scopes") else [],
        )

    # Fallback: database lookup (SHA-256 key hash)
    session_factory: async_sessionmaker = request.app.state.db_session_factory
    async with session_factory() as session:
        from src.repositories.models.api_key import APIKey
        from src.repositories.models.tenant import Tenant
        from src.security.auth import hash_api_key

        key_hash = hash_api_key(api_key)
        result = await session.execute(
            select(APIKey, Tenant)
            .join(Tenant, Tenant.id == APIKey.tenant_id)
            .where(APIKey.key_hash == key_hash, APIKey.is_active.is_(True), Tenant.is_active.is_(True))
            .limit(1)
        )
        row = result.one_or_none()

        if not row:
            raise HTTPException(
                status_code=403,
                detail="Invalid or inactive API key",
            )

        api_key_row, tenant_row = row
        scopes = list(api_key_row.scopes or [])

        tenant = TenantContext(
            tenant_id=str(tenant_row.id),
            user_id=str(api_key_row.user_id) if api_key_row.user_id else "anonymous",
            role="admin",  # MVP: seed key is admin (no per-key role field on the model)
            scopes=scopes,
        )

        # Cache for 5 minutes
        await redis.hset(
            cache_key,
            mapping={
                "tenant_id": tenant.tenant_id,
                "user_id": tenant.user_id,
                "role": tenant.role,
                "scopes": ",".join(tenant.scopes),
            },
        )
        await redis.expire(cache_key, 300)

        return tenant


async def get_current_tenant(
    request: Request,
    api_key: Optional[str] = Security(_api_key_header),
    redis: Redis = Depends(get_redis),
) -> TenantContext:
    """Dependency that authenticates the request and returns tenant context.

    Extracts the API key from X-API-Key header and resolves the tenant.
    """
    # Allow health endpoints to bypass auth
    if request.url.path in ("/health", "/ready", "/live", "/metrics"):
        return TenantContext(tenant_id="system", user_id="system", role="admin")

    return await _resolve_tenant_from_api_key(request, api_key, redis)


def require_scope(*scopes: str) -> Callable:
    """Factory that creates a dependency requiring specific permission scopes.

    Usage:
        @router.post("/admin/tenants")
        async def create_tenant(
            _: None = Depends(require_scope("admin:write")),
            tenant: TenantContext = Depends(get_current_tenant),
        ):
            ...

    Args:
        *scopes: Required scope strings (e.g., "admin:write", "rag:read").

    Returns:
        A FastAPI dependency callable that checks the tenant's scopes.
    """
    required_scopes = set(scopes)

    async def scope_checker(tenant: TenantContext = Depends(get_current_tenant)):
        if not required_scopes:
            return None

        # Admin role has all scopes
        if tenant.role == "admin":
            return None

        tenant_scopes = set(tenant.scopes)
        missing = required_scopes - tenant_scopes

        if missing:
            logger.warning(
                "Insufficient scopes",
                tenant_id=tenant.tenant_id,
                role=tenant.role,
                required=list(required_scopes),
                missing=list(missing),
            )
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions. Missing scopes: {list(missing)}",
            )

        return None

    return scope_checker
