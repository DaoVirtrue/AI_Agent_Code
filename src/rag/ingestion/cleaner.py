"""Text cleaning utilities for pre-processing document content."""

import logging
import re
import unicodedata
from collections import Counter
from typing import Optional

logger = logging.getLogger(__name__)


class TextCleaner:
    """Clean and normalize text extracted from documents.

    Handles:
    - Whitespace normalization
    - Control character removal
    - Garbled text detection (via character distribution analysis)
    - Boilerplate removal (headers, footers, page numbers)
    - Unicode normalization
    """

    # Patterns for common boilerplate
    PAGE_NUMBER_PATTERN = re.compile(r'^\s*(?:page\s*)?\d+\s*$', re.IGNORECASE)
    HEADER_FOOTER_PATTERNS = [
        re.compile(r'^\s*confidential\s*$', re.IGNORECASE),
        re.compile(r'^\s*all rights reserved\s*$', re.IGNORECASE),
        re.compile(r'^\s*copyright\s*©?\s*\d{4}.*$', re.IGNORECASE),
        re.compile(r'^\s*www\..*\s*$', re.IGNORECASE),
        re.compile(r'^\s*http[s]?://.*\s*$', re.IGNORECASE),
        re.compile(r'^\s*page\s+\d+\s+of\s+\d+\s*$', re.IGNORECASE),
        re.compile(r'^\s*\d+\s*/\s*\d+\s*$'),
    ]

    CONTROL_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')
    MULTIPLE_NEWLINES = re.compile(r'\n{3,}')
    MULTIPLE_SPACES = re.compile(r'[ \t]+')
    LEADING_TRAILING_WHITESPACE = re.compile(r'^\s+|\s+$')

    def __init__(self, remove_boilerplate: bool = True, normalize_unicode: bool = True):
        """Initialize cleaner with options."""
        self.remove_boilerplate = remove_boilerplate
        self.normalize_unicode = normalize_unicode
        logger.info("TextCleaner initialized (boilerplate=%s, unicode=%s)",
                     remove_boilerplate, normalize_unicode)

    def clean(self, text: str) -> str:
        """Full text cleaning pipeline.

        1. Normalize unicode (NFC)
        2. Remove control characters
        3. Normalize whitespace
        4. Remove boilerplate (if enabled)
        5. Trim
        """
        if not text:
            return ""

        # Step 1: Unicode normalization
        if self.normalize_unicode:
            text = unicodedata.normalize("NFC", text)

        # Step 2: Remove control characters (keep newlines and tabs)
        text = self.CONTROL_CHARS.sub("", text)

        # Step 3: Replace non-breaking spaces and other weird whitespace
        text = text.replace("\xa0", " ")  # Non-breaking space
        text = text.replace("​", "")   # Zero-width space
        text = text.replace("﻿", "")   # BOM

        # Step 4: Normalize newlines
        text = text.replace("\r\n", "\n")
        text = text.replace("\r", "\n")
        text = self.MULTIPLE_NEWLINES.sub("\n\n", text)

        # Step 5: Normalize spaces
        text = self.MULTIPLE_SPACES.sub(" ", text)

        # Step 6: Remove boilerplate
        if self.remove_boilerplate:
            text = self.remove_boilerplate_lines(text)

        # Step 7: Trim leading/trailing whitespace
        text = text.strip()

        return text

    def detect_garbled(self, text: str) -> bool:
        """Detect if text appears to be garbled/encoding-corrupted.

        Uses character distribution analysis:
        - Too many non-printable or unusual characters
        - High ratio of replacement characters (U+FFFD)
        - Abnormal character frequency distribution
        """
        if not text or len(text) < 10:
            return False

        total = len(text)

        # Count character categories
        replacement_chars = text.count("�")
        control_chars = sum(1 for c in text if ord(c) < 32 and c not in "\n\t\r")
        private_use = sum(1 for c in text if 0xE000 <= ord(c) <= 0xF8FF)

        # Garbled indicators
        if replacement_chars > total * 0.01:  # >1% replacement chars
            return True

        if control_chars > total * 0.02:  # >2% control chars
            return True

        if private_use > total * 0.05:  # >5% private use area
            return True

        # Check character entropy - too many unique chars relative to length
        unique_ratio = len(set(text)) / total
        if len(text) > 50 and unique_ratio > 0.8:
            return True

        # Check for mixed script confusion (Latin + CJK mixed oddly)
        latin_count = sum(1 for c in text if 'a' <= c.lower() <= 'z')
        cjk_count = sum(1 for c in text if '一' <= c <= '鿿')

        if latin_count > 0 and cjk_count > 0:
            # If both scripts are present, check ratio
            ratio = min(latin_count, cjk_count) / max(latin_count, cjk_count, 1)
            if 0.4 < ratio < 0.6 and total > 100:
                # Suspiciously even mix could indicate encoding issues
                return True

        return False

    def remove_boilerplate_lines(self, text: str) -> str:
        """Remove common boilerplate lines from document text.

        Removes: page numbers, headers, footers, copyright notices,
        URL patterns, and other common document artifacts.
        """
        lines = text.split("\n")
        cleaned_lines = []

        for line in lines:
            stripped = line.strip()

            # Skip empty lines (they'll be re-added by newline normalization)
            if not stripped:
                cleaned_lines.append(line)
                continue

            # Check page number patterns
            if self.PAGE_NUMBER_PATTERN.match(stripped):
                continue

            # Check other boilerplate patterns
            is_boilerplate = False
            for pattern in self.HEADER_FOOTER_PATTERNS:
                if pattern.match(stripped):
                    is_boilerplate = True
                    break

            if not is_boilerplate:
                cleaned_lines.append(line)

        result = "\n".join(cleaned_lines)

        # Re-normalize after removing lines
        result = self.MULTIPLE_NEWLINES.sub("\n\n", result)

        return result

    def extract_useful_sections(self, text: str) -> list[dict]:
        """Extract structured sections from cleaned text.

        Attempts to identify document structure: title, headings,
        paragraphs, lists, and tables.

        Returns list of {type, level, content} dicts.
        """
        sections: list[dict] = []
        lines = text.split("\n")

        heading_pattern = re.compile(
            r'^(?:#{1,6}\s+|(?:Chapter|Section|Part|第[一二三四五六七八九十]+[章节部分篇])\s*[:：]?\s*)'
        )
        list_pattern = re.compile(r'^\s*(?:[\-\*\•\◦\▪\▸\▹\►\▻]\s+|\d+[\.\)]\s+|[a-zA-Z][\.\)]\s+)')

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            if heading_pattern.match(stripped):
                # Determine heading level
                level = 1
                if stripped.startswith("#"):
                    level = min(len(stripped) - len(stripped.lstrip("#")), 6)
                    content = stripped.lstrip("#").strip()
                else:
                    content = stripped

                sections.append({"type": "heading", "level": level, "content": content})

            elif list_pattern.match(stripped):
                content = list_pattern.sub("", stripped, count=1).strip()
                sections.append({"type": "list_item", "level": 0, "content": content})

            else:
                sections.append({"type": "paragraph", "level": 0, "content": stripped})

        return sections

    def normalize_whitespace(self, text: str) -> str:
        """Aggressively normalize all whitespace (for short texts)."""
        if not text:
            return ""
        text = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
        text = self.MULTIPLE_SPACES.sub(" ", text)
        return text.strip()

    def truncate_safe(self, text: str, max_length: int) -> str:
        """Truncate text to max_length characters, trying to break at sentence/word boundary."""
        if len(text) <= max_length:
            return text

        truncated = text[:max_length]

        # Try to break at last sentence boundary
        last_period = truncated.rfind(".")
        last_exclaim = truncated.rfind("!")
        last_question = truncated.rfind("?")
        last_newline = truncated.rfind("\n")

        break_points = [p for p in [last_period, last_exclaim, last_question, last_newline] if p > max_length * 0.5]

        if break_points:
            return truncated[:max(break_points) + 1] + "..."

        # Try to break at last space
        last_space = truncated.rfind(" ")
        if last_space > max_length * 0.8:
            return truncated[:last_space] + "..."

        return truncated + "..."
