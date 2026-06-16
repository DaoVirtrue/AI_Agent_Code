"""
Jinja2 + Pydantic prompt rendering engine with schema validation.

Loads Jinja2 templates from a directory, optionally validates input variables
against Pydantic schemas, and renders templates with StrictUndefined to catch
missing variables early.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    TemplateNotFound,
    meta,
)
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


class PromptEngine:
    """Jinja2 + Pydantic prompt rendering engine with schema validation.

    Loads Jinja2 templates from a directory, optionally validates input
    variables against Pydantic schemas, and renders templates with
    StrictUndefined to catch missing variables early.

    Usage::

        engine = PromptEngine("/path/to/templates")
        engine.register_schema("chat", ChatVars)
        result = engine.render("chat", {"user_name": "Alice", "query": "Hello"})
    """

    def __init__(self, template_dir: str) -> None:
        """Initialize with Jinja2 Environment pointed at template_dir.

        Uses FileSystemLoader, StrictUndefined, autoescape=True.
        Enables trim_blocks and lstrip_blocks for cleaner output.
        Keeps trailing newline.

        Args:
            template_dir: Path to the directory containing .j2 / .jinja2 templates.

        Raises:
            NotADirectoryError: If template_dir does not exist or is not a directory.
        """
        resolved = Path(template_dir).resolve()
        if not resolved.exists():
            raise NotADirectoryError(
                f"Template directory does not exist: {resolved}"
            )
        if not resolved.is_dir():
            raise NotADirectoryError(
                f"Template path is not a directory: {resolved}"
            )

        self.template_dir = str(resolved)
        self._schemas: dict[str, type[BaseModel]] = {}

        self._env = Environment(
            loader=FileSystemLoader(self.template_dir),
            undefined=StrictUndefined,
            autoescape=True,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

        logger.info(
            "PromptEngine initialized with template_dir=%s", self.template_dir
        )

    # ------------------------------------------------------------------
    # Schema registration
    # ------------------------------------------------------------------

    def register_schema(self, template_name: str, schema: type[BaseModel]) -> None:
        """Register a Pydantic schema for a template.

        Variables will be validated against this schema before rendering.
        Overwrites any previously registered schema for the same template.

        Args:
            template_name: The name of the template (as loaded by Jinja2).
            schema: A Pydantic BaseModel subclass to validate variables.

        Raises:
            TypeError: If schema is not a Pydantic BaseModel subclass.
        """
        if not (isinstance(schema, type) and issubclass(schema, BaseModel)):
            raise TypeError(
                f"schema must be a Pydantic BaseModel subclass, got {type(schema)}"
            )
        self._schemas[template_name] = schema
        logger.debug(
            "Registered schema %s for template %r",
            schema.__name__,
            template_name,
        )

    def unregister_schema(self, template_name: str) -> None:
        """Remove a previously registered schema for a template.

        Args:
            template_name: The template name whose schema should be removed.
        """
        self._schemas.pop(template_name, None)
        logger.debug("Unregistered schema for template %r", template_name)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self, template_name: str, variables: dict[str, Any]) -> str:
        """Render a template with the given variables.

        Processing steps:
        1. Validate variables with Pydantic if a schema is registered.
        2. Load the Jinja2 template by name.
        3. Render with the validated (or raw) variables.
        4. Return the rendered string.

        Args:
            template_name: The name of the template file (e.g. "chat" for "chat.j2").
            variables: Dict of variable names to values for template rendering.

        Returns:
            The rendered template as a string.

        Raises:
            ValueError: If schema validation fails or rendering errors occur.
            TemplateNotFound: If the template cannot be found by the loader.
        """
        # Step 1: Pydantic validation (if schema registered)
        validated_vars: dict[str, Any] = dict(variables)
        if template_name in self._schemas:
            schema = self._schemas[template_name]
            try:
                instance = schema(**variables)
                validated_vars = instance.model_dump()
            except ValidationError as exc:
                error_details: list[str] = []
                for error in exc.errors():
                    loc = " -> ".join(str(p) for p in error["loc"])
                    msg = error["msg"]
                    error_details.append(f"  - {loc}: {msg}")
                message = (
                    f"Schema validation failed for template {template_name!r}:\n"
                    + "\n".join(error_details)
                )
                logger.warning("Schema validation failed: %s", message)
                raise ValueError(message) from exc

        # Step 2: Load template
        try:
            jinja_template = self._env.get_template(template_name)
        except TemplateNotFound as exc:
            logger.error("Template not found: %r", template_name)
            raise TemplateNotFound(template_name) from exc

        # Step 3: Render
        try:
            rendered = jinja_template.render(**validated_vars)
        except Exception as exc:
            message = (
                f"Failed to render template {template_name!r}: {exc}"
            )
            logger.error("Rendering error: %s", message)
            raise ValueError(message) from exc

        logger.debug(
            "Rendered template %r with %d variables (%d chars)",
            template_name,
            len(validated_vars),
            len(rendered),
        )
        return rendered

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def list_templates(self) -> list[str]:
        """List all available template names in the template directory.

        Uses the Jinja2 FileSystemLoader to discover templates. Templates
        must have recognizable Jinja2 extensions (.j2, .jinja2, .html, etc.).

        Returns:
            Sorted list of template names (relative paths from template_dir).
        """
        loader = self._env.loader
        if not isinstance(loader, FileSystemLoader):
            # Fallback: scan directory ourselves
            return self._list_templates_fallback()

        templates: list[str] = []
        try:
            templates = loader.list_templates()
        except Exception as exc:
            logger.warning(
                "loader.list_templates() failed: %s; using fallback", exc
            )
            templates = self._list_templates_fallback()

        templates.sort()
        return templates

    def get_template_variables(self, template_name: str) -> list[str]:
        """Parse the template AST to extract undeclared variable names.

        Uses ``jinja2.meta.find_undeclared_variables`` to identify all
        variables referenced in the template that are not set by Jinja2
        constructs (set, for-loop vars, etc.).

        Args:
            template_name: The name of the template to analyze.

        Returns:
            Sorted list of undeclared variable names.

        Raises:
            TemplateNotFound: If the template cannot be found.
        """
        source = self._env.loader.get_source(self._env, template_name)  # type: ignore[union-attr]
        parsed_content = self._env.parse(source)
        variables = meta.find_undeclared_variables(parsed_content)
        result = sorted(variables)
        logger.debug(
            "Template %r variables: %s", template_name, result
        )
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _list_templates_fallback(self) -> list[str]:
        """Walk the template directory and collect files with common extensions."""
        common_extensions = frozenset({".j2", ".jinja2", ".html", ".htm", ".txt"})
        template_path = Path(self.template_dir)
        result: list[str] = []
        for root, _dirs, files in os.walk(template_path):
            for filename in files:
                _, ext = os.path.splitext(filename)
                if ext.lower() in common_extensions:
                    full = Path(root) / filename
                    rel = str(full.relative_to(template_path)).replace(os.sep, "/")
                    result.append(rel)
        result.sort()
        return result

    @property
    def environment(self) -> Environment:
        """Expose the underlying Jinja2 Environment for advanced customization."""
        return self._env
