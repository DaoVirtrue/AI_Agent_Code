"""
Document model – tracks uploaded files through the ingestion pipeline.

Status lifecycle: pending -> processing -> indexed  (success path)
Status lifecycle: pending -> processing -> failed   (error path)
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from .tenant import Tenant


class Document(UUIDPrimaryKeyMixin, Base):
    """A document uploaded for RAG ingestion."""

    __tablename__ = "documents"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    collection_name: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True,
        doc="Milvus collection this document belongs to",
    )
    filename: Mapped[str] = mapped_column(
        String(500), nullable=False, doc="Original filename"
    )
    file_type: Mapped[str] = mapped_column(
        String(50), nullable=False, doc="MIME type or extension: pdf, txt, md, csv, etc."
    )
    file_size_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, doc="File size in bytes"
    )
    file_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True,
        doc="SHA-256 hash of the file content for deduplication",
    )
    storage_path: Mapped[str] = mapped_column(
        String(1000), nullable=False, doc="Path to the file in object storage (S3/MinIO)"
    )
    chunk_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, doc="Number of chunks indexed in Milvus"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
        doc="Ingestion status: pending, processing, indexed, or failed",
    )
    metadata_info: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        doc="Arbitrary metadata: page count, author, tags, custom fields",
    )

    # -- Relationships -------------------------------------------------------
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="documents")

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, filename={self.filename!r}, status={self.status!r})>"
