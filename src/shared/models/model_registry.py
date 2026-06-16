"""
Model Registry – centrally tracks which LLM models are available.

Each row describes a specific model from a specific provider, including
its capabilities, pricing, and routing metadata.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UUIDPrimaryKeyMixin


class ModelRegistry(UUIDPrimaryKeyMixin, Base):
    """A registered LLM model available for use by the platform."""

    __tablename__ = "model_registry"

    # --- Identity -----------------------------------------------------------
    model_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True,
        doc="Unique model identifier, e.g. 'openai/gpt-4o'",
    )
    provider: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True,
        doc="Provider name: openai, anthropic, azure, bedrock, vertex, etc.",
    )
    display_name: Mapped[str] = mapped_column(
        String(255), nullable=False,
        doc="Human-friendly name shown in the UI",
    )

    # --- Capabilities -------------------------------------------------------
    context_window: Mapped[int] = mapped_column(
        Integer, nullable=False,
        doc="Max context window in tokens",
    )
    max_output_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False,
        doc="Max tokens the model can generate in one response",
    )
    supports_vision: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
        doc="Whether the model accepts image inputs",
    )
    supports_tools: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
        doc="Whether the model supports tool/function calling",
    )
    supports_streaming: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        doc="Whether the model supports streaming responses",
    )

    # --- Pricing (per million tokens) ---------------------------------------
    input_price_per_1m: Mapped[Decimal] = mapped_column(
        Float, nullable=False, default=0.0,
        doc="USD per 1M input tokens",
    )
    output_price_per_1m: Mapped[Decimal] = mapped_column(
        Float, nullable=False, default=0.0,
        doc="USD per 1M output tokens",
    )
    cached_input_price_per_1m: Mapped[Decimal] = mapped_column(
        Float, nullable=False, default=0.0,
        doc="USD per 1M cached/anthropic-prompt-cache input tokens",
    )

    # --- Routing ------------------------------------------------------------
    endpoint_url: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        doc="Override URL for the provider endpoint (e.g. proxy or private deployment)",
    )
    api_version: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        doc="Provider API version to use, if applicable",
    )
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        doc="Priority for fallback ordering (higher = preferred)",
    )
    is_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        doc="Whether this model is currently enabled for routing",
    )

    # --- Extras -------------------------------------------------------------
    metadata_info: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        doc="Arbitrary provider-specific metadata (rate limits, regions, etc.)",
    )

    def __repr__(self) -> str:
        return f"<ModelRegistry(model_id={self.model_id!r}, provider={self.provider!r})>"
