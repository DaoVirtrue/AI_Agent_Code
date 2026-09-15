"""
Web search tool using DuckDuckGo-like search API.
"""

import json
import logging
from typing import Any

import httpx
from httpx import HTTPStatusError, RequestError, TimeoutException

from src.core.tools import BaseTool, ToolDefinition, ToolResult, ToolStatus

logger = logging.getLogger(__name__)


class WebSearchTool(BaseTool):
    """Performs web searches and returns formatted results.

    Uses DuckDuckGo Instant Answer API (no API key required) as the
    default backend, with support for configurable backends.
    """

    def __init__(self, backend: str = "duckduckgo", max_results: int = 10):
        self._backend = backend
        self._max_results = max_results
        self._http_client: httpx.AsyncClient | None = None

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="web_search",
            description=(
                "Search the internet for information. "
                "Returns a list of results with titles, URLs, and snippets."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query.",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results to return (default 5).",
                        "default": 5,
                    },
                    "region": {
                        "type": "string",
                        "description": "Region code for localized results (e.g., 'us-en', 'zh-cn').",
                        "default": "us-en",
                    },
                },
                "required": ["query"],
            },
            category="web",
            timeout_seconds=15,
            max_retries=2,
        )

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(15.0),
                headers={"User-Agent": "AgentSystem/1.0"},
            )
        return self._http_client

    async def execute(self, **kwargs) -> ToolResult:
        is_valid, err = self.validate_args(**kwargs)
        if not is_valid:
            return ToolResult(status=ToolStatus.INVALID_ARGS, error=err)

        query = kwargs["query"]
        num_results = kwargs.get("num_results", 5)
        region = kwargs.get("region", "us-en")

        try:
            client = await self._get_client()
            results = await self._search_duckduckgo(client, query, num_results, region)

            return ToolResult(
                status=ToolStatus.SUCCESS,
                data={
                    "query": query,
                    "results": results,
                    "total_found": len(results),
                },
            )

        except TimeoutException:
            return ToolResult(
                status=ToolStatus.TIMEOUT,
                error="Web search timed out. The search provider may be unavailable.",
            )
        except RequestError as e:
            return ToolResult(
                status=ToolStatus.RETRYABLE_ERROR,
                error=f"Web search request failed: {e}",
            )
        except Exception as e:
            logger.exception("Unexpected error in web_search")
            return ToolResult(
                status=ToolStatus.FATAL_ERROR,
                error=f"Unexpected error: {e}",
            )

    async def _search_duckduckgo(
        self, client: httpx.AsyncClient, query: str,
        num_results: int, region: str,
    ) -> list[dict]:
        """Perform a DuckDuckGo search via the HTML-based API.

        Falls back to the instant answers API for zero-click results.
        """
        # Use DuckDuckGo's lite/HTML search for comprehensive results
        url = "https://lite.duckduckgo.com/lite/"
        try:
            response = await client.get(
                url,
                params={"q": query, "kl": region},
                follow_redirects=True,
            )
            response.raise_for_status()
        except HTTPStatusError as e:
            logger.warning("DuckDuckGo lite failed (status %d), trying Instant Answer API", e.response.status_code)
            return await self._search_duckduckgo_instant(client, query, num_results, region)

        # Parse the HTML response for results
        results = self._parse_lite_results(response.text, num_results)
        if not results:
            return await self._search_duckduckgo_instant(client, query, num_results, region)

        return results

    async def _search_duckduckgo_instant(
        self, client: httpx.AsyncClient, query: str,
        num_results: int, region: str,
    ) -> list[dict]:
        """Fallback to DuckDuckGo Instant Answer API."""
        url = "https://api.duckduckgo.com/"
        try:
            response = await client.get(
                url,
                params={
                    "q": query,
                    "format": "json",
                    "no_html": 1,
                    "skip_disambig": 1,
                    "kl": region,
                },
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.warning("DuckDuckGo Instant Answer failed: %s", e)
            return []

        results = []

        # Abstract
        if data.get("Abstract") and data.get("AbstractURL"):
            results.append({
                "title": data.get("Heading", query),
                "url": data["AbstractURL"],
                "snippet": data["Abstract"],
                "source": data.get("AbstractSource", "DuckDuckGo"),
            })

        # Related topics
        for topic in (data.get("RelatedTopics", []) or [])[:num_results - len(results)]:
            if isinstance(topic, dict) and "Text" in topic:
                results.append({
                    "title": topic.get("FirstURL", "").rsplit("/", 1)[-1].replace("_", " "),
                    "url": topic.get("FirstURL", ""),
                    "snippet": topic.get("Text", ""),
                    "source": "DuckDuckGo",
                })

        return results[:num_results]

    def _parse_lite_results(self, html: str, num_results: int) -> list[dict]:
        """Parse DuckDuckGo Lite HTML results."""
        results = []
        from html.parser import HTMLParser

        class LiteParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.results = []
                self.in_link = False
                self.in_snippet = False
                self.current_title = ""
                self.current_url = ""
                self.current_snippet = ""
                self._snippet_buffer = ""

            def handle_starttag(self, tag, attrs):
                attrs_dict = dict(attrs)
                if tag == "a" and "href" in attrs_dict:
                    # DuckDuckGo lite uses result-link class
                    self.in_link = True
                    self.current_url = attrs_dict["href"]
                    self._snippet_buffer = ""
                elif tag == "td" and "result-snippet" in attrs_dict.get("class", ""):
                    self.in_snippet = True

            def handle_endtag(self, tag):
                if tag == "a":
                    if self.in_link and self.current_title.strip():
                        self.results.append({
                            "title": self.current_title.strip(),
                            "url": self.current_url,
                            "snippet": "",
                            "source": "Web",
                        })
                    self.in_link = False
                    self.current_title = ""
                    self.current_url = ""
                elif tag == "td":
                    self.in_snippet = False

            def handle_data(self, data):
                if self.in_link:
                    self.current_title += data
                if self.in_snippet:
                    if self.results:
                        self.results[-1]["snippet"] += data

        parser = LiteParser()
        parser.feed(html)

        # Enrich snippets with text from the snippet columns
        # Simple regex-based fallback if parser didn't catch enough
        import re
        if len(parser.results) < num_results:
            link_pattern = re.compile(
                r'<a[^>]+href="([^"]+)"[^>]*class="[^"]*result-link[^"]*"[^>]*>(.*?)</a>',
                re.DOTALL | re.IGNORECASE,
            )
            snippet_pattern = re.compile(
                r'<td[^>]+class="[^"]*result-snippet[^"]*"[^>]*>(.*?)</td>',
                re.DOTALL | re.IGNORECASE,
            )

            links = link_pattern.findall(html)
            snippets = snippet_pattern.findall(html)

            for i, (url, title) in enumerate(links):
                if i >= num_results:
                    break
                snippet_text = ""
                if i < len(snippets):
                    snippet_text = re.sub(r'<[^>]+>', '', snippets[i]).strip()
                results.append({
                    "title": re.sub(r'<[^>]+>', '', title).strip(),
                    "url": url,
                    "snippet": snippet_text[:300],
                    "source": "Web",
                })

        return results[:num_results]

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None
