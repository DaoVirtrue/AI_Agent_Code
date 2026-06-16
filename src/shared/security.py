"""
Security utilities – API key hashing/verification/generation and auth dependencies.

API keys are generated as ``{prefix}_`` + random hex, hashed with SHA-256 for
storage.  The plaintext key is returned once at creation time and never stored.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from contextvars import ContextVar
from typing import Optional

from fastapi import Depends, Header, Request
from sqlalchemy import select

from .config import get_settings
from .database import get_db
from .exceptions import AuthenticationError, AuthorizationError


# ---------------------------------------------------------------------------
# Key hashing
# ---------------------------------------------------------------------------


def hash_api_key(key: str) -> str:
    """SHA-256 hex digest of the API key (salted with secret key)."""
    settings = get_settings()
    secret = settings.secret_key.get_secret_value()
    return hashlib.sha256(f"{key}:{secret}".encode("utf-8")).hexdigest()


def verify_api_key(key: str, stored_hash: str) -> bool:
    """Constant-time comparison of a plaintext key against its stored hash."""
    computed = hash_api_key(key)
    return hmac.compare_digest(computed, stored_hash)


def generate_api_key(prefix: str = "llm") -> tuple[str, str]:
    """Generate a new API key pair.

    Returns:
        (raw_key, hashed_key)

    Example:
        >>> raw, hashed = generate_api_key()
        >>> raw
        'llm_a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0'
        >>> len(hashed)  # SHA-256 hex
        64
    """
    raw_bytes = secrets.token_bytes(40)
    raw = f"{prefix}_{raw_bytes.hex()}"
    hashed = hash_api_key(raw)
    return raw, hashed


# ---------------------------------------------------------------------------
# Tenant context (request-scoped)
# ---------------------------------------------------------------------------

TenantContext: ContextVar[Optional["TenantContextData"]] = ContextVar(
    "tenant_context", default=None
)


class TenantContextData:
    """Lightweight tenant info attached to the request via ContextVar."""

    __slots__ = ("tenant_id", "tenant_slug", "tier", "scopes")

    def __init__(
        self,
        tenant_id: str,
        tenant_slug: str,
        tier: str,
        scopes: list[str],
    ) -> None:
        self.tenant_id = tenant_id
        self.tenant_slug = tenant_slug
        self.tier = tier
        self.scopes = scopes


# ---------------------------------------------------------------------------
# FastAPI auth dependency
# ---------------------------------------------------------------------------


async def get_current_tenant(
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key", description="API key for authentication"),
) -> TenantContextData:
    """FastAPI dependency that validates X-API-Key and sets TenantContext.

    Looks up the hashed key in the database, checks expiry and active status,
    and sets the ``TenantContext`` ContextVar for downstream use.

    Usage::

        @router.get("/protected")
        async def protected_endpoint(tenant: TenantContextData = Depends(get_current_tenant)):
            ...
    """
    from sqlalchemy.ext.asyncio import AsyncSession

    settings = get_settings()

    if not x_api_key or not x_api_key.strip():
        raise AuthenticationError("X-API-Key header is required")

    x_api_key = x_api_key.strip()
    key_hash = hash_api_key(x_api_key)

    # We need a DB session.  get_db is a FastAPI dependency itself, but we
    # are already in a dependency – so we look up the session via request state.
    # Fallback: create a session directly (not ideal, but functional).
    db: AsyncSession
    try:
        db_gen = get_db()
        db = await anext(db_gen)  # type: ignore[arg-type]
    except (StopAsyncIteration, TypeError, RuntimeError):
        # If get_db cannot be resolved as a dependency, create a raw session.
        from .database import get_session_factory

        factory = get_session_factory()
        db = factory()
        _owned = True
    else:
        _owned = True

    try:
        from .models.api_key import APIKey
        from .models.tenant import Tenant

        result = await db.execute(
            select(APIKey, Tenant)
            .join(Tenant, Tenant.id == APIKey.tenant_id)
            .where(APIKey.key_hash == key_hash, APIKey.is_active.is_(True))
            .limit(1)
        )
        row = result.one_or_none()

        if row is None:
            raise AuthenticationError("Invalid API key")

        api_key: APIKey = row[0]
        tenant: Tenant = row[1]

        # Check tenant active
        if not tenant.is_active:
            raise AuthenticationError("Tenant account is deactivated")

        # Check key expiry
        if api_key.expires_at is not None:
            from datetime import datetime, timezone

            if api_key.expires_at < datetime.now(timezone.utc):
                raise AuthenticationError("API key has expired")

        # Build context
        ctx = TenantContextData(
            tenant_id=str(tenant.id),
            tenant_slug=tenant.slug,
            tier=tenant.tier,
            scopes=list(api_key.scopes or []),
        )
        TenantContext.set(ctx)

        # Update last_used_at
        from datetime import datetime, timezone

        api_key.last_used_at = datetime.now(timezone.utc)
        await db.commit()

        return ctx

    finally:
        if _owned:
            await db.close()


# ---------------------------------------------------------------------------
# Scope-checking dependency factory
# ---------------------------------------------------------------------------


def require_scopes(*required_scopes: str):
    """Dependency factory: require one or more scopes on the current tenant.

    Usage::

        @router.get("/admin")
        async def admin_endpoint(
            tenant: TenantContextData = Depends(get_current_tenant),
            _: None = Depends(require_scopes("admin", "write:all")),
        ):
            ...
    """
    async def _checker(
        tenant: TenantContextData = Depends(get_current_tenant),
    ) -> None:
        if not required_scopes:
            return

        tenant_scopes = set(tenant.scopes or [])
        # Wildcard admin scope bypasses all checks
        if "admin" in tenant_scopes or "*" in tenant_scopes:
            return

        missing = [s for s in required_scopes if s not in tenant_scopes]
        if missing:
            raise AuthorizationError(
                f"Missing required scopes: {', '.join(missing)}"
            )

    return _checker


# ---------------------------------------------------------------------------
# Convenience: extract tenant from context
# ---------------------------------------------------------------------------


def get_tenant_context() -> TenantContextData:
    """Read the current tenant from the ContextVar.  Raises if not set."""
    ctx = TenantContext.get()
    if ctx is None:
        raise RuntimeError("TenantContext is not set – ensure get_current_tenant dependency is used.")
    return ctx
