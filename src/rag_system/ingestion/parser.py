"""Multi-format document parser for PDF, DOCX, HTML, MD, TXT, CSV files.

Uses a pluggable backend architecture. When the 'unstructured' library
is available it is preferred; otherwise falls back to built-in parsers
for each format.
"""

from __future__ import annotations

import csv
import html.parser as html_parser
import io
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)

try:
    from unstructured.partition.auto import partition
    HAS_UNSTRUCTURED = True
except ImportError:
    HAS_UNSTRUCTURED = False
    logger.warning("unstructured not installed; using built-in parsers")

try:
    import docx
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

try:
    import PyPDF2
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False


@dataclass
class ParsedDocument:
    """Result of document parsing."""
    file_path: str
    file_type: str
    title: str = ""
    content: str = ""
    pages: list[dict] = field(default_factory=list)
    tables: list[dict] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    parse_time_ms: float = 0.0
    parse_errors: list[str] = field(default_factory=list)
    char_count: int = 0
    word_count: int = 0


class DocumentParser:
    """Multi-format document parser with automatic format detection.

    Supported formats: PDF, DOCX, MD, HTML, TXT, CSV.
    Uses 'unstructured' library when available, falls back to
    format-specific parsers otherwise.
    """

    SUPPORTED_FORMATS = {".pdf", ".docx", ".md", ".html", ".txt", ".csv", ".json"}

    # File type to MIME type mapping
    MIME_TYPES = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".md": "text/markdown",
        ".html": "text/html",
        ".txt": "text/plain",
        ".csv": "text/csv",
        ".json": "application/json",
    }

    def __init__(self, use_unstructured: bool = True):
        """Initialize parser with backend selection."""
        self.use_unstructured = use_unstructured and HAS_UNSTRUCTURED
        logger.info(
            "DocumentParser initialized (unstructured=%s, pypdf=%s, docx=%s, pdfplumber=%s)",
            self.use_unstructured, HAS_PYPDF, HAS_DOCX, HAS_PDFPLUMBER
        )

    async def parse(self, file_path: str, file_type: Optional[str] = None) -> ParsedDocument:
        """Parse a document file into a structured ParsedDocument."""
        import time
        start = time.time()

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if file_type is None:
            file_type = path.suffix.lower()

        if file_type not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported file type: {file_type}. Supported: {self.SUPPORTED_FORMATS}"
            )

        errors: list[str] = []
        content = ""
        pages = []
        tables = []

        try:
            if self.use_unstructured:
                content, pages, tables = await self._parse_with_unstructured(str(path))
            else:
                content, pages, tables, errs = await self._parse_native(str(path), file_type)
                errors.extend(errs)
        except Exception as e:
            errors.append(f"Parse error: {str(e)}")
            logger.exception("Error parsing %s", file_path)

        if not content and not pages:
            errors.append("No content extracted from document")

        # Build result
        result = ParsedDocument(
            file_path=str(path),
            file_type=file_type,
            title=path.stem,
            content=content,
            pages=pages,
            tables=tables,
            metadata={
                "file_name": path.name,
                "file_size": path.stat().st_size,
                "mime_type": self.MIME_TYPES.get(file_type, "application/octet-stream"),
            },
            parse_time_ms=(time.time() - start) * 1000,
            parse_errors=errors,
            char_count=len(content),
            word_count=len(content.split()) if content else 0,
        )

        logger.info(
            "Parsed %s: %d chars, %d pages, %d tables (%.0fms)",
            path.name, result.char_count, len(pages), len(tables), result.parse_time_ms
        )

        return result

    async def parse_bytes(self, content: bytes, filename: str) -> ParsedDocument:
        """Parse document from raw bytes (e.g., from an upload)."""
        import tempfile
        import time
        start = time.time()

        suffix = Path(filename).suffix.lower()
        if suffix not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported file type: {suffix}")

        # Write to temp file for parsing
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            result = await self.parse(tmp_path, file_type=suffix)
            result.metadata["original_filename"] = filename
            return result
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def supports_format(self, file_type: str) -> bool:
        """Check if a file type is supported."""
        return file_type.lower() in self.SUPPORTED_FORMATS

    async def _parse_with_unstructured(self, file_path: str) -> tuple[str, list[dict], list[dict]]:
        """Parse using unstructured library."""
        elements = partition(filename=file_path)

        content_parts = []
        pages: list[dict] = []
        tables: list[dict] = []
        current_page = {"page_num": 1, "elements": [], "text": ""}

        for el in elements:
            el_type = str(el).split(",")[0] if hasattr(el, '__str__') else type(el).__name__

            if hasattr(el, 'metadata') and el.metadata:
                page_num = getattr(el.metadata, 'page_number', 1)
                if page_num != current_page["page_num"]:
                    pages.append(current_page)
                    current_page = {"page_num": page_num, "elements": [], "text": ""}

            text = str(el) if hasattr(el, '__str__') else ""
            content_parts.append(text)

            if 'table' in el_type.lower() or 'Table' in el_type:
                tables.append({
                    "page": current_page["page_num"],
                    "content": text,
                    "format": "unstructured",
                })

        pages.append(current_page)
        content = "\n\n".join(content_parts)

        return content, pages, tables

    async def _parse_native(
        self, file_path: str, file_type: str
    ) -> tuple[str, list[dict], list[dict], list[str]]:
        """Parse using native (non-unstructured) parsers."""
        errors: list[str] = []
        content = ""
        pages: list[dict] = []
        tables: list[dict] = []

        try:
            if file_type == ".pdf":
                content, pages, tables, errs = self._parse_pdf_native(file_path)
                errors.extend(errs)
            elif file_type == ".docx":
                content, pages, errs = self._parse_docx_native(file_path)
                errors.extend(errs)
            elif file_type in (".md", ".txt"):
                content = self._parse_text_native(file_path)
            elif file_type == ".html":
                content = self._parse_html_native(file_path)
            elif file_type == ".csv":
                content, tables = self._parse_csv_native(file_path)
            elif file_type == ".json":
                content = self._parse_json_native(file_path)
            else:
                errors.append(f"No native parser for {file_type}")
        except Exception as e:
            errors.append(f"Native parse error: {str(e)}")

        return content, pages, tables, errors

    def _parse_pdf_native(self, file_path: str) -> tuple[str, list[dict], list[dict], list[str]]:
        """Parse PDF using PyPDF2 or pdfplumber natively."""
        errors: list[str] = []
        pages: list[dict] = []
        tables: list[dict] = []
        content_parts: list[str] = []

        if HAS_PDFPLUMBER:
            try:
                import pdfplumber as plumber
                with plumber.open(file_path) as pdf:
                    for i, page in enumerate(pdf.pages):
                        text = page.extract_text() or ""
                        content_parts.append(text)
                        pages.append({"page_num": i + 1, "text": text})

                        # Extract tables
                        page_tables = page.extract_tables()
                        for t_idx, table in enumerate(page_tables):
                            tables.append({
                                "page": i + 1,
                                "table_index": t_idx,
                                "headers": table[0] if table else [],
                                "rows": table[1:] if len(table) > 1 else [],
                            })
            except Exception as e:
                errors.append(f"pdfplumber error: {e}")
                logger.debug("pdfplumber failed, falling back to PyPDF2")

        # Fallback to PyPDF2
        if not content_parts and HAS_PYPDF:
            try:
                reader = PyPDF2.PdfReader(file_path)
                for i, page in enumerate(reader.pages):
                    text = page.extract_text() or ""
                    content_parts.append(text)
                    pages.append({"page_num": i + 1, "text": text})
            except Exception as e:
                errors.append(f"PyPDF2 error: {e}")

        if not content_parts:
            errors.append("No text extracted from PDF")

        content = "\n\n".join(content_parts)
        return content, pages, tables, errors

    def _parse_docx_native(self, file_path: str) -> tuple[str, list[dict], list[str]]:
        """Parse DOCX using python-docx."""
        errors: list[str] = []
        pages: list[dict] = []

        if not HAS_DOCX:
            return "", [], ["python-docx not installed"]

        try:
            doc = docx.Document(file_path)

            # Extract paragraphs
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            content = "\n\n".join(paragraphs)

            # Extract tables
            for t_idx, table in enumerate(doc.tables):
                rows = []
                for row in table.rows:
                    cells = [cell.text for cell in row.cells]
                    rows.append(cells)
                # Tables are added to pages dict
                pages.append({
                    "table_index": t_idx,
                    "headers": rows[0] if rows else [],
                    "rows": rows[1:] if len(rows) > 1 else [],
                })

            return content, pages, errors
        except Exception as e:
            errors.append(f"DOCX parse error: {e}")
            return "", [], errors

    def _parse_text_native(self, file_path: str) -> str:
        """Parse plain text or markdown files."""
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    def _parse_html_native(self, file_path: str) -> str:
        """Parse HTML files, extracting text content."""
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            html_content = f.read()

        # Simple HTML text extraction
        class HTMLTextExtractor(html_parser.HTMLParser):
            def __init__(self):
                super().__init__()
                self.text: list[str] = []
                self.skip_tags = {"script", "style", "meta", "link", "head"}
                self.current_tag = ""

            def handle_starttag(self, tag, attrs):
                self.current_tag = tag

            def handle_endtag(self, tag):
                if tag in ("p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6"):
                    self.text.append("\n")
                self.current_tag = ""

            def handle_data(self, data):
                if self.current_tag not in self.skip_tags:
                    text = data.strip()
                    if text:
                        self.text.append(text)

        extractor = HTMLTextExtractor()
        extractor.feed(html_content)
        return "\n".join(extractor.text)

    def _parse_csv_native(self, file_path: str) -> tuple[str, list[dict]]:
        """Parse CSV files into text and table representations."""
        rows = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f)
                for row in reader:
                    rows.append(row)
        except Exception:
            with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
                reader = csv.reader(f)
                for row in reader:
                    rows.append(row)

        if not rows:
            return "", []

        headers = rows[0] if rows else []
        data_rows = rows[1:] if len(rows) > 1 else []

        # Text representation
        lines = [", ".join(headers)]
        for row in data_rows:
            lines.append(", ".join(row))
        content = "\n".join(lines)

        tables = [{"page": 1, "headers": headers, "rows": data_rows, "format": "csv"}]

        return content, tables

    def _parse_json_native(self, file_path: str) -> str:
        """Parse JSON files, prettifying for LLM consumption."""
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)

        if isinstance(data, list):
            lines = []
            for item in data:
                if isinstance(item, dict):
                    lines.append(json.dumps(item, ensure_ascii=False))
                else:
                    lines.append(str(item))
            return "\n".join(lines)
        elif isinstance(data, dict):
            return json.dumps(data, indent=2, ensure_ascii=False)
        else:
            return str(data)
