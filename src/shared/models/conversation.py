"""
Conversation & Message models – tracks chat sessions and their messages.

A Conversation belongs to a tenant and optionally a user.  Each Message
records the LLM interaction including tool calls.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from .tenant import Tenant
    from .user import User


class Conversation(UUIDPrimaryKeyMixin, Base):
    """A conversation / chat session."""

    __tablename__ = "conversations"

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
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(500), nullable=False, default="New Conversation",
        doc="Conversation title (auto-generated or user-set)"
    )
    model_used: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        doc="Primary model used, e.g. 'anthropic/claude-sonnet-4-20250514'"
    )
    message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, doc="Cached count of messages"
    )
    total_input_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, doc="Sum of all input tokens"
    )
    total_output_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, doc="Sum of all output tokens"
    )
    total_cost_usd: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, doc="Total estimated cost in USD"
    )

    # -- Relationships -------------------------------------------------------
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="conversations")
    user: Mapped["User | None"] = relationship("User", back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, title={self.title!r}, messages={self.message_count})>"


class Message(Base):
    """A single message within a conversation."""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        doc="Message role: system, user, assistant, tool",
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, default="",
        doc="Message content (plain text or markdown)"
    )
    tool_calls: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB,
        nullable=True,
        doc="Serialised tool-call blocks for assistant messages",
    )
    tool_call_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        doc="Tool-call ID for tool-role messages"
    )
    token_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        doc="Estimated token count for this message"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.now,
        doc="When this message was created",
    )

    # -- Relationships -------------------------------------------------------
    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="messages"
    )

    def __repr__(self) -> str:
        content_preview = (self.content or "")[:60]
        return f"<Message(id={self.id}, role={self.role!r}, content={content_preview!r}...)>"
