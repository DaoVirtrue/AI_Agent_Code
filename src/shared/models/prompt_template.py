"""
Prompt Template model with versioned content.

Each PromptTemplate can have multiple PromptTemplateVersion rows, each storing
the full content, variable schema, and change description for that version.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from .tenant import Tenant
    from .user import User


class PromptTemplate(UUIDPrimaryKeyMixin, Base):
    """A named prompt template owned by a tenant."""

    __tablename__ = "prompt_templates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_prompt_templates_tenant_name"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, doc="Template name (unique per tenant)"
    )
    current_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, doc="Latest version number"
    )
    category: Mapped[str] = mapped_column(
        String(100), nullable=False, default="general",
        doc="Category for grouping: general, chat, extraction, code, etc."
    )
    description: Mapped[str] = mapped_column(
        Text, nullable=False, default="", doc="Human-readable description"
    )

    # -- Relationships -------------------------------------------------------
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="prompt_templates")
    versions: Mapped[list["PromptTemplateVersion"]] = relationship(
        "PromptTemplateVersion",
        back_populates="template",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="PromptTemplateVersion.version",
    )

    def __repr__(self) -> str:
        return f"<PromptTemplate(id={self.id}, name={self.name!r}, v{self.current_version})>"


class PromptTemplateVersion(Base):
    """A specific version of a prompt template's content."""

    __tablename__ = "prompt_template_versions"
    __table_args__ = (
        UniqueConstraint("template_id", "version", name="uq_prompt_versions_template_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompt_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, doc="Version number (1-based)"
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, doc="Full prompt template with {variable} placeholders"
    )
    variables_schema: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        doc="JSON Schema describing expected variables, e.g. {name: {type: string}}",
    )
    change_description: Mapped[str] = mapped_column(
        String(500), nullable=False, default="", doc="What changed in this version"
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        doc="User who created this version",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.now, doc="Creation timestamp"
    )

    # -- Relationships -------------------------------------------------------
    template: Mapped["PromptTemplate"] = relationship(
        "PromptTemplate", back_populates="versions"
    )
    author: Mapped["User | None"] = relationship("User")

    def __repr__(self) -> str:
        return f"<PromptTemplateVersion(template_id={self.template_id}, v{self.version})>"
