"""
Web fetch tool for retrieving and parsing web page content.

Uses httpx for HTTP requests with configurable timeouts and size limits.
Parses HTML to extract readable text content.
"""

import logging
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import httpx
from httpx import HTTPStatusError, RedirectLoop, TimeoutException

from agent_system.tools.base import BaseTool, ToolDefinition, ToolResult, ToolStatus

logger = logging.getLogger(__name__)


class HTMLTextExtractor(HTMLParser):
    """Extracts plain text from HTML, skipping script and style content."""

    def __init__(self):
        super().__init__()
        self.text_parts: list[str] = []
        self._skip = False
        self._skip_tags = {"script", "style", "noscript", "iframe", "svg", "canvas"}

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._skip_tags:
            self._skip = True

    def handle_endtag(self, tag):
        if tag.lower() in self._skip_tags:
            self._skip = False
        # Add newlines after block-level elements
        if tag.lower() in {"p", "br", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr"}:
            self.text_parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            stripped = data.strip()
            if stripped:
                self.text_parts.append(stripped + " ")

    def get_text(self) -> str:
        """Return extracted and cleaned text."""
        text = "".join(self.text_parts)
        # Collapse multiple whitespace
        import re
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        return text.strip()


class WebFetchTool(BaseTool):
    """Fetches web page content via HTTP GET with size and time limits.

    Extracts readable text from HTML pages. Handles redirects safely.
    """

    def __init__(self, max_size_bytes: int = 2 * 1024 * 1024):
        self._max_size = max_size_bytes
        self._client: httpx.AsyncClient | None = None

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="web_fetch",
            description=(
                "Fetch and extract text content from a web page. "
                "Returns the title and extracted text content. "
                "Use this to read articles, documentation, or any web page."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "format": "uri",
                        "description": "The URL of the web page to fetch.",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Maximum characters to return (default 5000).",
                        "default": 5000,
                    },
                },
                "required": ["url"],
            },
            category="web",
            timeout_seconds=20,
            max_retries=2,
        )

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(20.0),
                follow_redirects=True,
                max_redirects=5,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (compatible; AgentSystem/1.0; "
                        "+https://github.com/agent-system)"
                    ),
                    "Accept": "text/html,application/xhtml+xml,text/plain",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
        return self._client

    async def execute(self, **kwargs) -> ToolResult:
        is_valid, err = self.validate_args(**kwargs)
        if not is_valid:
            return ToolResult(status=ToolStatus.INVALID_ARGS, error=err)

        url = kwargs["url"]
        max_chars = kwargs.get("max_chars", 5000)

        # Validate URL scheme
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return ToolResult(
                status=ToolStatus.INVALID_ARGS,
                error=f"Unsupported URL scheme: {parsed.scheme}. Only http/https allowed.",
            )

        try:
            client = await self._get_client()
            response = await client.get(url)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "").lower()

            # Check size before reading body
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > self._max_size:
                return ToolResult(
                    status=ToolStatus.INVALID_ARGS,
                    error=f"Content too large: {content_length} bytes (max {self._max_size}).",
                )

            # Read with size limit
            content = response.text[: self._max_size]

            # Extract text based on content type
            if "text/html" in content_type:
                title, text = self._extract_html(content)
            elif "text/plain" in content_type:
                title = parsed.netloc
                text = content
            elif "application/json" in content_type:
                title = parsed.netloc
                text = content[:max_chars]
            else:
                title = parsed.netloc
                text = content[:max_chars]

            # Truncate text
            if len(text) > max_chars:
                text = text[:max_chars] + f"\n... [truncated at {max_chars} chars]"

            return ToolResult(
                status=ToolStatus.SUCCESS,
                data={
                    "url": str(response.url),
                    "status_code": response.status_code,
                    "title": title,
                    "content": text,
                    "content_length": len(text),
                    "truncated": len(response.text) > max_chars,
                },
            )

        except TimeoutException:
            return ToolResult(
                status=ToolStatus.TIMEOUT,
                error=f"Request timed out for: {url}",
            )
        except RedirectLoop:
            return ToolResult(
                status=ToolStatus.FATAL_ERROR,
                error=f"Too many redirects for: {url}",
            )
        except HTTPStatusError as e:
            return ToolResult(
                status=ToolStatus.RETRYABLE_ERROR if e.response.status_code >= 500
                else ToolStatus.FATAL_ERROR,
                error=f"HTTP {e.response.status_code}: {e}",
            )
        except Exception as e:
            logger.exception("Unexpected error in web_fetch")
            return ToolResult(
                status=ToolStatus.RETRYABLE_ERROR,
                error=f"Request failed: {e}",
            )

    def _extract_html(self, html: str) -> tuple[str, str]:
        """Extract title and text from HTML content.

        Returns:
            Tuple of (title, body_text).
        """
        import re

        # Extract title
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else "No title"

        # Remove scripts, styles, and comments
        cleaned = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r'<style[^>]*>.*?</style>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r'<!--.*?-->', '', cleaned, flags=re.DOTALL)

        # Extract text
        parser = HTMLTextExtractor()
        try:
            parser.feed(cleaned)
        except Exception:
            # Fallback: strip all tags
            cleaned = re.sub(r'<[^>]+>', ' ', cleaned)
            cleaned = re.sub(r'\s+', ' ', cleaned)
            return title, cleaned.strip()

        return title, parser.get_text()

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
