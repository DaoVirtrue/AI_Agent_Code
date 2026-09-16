"""Document tool — 通过 MCP 生成/保存文档（md/docx/xlsx/pptx）.

Wraps the DocumentGenerator service as an MCP tool so an agent can generate
and save documents directly, instead of the logic living in a hardcoded route.
"""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Any

from src.core.tools import BaseTool, ToolDefinition, ToolResult, ToolStatus

logger = logging.getLogger(__name__)


class DocumentTool(BaseTool):
    """Generate and save a document (md/docx/xlsx/pptx) via MCP.

    Args:
        generator: DocumentGenerator instance.
        output_dir: Directory where generated files are written.
    """

    def __init__(self, generator: Any = None, output_dir: str = "uploads"):
        self.generator = generator
        self.output_dir = output_dir
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="document.generate",
            description=(
                "生成并保存文档（md/docx/xlsx/pptx）。给定主题和格式，"
                "生成文档内容并保存到文件，返回文件路径和内容预览。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "文档主题"},
                    "format": {"type": "string", "enum": ["md", "docx", "xlsx", "pptx"], "description": "输出格式"},
                    "title": {"type": "string", "description": "文档标题/文件名（可选）"},
                    "content": {"type": "string", "description": "直接提供的文档内容（可选，缺省则由 LLM 生成）"},
                },
                "required": ["topic", "format"],
            },
            category="document",
            requires_approval=False,  # 生成文档是安全的
            timeout_seconds=60,
            max_retries=1,
        )

    async def execute(self, **kwargs) -> ToolResult:
        is_valid, err = self.validate_args(**kwargs)
        if not is_valid:
            return ToolResult(status=ToolStatus.INVALID_ARGS, error=err)

        topic = kwargs["topic"]
        fmt = kwargs["format"]
        title = kwargs.get("title") or topic[:20]

        if self.generator is None:
            from src.services.document_generator import DocumentGenerator
            self.generator = DocumentGenerator(llm=None)

        try:
            content = kwargs.get("content")
            if content is None:
                content = await self.generator.generate_content(topic, fmt)
            doc = self.generator.render(content, fmt, title)

            # Save to output dir
            filepath = Path(self.output_dir) / doc.filename
            filepath.write_bytes(doc.content)

            return ToolResult(
                status=ToolStatus.SUCCESS,
                data={
                    "filename": doc.filename,
                    "filepath": str(filepath),
                    "format": fmt,
                    "size_bytes": len(doc.content),
                    "content_preview": content[:500],
                },
            )
        except ValueError as e:
            return ToolResult(status=ToolStatus.INVALID_ARGS, error=str(e))
        except RuntimeError as e:
            return ToolResult(status=ToolStatus.FATAL_ERROR, error=str(e))
        except Exception as e:  # noqa: BLE001
            logger.exception("Document generation failed")
            return ToolResult(status=ToolStatus.FATAL_ERROR, error=str(e))
