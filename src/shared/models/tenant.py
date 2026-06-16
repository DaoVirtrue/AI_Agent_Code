"""
Tenant model – the top-level organisational unit.

Each tenant represents a customer/organisation with its own users, API keys,
documents, conversations, and quota tracking.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Boolean, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from .api_key import APIKey
    from .conversation import Conversation
    from .document import Document
    from .prompt_template import PromptTemplate
    from .request_log import RequestLog
    from .user import User


class Tenant(UUIDPrimaryKeyMixin, Base):
    """An organisation using the LLM platform."""

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(
        String(255), nullable=False, doc="Display name of the tenant"
    )
    slug: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True, doc="URL-safe unique identifier"
    )
    tier: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="free",
        server_default="free",
        doc="Subscription tier: free, pro, or enterprise",
    )
    api_key_hash: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, doc="Hashed root API key for this tenant"
    )
    quotas: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        doc="JSONB blob for quota limits: tokens/mo, requests/mo, storage_gb, docs, users",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true", doc="Soft-delete flag"
    )

    # -- Relationships -------------------------------------------------------
    users: Mapped[list["User"]] = relationship(
        "User", back_populates="tenant", lazy="selectin", cascade="all, delete-orphan"
    )
    api_keys: Mapped[list["APIKey"]] = relationship(
        "APIKey", back_populates="tenant", lazy="selectin", cascade="all, delete-orphan"
    )
    prompt_templates: Mapped[list["PromptTemplate"]] = relationship(
        "PromptTemplate", back_populates="tenant", lazy="selectin", cascade="all, delete-orphan"
    )
    documents: Mapped[list["Document"]] = relationship(
        "Document", back_populates="tenant", lazy="selectin", cascade="all, delete-orphan"
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation", back_populates="tenant", lazy="selectin", cascade="all, delete-orphan"
    )
    request_logs: Mapped[list["RequestLog"]] = relationship(
        "RequestLog", back_populates="tenant", lazy="selectin", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, slug={self.slug!r}, tier={self.tier!r})>"
