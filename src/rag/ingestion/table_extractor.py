"""Extract tables from documents into structured formats."""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    import camelot
    HAS_CAMELOT = True
except ImportError:
    HAS_CAMELOT = False


class TableExtractor:
    """Extract tables from PDF and other document formats.

    Uses pdfplumber and camelot-py for PDFs. Falls back to
    basic CSV-style parsing for text documents.
    """

    def __init__(self, use_camelot: bool = False):
        """Initialize table extractor.

        Args:
            use_camelot: Use Camelot for more accurate table extraction (slower)
        """
        self.use_camelot = use_camelot and HAS_CAMELOT
        logger.info(
            "TableExtractor initialized (pdfplumber=%s, camelot=%s)",
            HAS_PDFPLUMBER, self.use_camelot
        )

    async def extract(self, file_path: str, **kwargs) -> list[dict]:
        """Extract all tables from a document.

        Returns list of dicts with:
        {page, table_index, headers, rows, markdown}
        """
        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".pdf":
            return await self._extract_from_pdf(file_path)
        elif ext == ".csv":
            return await self._extract_from_csv(file_path)
        else:
            logger.debug("Table extraction not supported for %s files", ext)
            return []

    async def _extract_from_pdf(self, pdf_path: str) -> list[dict]:
        """Extract tables from PDF using pdfplumber or camelot."""
        tables: list[dict] = []

        if self.use_camelot and HAS_CAMELOT:
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                camelot_tables = await loop.run_in_executor(
                    None, lambda: camelot.read_pdf(pdf_path, pages="all", flavor="lattice")
                )
                for i, table in enumerate(camelot_tables):
                    df = table.df
                    headers = df.iloc[0].tolist() if len(df) > 0 else []
                    rows = df.iloc[1:].values.tolist() if len(df) > 1 else []

                    tables.append({
                        "page": table.page,
                        "table_index": i,
                        "headers": headers,
                        "rows": rows,
                        "markdown": self._to_markdown(headers, rows),
                        "accuracy": table.parsing_report.get("accuracy", 0),
                    })
                return tables
            except Exception as e:
                logger.warning("Camelot failed, falling back to pdfplumber: %s", e)

        # Use pdfplumber
        if HAS_PDFPLUMBER:
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    for page_num, page in enumerate(pdf.pages):
                        page_tables = page.extract_tables()
                        for t_idx, table_data in enumerate(page_tables):
                            if not table_data:
                                continue
                            headers = table_data[0] if table_data else []
                            rows = table_data[1:] if len(table_data) > 1 else []

                            tables.append({
                                "page": page_num + 1,
                                "table_index": t_idx,
                                "headers": [str(h) if h else "" for h in headers],
                                "rows": [[str(c) if c else "" for c in row] for row in rows],
                                "markdown": self._to_markdown(
                                    [str(h) if h else "" for h in headers],
                                    [[str(c) if c else "" for c in row] for row in rows],
                                ),
                            })
            except Exception as e:
                logger.error("pdfplumber table extraction error: %s", e)

        return tables

    async def _extract_from_csv(self, csv_path: str) -> list[dict]:
        """Extract table from CSV file."""
        import csv

        rows = []
        try:
            with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f)
                for row in reader:
                    rows.append(row)
        except UnicodeDecodeError:
            with open(csv_path, "r", encoding="utf-8-sig", errors="replace") as f:
                reader = csv.reader(f)
                for row in reader:
                    rows.append(row)

        if not rows:
            return []

        headers = rows[0] if rows else []
        data_rows = rows[1:] if len(rows) > 1 else []

        return [{
            "page": 1,
            "table_index": 0,
            "headers": headers,
            "rows": data_rows,
            "markdown": self._to_markdown(headers, data_rows),
        }]

    def _to_markdown(self, headers: list[str], rows: list[list[str]]) -> str:
        """Convert table data to Markdown format."""
        if not headers or not rows:
            return ""

        lines = []
        # Header row
        lines.append("| " + " | ".join(str(h) for h in headers) + " |")
        # Separator
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
        # Data rows
        for row in rows:
            padded = list(row) + [""] * (len(headers) - len(row))
            lines.append("| " + " | ".join(str(c)[:200] for c in padded[:len(headers)]) + " |")

        return "\n".join(lines)

    def extract_from_html(self, html_content: str) -> list[dict]:
        """Extract tables from HTML content using basic parsing."""
        tables = []

        # Simple regex-based HTML table extraction
        import re
        table_pattern = re.compile(r'<table[^>]*>(.*?)</table>', re.DOTALL | re.IGNORECASE)
        tr_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL | re.IGNORECASE)
        td_pattern = re.compile(r'<t[dh][^>]*>(.*?)</t[dh]>', re.DOTALL | re.IGNORECASE)
        tag_cleaner = re.compile(r'<[^>]+>')

        for t_idx, table_match in enumerate(table_pattern.finditer(html_content)):
            table_html = table_match.group(1)
            all_rows = []

            for tr_match in tr_pattern.finditer(table_html):
                cells = []
                for td_match in td_pattern.finditer(tr_match.group(1)):
                    cell_text = tag_cleaner.sub('', td_match.group(1)).strip()
                    cells.append(cell_text)
                if cells:
                    all_rows.append(cells)

            if all_rows:
                headers = all_rows[0] if all_rows else []
                rows = all_rows[1:] if len(all_rows) > 1 else []
                tables.append({
                    "page": 1,
                    "table_index": t_idx,
                    "headers": headers,
                    "rows": rows,
                    "markdown": self._to_markdown(headers, rows),
                    "source": "html",
                })

        return tables
