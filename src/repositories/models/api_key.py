"""
API Key model – JWT-free authentication for programmatic access.

Keys are hashed (SHA-256) before storage.  The *key_prefix* (first 8 plaintext
characters) is stored to help users identify keys in the UI.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from .tenant import Tenant
    from .user import User


class APIKey(UUIDPrimaryKeyMixin, Base):
    """Hashed API key for tenant or user-level authentication."""

    __tablename__ = "api_keys"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Owning tenant",
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Optional user that owns this key",
    )
    key_hash: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True, doc="SHA-256 hash of the plaintext key"
    )
    key_prefix: Mapped[str] = mapped_column(
        String(16), nullable=False, doc="First 8 chars of the plaintext key (for identification)"
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, doc="Human-readable label for this key"
    )
    scopes: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        doc="List of permission scopes, e.g. ['read:models', 'write:conversations']",
    )
    rate_limit_rpm: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, doc="Per-key rate limit in requests per minute"
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, doc="Expiry date; NULL = never expires"
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, doc="Timestamp of last use"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # -- Relationships -------------------------------------------------------
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="api_keys")
    user: Mapped[Optional["User"]] = relationship("User")

    def __repr__(self) -> str:
        return f"<APIKey(id={self.id}, prefix={self.key_prefix!r}, name={self.name!r})>"
