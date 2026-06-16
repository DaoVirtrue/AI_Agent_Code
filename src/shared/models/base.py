"""
SQLAlchemy 2.0 declarative base with common mixins.

Provides:
- ``Base`` – the declarative base for all ORM models.
- ``UUIDPrimaryKeyMixin`` – adds ``id`` (UUID), ``created_at``, ``updated_at``.
- ``TimestampMixin`` – adds ``created_at``, ``updated_at`` only (for association tables).
- Automatic ``__tablename__`` generation from class name.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


def _camel_to_snake(name: str) -> str:
    """Convert CamelCase to snake_case."""
    result: list[str] = []
    for i, ch in enumerate(name):
        if ch.isupper():
            if i > 0:
                result.append("_")
            result.append(ch.lower())
        else:
            result.append(ch)
    return "".join(result).strip("_")


class Base(DeclarativeBase):
    """Declarative base for all ORM models.

    ``__tablename__`` is auto-generated from the class name in snake_case.
    Override ``__tablename_plural__`` on subclasses to add an 's' suffix for
    models where the singular form would be confusing (e.g. class ``Address``
    -> table ``address`` is fine, but class ``Status`` -> table ``status``
    may conflict with reserved words – override to ``statuses``).
    """

    __abstract__ = True
    __tablename_plural__: bool = False

    @declared_attr.directive
    def __tablename__(cls) -> str:  # noqa: N805
        name = _camel_to_snake(cls.__name__)
        if getattr(cls, "__tablename_plural__", False):
            name = f"{name}s"
        return name

    def __repr__(self) -> str:
        cols = ", ".join(
            f"{c.name}={getattr(self, c.name)!r}"
            for c in self.__table__.columns
        )
        return f"<{self.__class__.__name__}({cols})>"


# ---------------------------------------------------------------------------
# Mixins
# ---------------------------------------------------------------------------


class TimestampMixin:
    """Adds ``created_at`` and ``updated_at`` timestamp columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        doc="UTC timestamp of row creation",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        doc="UTC timestamp of last update",
    )


class UUIDPrimaryKeyMixin(TimestampMixin):
    """UUID v4 primary key plus created/updated timestamps."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        doc="UUID v4 primary key",
    )
