"""Document generation service — render LLM output into downloadable files.

Supported formats: markdown (always), docx (python-docx, optional),
xlsx (openpyxl, optional), pptx (python-pptx, optional). Each format is
best-effort: if the library is missing, that format is reported as unsupported
rather than crashing the whole request.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class GeneratedDocument:
    """A generated document ready for download."""

    filename: str
    content: bytes
    media_type: str
    format: str


class DocumentGenerator:
    """Renders text (or LLM output) into downloadable document formats."""

    def __init__(self, llm: Any = None):
        self.llm = llm

    async def generate_content(self, topic: str, format: str = "md") -> str:
        """Generate content via the LLM, or a placeholder if no LLM is set."""
        if self.llm is not None:
            try:
                response = await self.llm.ainvoke([
                    {"role": "user", "content": (
                        f"请围绕主题「{topic}」生成一份结构完整的文档内容，"
                        f"使用 Markdown 格式，包含标题、分节、列表和要点。"
                    )},
                ])
                return response.content if hasattr(response, "content") else str(response)
            except Exception as exc:  # noqa: BLE001
                logger.warning("LLM content generation failed: %s", exc)
        return (
            f"# {topic}\n\n"
            f"这是关于「{topic}」的示例文档。\n\n"
            f"## 概述\n\n- 要点一\n- 要点二\n- 要点三\n\n"
            f"## 总结\n\n这是一个演示文档，用于验证文档生成与下载功能。\n"
        )

    def render(self, content: str, format: str, title: str = "document") -> GeneratedDocument:
        """Render content into the requested format."""
        fmt = format.lower()
        if fmt == "md" or fmt == "markdown":
            return self._render_markdown(content, title)
        if fmt == "docx":
            return self._render_docx(content, title)
        if fmt == "xlsx":
            return self._render_xlsx(content, title)
        if fmt == "pptx":
            return self._render_pptx(content, title)
        raise ValueError(f"Unsupported format: {format}. Supported: md, docx, xlsx, pptx")

    # ------------------------------------------------------------------
    # Format renderers
    # ------------------------------------------------------------------

    def _render_markdown(self, content: str, title: str) -> GeneratedDocument:
        return GeneratedDocument(
            filename=f"{title}.md",
            content=content.encode("utf-8"),
            media_type="text/markdown",
            format="md",
        )

    def _render_docx(self, content: str, title: str) -> GeneratedDocument:
        try:
            import docx
        except ImportError:
            raise RuntimeError("python-docx not installed; docx format unavailable")

        doc = docx.Document()
        doc.add_heading(title, 0)
        for line in content.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("# "):
                doc.add_heading(line[2:], level=1)
            elif line.startswith("## "):
                doc.add_heading(line[3:], level=2)
            elif line.startswith("### "):
                doc.add_heading(line[4:], level=3)
            elif line.startswith("- "):
                doc.add_paragraph(line[2:], style="List Bullet")
            elif line.startswith("1. "):
                doc.add_paragraph(line[3:], style="List Number")
            else:
                doc.add_paragraph(line)

        buf = io.BytesIO()
        doc.save(buf)
        return GeneratedDocument(
            filename=f"{title}.docx",
            content=buf.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            format="docx",
        )

    def _render_xlsx(self, content: str, title: str) -> GeneratedDocument:
        try:
            import openpyxl
        except ImportError:
            raise RuntimeError("openpyxl not installed; xlsx format unavailable")

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = title[:31] or "Sheet"
        for row_idx, line in enumerate(content.split("\n"), start=1):
            ws.cell(row=row_idx, column=1, value=line.strip())

        buf = io.BytesIO()
        wb.save(buf)
        return GeneratedDocument(
            filename=f"{title}.xlsx",
            content=buf.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            format="xlsx",
        )

    def _render_pptx(self, content: str, title: str) -> GeneratedDocument:
        try:
            from pptx import Presentation
        except ImportError:
            raise RuntimeError("python-pptx not installed; pptx format unavailable")

        prs = Presentation()
        # Title slide
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        slide.shapes.title.text = title

        # Content slides (one per section)
        sections = [s.strip() for s in content.split("\n# ") if s.strip()]
        for section in sections[:10]:
            slide = prs.slides.add_slide(prs.slide_layouts[1])
            lines = section.split("\n")
            slide.shapes.title.text = lines[0].lstrip("# ").strip()
            body = "\n".join(lines[1:])[:500]
            slide.placeholders[1].text = body

        buf = io.BytesIO()
        prs.save(buf)
        return GeneratedDocument(
            filename=f"{title}.pptx",
            content=buf.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            format="pptx",
        )

    def supported_formats(self) -> list[str]:
        """Return the formats that can actually be rendered in this environment."""
        supported = ["md"]
        for fmt, mod in [("docx", "docx"), ("xlsx", "openpyxl"), ("pptx", "pptx")]:
            try:
                __import__(mod)
                supported.append(fmt)
            except ImportError:
                pass
        return supported
