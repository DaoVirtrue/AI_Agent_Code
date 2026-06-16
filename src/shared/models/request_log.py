"""
Request Log model – immutable audit trail for every LLM request.

Uses ULID string for ``request_id`` (lexicographically sortable by time).
Includes composite index on (tenant_id, created_at DESC) for dashboard queries.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .tenant import Tenant
    from .user import User


class RequestLog(Base):
    """Immutable log of each LLM API request for billing, monitoring, and audit."""

    __tablename__ = "request_logs"
    __table_args__ = (
        Index("ix_request_logs_tenant_created", "tenant_id", "created_at".desc()),
        Index("ix_request_logs_request_id", "request_id"),
        Index("ix_request_logs_parent_request_id", "parent_request_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    request_id: Mapped[str] = mapped_column(
        String(26), nullable=False,
        doc="ULID string – globally unique, time-sortable request identifier",
    )
    parent_request_id: Mapped[str | None] = mapped_column(
        String(26), nullable=True,
        doc="ULID of the parent request for tracing nested calls",
    )
    operation: Mapped[str] = mapped_column(
        String(100), nullable=False,
        doc="High-level operation: chat.completion, embedding, rerank, etc.",
    )
    provider: Mapped[str] = mapped_column(
        String(100), nullable=False,
        doc="LLM provider: openai, anthropic, azure, bedrock, etc.",
    )
    model: Mapped[str] = mapped_column(
        String(255), nullable=False,
        doc="Model identifier, e.g. 'openai/gpt-4o'",
    )
    input_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        doc="Prompt / input tokens consumed",
    )
    output_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        doc="Completion / output tokens consumed",
    )
    latency_ms: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
        doc="End-to-end latency in milliseconds",
    )
    cost_usd: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
        doc="Estimated cost in USD",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False,
        doc="Request status: success, error, fallback, or rate_limited",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        doc="Error details when status is 'error'",
    )
    metadata_info: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        doc="Arbitrary metadata: headers, retry count, circuit state, etc.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.now,
        doc="UTC timestamp of the request",
    )

    # -- Relationships -------------------------------------------------------
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="request_logs")
    user: Mapped["User | None"] = relationship("User", back_populates="request_logs")

    def __repr__(self) -> str:
        return (
            f"<RequestLog(request_id={self.request_id!r}, operation={self.operation!r}, "
            f"status={self.status!r}, latency={self.latency_ms}ms)>"
        )
