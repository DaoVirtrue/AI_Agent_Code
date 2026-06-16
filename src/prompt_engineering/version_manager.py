"""
Git-like version management for prompts backed by SQLAlchemy async sessions.

Supports create, update, rollback, version history, and unified diff.
Uses SHA-256 for content hashing to detect actual changes before creating
a new version.
"""

from __future__ import annotations

import difflib
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.models.prompt_template import PromptTemplate, PromptTemplateVersion

logger = logging.getLogger(__name__)


class PromptVersionManager:
    """Git-like version management for prompts backed by SQLAlchemy.

    Supports create, update, rollback, version history, and unified diff.
    Uses SHA-256 for content hashing to detect actual changes.

    Usage::

        async with session_factory() as db:
            mgr = PromptVersionManager(db)
            template = await mgr.create(
                tenant_id=tenant_id,
                name="greeting",
                content="Hello {{ user_name }}!",
                variables_schema={"user_name": {"type": "string"}},
            )
            new_version = await mgr.update(
                template_id=template.id,
                content="Hi {{ user_name }}, welcome!",
                change_description="Changed greeting tone",
            )
    """

    def __init__(self, db_session: AsyncSession) -> None:
        """Initialize with an async SQLAlchemy session.

        Args:
            db_session: An active AsyncSession for database operations.
                The caller is responsible for session lifecycle (commit/rollback).
        """
        self.db: AsyncSession = db_session
        logger.debug("PromptVersionManager initialized")

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create(
        self,
        tenant_id: uuid.UUID,
        name: str,
        content: str,
        variables_schema: dict[str, Any],
        description: str = "",
        category: str = "general",
    ) -> PromptTemplate:
        """Create a new PromptTemplate with its first version.

        Checks for an existing template with the same tenant_id + name
        combination and raises ValueError if one already exists.

        Args:
            tenant_id: The tenant that owns this template.
            name: Unique template name within the tenant.
            content: The full prompt template content with variable placeholders.
            variables_schema: JSON Schema dict describing expected template variables.
            description: Human-readable description of this template.
            category: Category for grouping (general, chat, extraction, code, etc.).

        Returns:
            The newly created PromptTemplate with its first version.

        Raises:
            ValueError: If a template with the same tenant_id + name already exists.
        """
        # Guard: unique constraint check
        existing = await self.db.execute(
            select(PromptTemplate).where(
                PromptTemplate.tenant_id == tenant_id,
                PromptTemplate.name == name,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError(
                f"PromptTemplate with name {name!r} already exists for "
                f"tenant {tenant_id}"
            )

        # Create the template row
        template = PromptTemplate(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name=name,
            current_version=1,
            category=category,
            description=description,
        )
        self.db.add(template)

        # Create version 1
        content_hash = self._compute_hash(content)
        version = PromptTemplateVersion(
            id=uuid.uuid4(),
            template_id=template.id,
            version=1,
            content=content,
            variables_schema=variables_schema,
            change_description="Initial version",
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(version)

        await self.db.flush()
        logger.info(
            "Created PromptTemplate %r (id=%s) v1 for tenant %s, hash=%s",
            name,
            template.id,
            tenant_id,
            content_hash[:12],
        )

        return template

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update(
        self,
        template_id: uuid.UUID,
        content: str,
        change_description: str = "",
        variables_schema: Optional[dict[str, Any]] = None,
    ) -> PromptTemplateVersion:
        """Create a new version for an existing template.

        Computes a SHA-256 hash of the new content. If the hash matches
        the latest version's hash, returns the existing version without
        creating a duplicate (no-op). Otherwise increments the version
        number, creates a new PromptTemplateVersion row, and bumps
        ``current_version`` on the parent PromptTemplate.

        Args:
            template_id: The UUID of the template to update.
            content: The new full prompt template content.
            change_description: Human-readable description of what changed.
            variables_schema: Optional updated variables schema. If None,
                the schema from the latest version is reused.

        Returns:
            The newly created PromptTemplateVersion (or existing one if no change).

        Raises:
            ValueError: If the template is not found.
        """
        # Load the template
        template = await self.db.get(PromptTemplate, template_id)
        if template is None:
            raise ValueError(f"PromptTemplate with id {template_id} not found")

        # Load the latest version
        latest = await self._get_latest_version(template_id)
        if latest is None:
            raise ValueError(
                f"PromptTemplate {template_id} has no versions (corrupt state)"
            )

        # Compute hash and check for actual change
        new_hash = self._compute_hash(content)
        old_hash = self._compute_hash(latest.content)

        if new_hash == old_hash:
            logger.info(
                "No content change detected for template %s (hash=%s), "
                "returning existing version %d",
                template_id,
                new_hash[:12],
                latest.version,
            )
            return latest

        # Determine the schema to use
        schema = (
            variables_schema
            if variables_schema is not None
            else dict(latest.variables_schema)
        )

        new_version_number = template.current_version + 1

        # Create the new version
        new_version = PromptTemplateVersion(
            id=uuid.uuid4(),
            template_id=template_id,
            version=new_version_number,
            content=content,
            variables_schema=schema,
            change_description=change_description,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(new_version)

        # Bump current_version on the template
        template.current_version = new_version_number

        await self.db.flush()
        logger.info(
            "Created version %d for template %r (id=%s), hash=%s: %s",
            new_version_number,
            template.name,
            template_id,
            new_hash[:12],
            change_description or "(no description)",
        )

        return new_version

    # ------------------------------------------------------------------
    # Rollback
    # ------------------------------------------------------------------

    async def rollback(
        self, template_id: uuid.UUID, target_version: int
    ) -> PromptTemplateVersion:
        """Rollback to a specific version by creating a NEW version that copies
        the target version's content.

        This follows Git semantics: rollback is an explicit operation that
        creates a new version preserving the rollback in history.

        Args:
            template_id: The UUID of the template to rollback.
            target_version: The version number to restore.

        Returns:
            The newly created PromptTemplateVersion containing the target's content.

        Raises:
            ValueError: If the template or target version is not found.
        """
        template = await self.db.get(PromptTemplate, template_id)
        if template is None:
            raise ValueError(f"PromptTemplate with id {template_id} not found")

        target = await self.get_version(template_id, target_version)
        if target is None:
            raise ValueError(
                f"Version {target_version} not found for template {template_id}"
            )

        new_version_number = template.current_version + 1
        change_desc = (
            f"Rollback from v{template.current_version} to v{target_version}"
        )

        new_version = PromptTemplateVersion(
            id=uuid.uuid4(),
            template_id=template_id,
            version=new_version_number,
            content=target.content,
            variables_schema=dict(target.variables_schema),
            change_description=change_desc,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(new_version)

        template.current_version = new_version_number
        await self.db.flush()

        logger.info(
            "Rolled back template %r (id=%s) from v%d to v%d -> new v%d",
            template.name,
            template_id,
            template.current_version - 1,
            target_version,
            new_version_number,
        )

        return new_version

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    async def get_version(
        self, template_id: uuid.UUID, version: int
    ) -> PromptTemplateVersion:
        """Get a specific version of a template.

        Args:
            template_id: The UUID of the template.
            version: The version number to retrieve (1-based).

        Returns:
            The matching PromptTemplateVersion.

        Raises:
            ValueError: If the version is not found.
        """
        result = await self.db.execute(
            select(PromptTemplateVersion).where(
                PromptTemplateVersion.template_id == template_id,
                PromptTemplateVersion.version == version,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise ValueError(
                f"Version {version} not found for template {template_id}"
            )
        return row

    async def get_history(self, template_id: uuid.UUID) -> list[dict[str, Any]]:
        """Get full version history ordered by version DESC (newest first).

        Args:
            template_id: The UUID of the template.

        Returns:
            A list of dicts with keys: version, content, variables_schema,
            change_description, created_at, hash.
        """
        result = await self.db.execute(
            select(PromptTemplateVersion)
            .where(PromptTemplateVersion.template_id == template_id)
            .order_by(PromptTemplateVersion.version.desc())
        )
        versions = result.scalars().all()

        history: list[dict[str, Any]] = []
        for v in versions:
            history.append({
                "version": v.version,
                "content": v.content,
                "variables_schema": dict(v.variables_schema),
                "change_description": v.change_description,
                "created_at": (
                    v.created_at.isoformat()
                    if v.created_at is not None
                    else None
                ),
                "hash": self._compute_hash(v.content),
            })

        logger.debug(
            "Retrieved %d version(s) for template %s",
            len(history),
            template_id,
        )
        return history

    async def get_latest_version(
        self, template_id: uuid.UUID
    ) -> PromptTemplateVersion:
        """Convenience method to get the current (latest) version.

        Args:
            template_id: The UUID of the template.

        Returns:
            The latest PromptTemplateVersion.

        Raises:
            ValueError: If the template has no versions.
        """
        latest = await self._get_latest_version(template_id)
        if latest is None:
            raise ValueError(f"No versions found for template {template_id}")
        return latest

    # ------------------------------------------------------------------
    # Diff
    # ------------------------------------------------------------------

    @staticmethod
    def diff(v1_content: str, v2_content: str) -> str:
        """Generate a unified diff between two versions' content.

        Args:
            v1_content: Content of the first (older) version.
            v2_content: Content of the second (newer) version.

        Returns:
            A unified diff string, or a message indicating no differences.
        """
        v1_lines = v1_content.splitlines(keepends=True)
        v2_lines = v2_content.splitlines(keepends=True)

        diff_lines = list(
            difflib.unified_diff(
                v1_lines,
                v2_lines,
                fromfile="version_old",
                tofile="version_new",
                lineterm="",
            )
        )

        if not diff_lines:
            return "(no differences)"
        return "\n".join(diff_lines)

    # ------------------------------------------------------------------
    # Hash
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_hash(content: str) -> str:
        """Compute SHA-256 hex digest of content.

        Args:
            content: The string content to hash.

        Returns:
            A 64-character lowercase hex digest string.
        """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_latest_version(
        self, template_id: uuid.UUID
    ) -> Optional[PromptTemplateVersion]:
        """Return the version with the highest version number, or None."""
        result = await self.db.execute(
            select(PromptTemplateVersion)
            .where(PromptTemplateVersion.template_id == template_id)
            .order_by(PromptTemplateVersion.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
