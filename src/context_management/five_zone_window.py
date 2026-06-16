"""Five-zone context window management system.

Models context as five priority zones with automatic overflow handling:
compression and truncation of low-priority content when the window fills up.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ZoneConfig:
    """Configuration for a single context zone.

    Attributes:
        max_pct: Maximum percentage of total context window.
        priority: Priority level (higher = harder to evict, 0-100).
        compressible: Can this zone be compressed on overflow?
        cacheable: Can this zone benefit from prompt caching?
    """

    max_pct: float
    priority: int
    compressible: bool
    cacheable: bool = False


class FiveZoneWindow:
    """Five-zone priority-based context management.

    Zones (by priority):
    1. **Pinned** (99): Critical system prompts, rules, persona. Never evicted.
    2. **Priority** (80): Few-shot examples, tool definitions. Not compressible.
    3. **Working** (50): Active conversation turns. High value.
    4. **Reference** (30): Retrieved documents, knowledge. Compressible.
    5. **Archive** (10): Older history, background info. Compressible & first evicted.

    On overflow, lower-priority zones are compressed first, then truncated.

    Usage::

        window = FiveZoneWindow(128000, "gpt-4o", token_counter)
        window.add_to_zone("pinned", system_prompt)
        window.add_to_zone("working", user_message)
        window.add_to_zone("reference", rag_chunks)
        messages = window.build_context()
    """

    ZONES: dict[str, ZoneConfig] = {
        "pinned": ZoneConfig(max_pct=0.20, priority=99, compressible=False, cacheable=True),
        "priority": ZoneConfig(max_pct=0.25, priority=80, compressible=False, cacheable=False),
        "working": ZoneConfig(max_pct=0.30, priority=50, compressible=False, cacheable=False),
        "reference": ZoneConfig(max_pct=0.20, priority=30, compressible=True, cacheable=False),
        "archive": ZoneConfig(max_pct=0.05, priority=10, compressible=True, cacheable=False),
    }

    def __init__(
        self,
        context_window: int,
        model: str,
        token_counter: Any,
        zones: dict[str, ZoneConfig] | None = None,
    ) -> None:
        """Initialize the five-zone window.

        Args:
            context_window: Total context window size in tokens.
            model: Model identifier.
            token_counter: TokenCounter instance.
            zones: Optional custom zone configuration.
        """
        self.context_window = context_window
        self.model = model
        self.token_counter = token_counter
        self.zones_config = zones if zones is not None else dict(self.ZONES)

        # Content storage: zone_name -> OrderedDict[content_key -> content]
        self._content: dict[str, OrderedDict[str, Any]] = {
            name: OrderedDict() for name in self.zones_config
        }

        # Token count cache per zone
        self._zone_tokens: dict[str, int] = {name: 0 for name in self.zones_config}

        # Content id counter
        self._next_id = 0

        # Compression state
        self._compressed: dict[str, bool] = {name: False for name in self.zones_config}

    def add_to_zone(self, zone: str, content: Any, key: str | None = None) -> str:
        """Add content to a zone.

        Args:
            zone: Zone name (pinned, priority, working, reference, archive).
            content: Content to add. Can be a message dict, text string,
                or list of message dicts.
            key: Optional key for referencing this content later.

        Returns:
            Key used to store the content.

        Raises:
            ValueError: If zone name is invalid.
        """
        if zone not in self.zones_config:
            raise ValueError(f"Invalid zone '{zone}'. Must be one of {list(self.zones_config)}")

        if key is None:
            key = f"_{self._next_id}"
            self._next_id += 1

        self._content[zone][key] = content
        self._zone_tokens[zone] = self._count_zone(zone)
        self._compressed[zone] = False

        self._check_overflow()
        return key

    def remove_from_zone(self, zone: str, key: str) -> bool:
        """Remove content from a zone by key.

        Args:
            zone: Zone name.
            key: Content key.

        Returns:
            True if removed, False if not found.
        """
        if zone not in self._content:
            return False

        if key in self._content[zone]:
            del self._content[zone][key]
            self._zone_tokens[zone] = self._count_zone(zone)
            return True
        return False

    def build_context(self) -> list[dict[str, Any]]:
        """Build the final context messages list.

        Messages are ordered by zone priority: pinned first, archive last.

        Returns:
            List of message dicts.
        """
        result: list[dict[str, Any]] = []

        # Sort zones by priority descending
        sorted_zones = sorted(
            self.zones_config.items(),
            key=lambda x: x[1].priority,
            reverse=True,
        )

        for zone_name, _config in sorted_zones:
            for content in self._content[zone_name].values():
                if isinstance(content, dict):
                    result.append(content)
                elif isinstance(content, list):
                    result.extend(content)
                elif isinstance(content, str):
                    result.append({"role": "system", "content": content})
                else:
                    result.append({"role": "system", "content": str(content)})

        return result

    def get_zone_tokens(self, zone: str) -> int:
        """Get token count for a specific zone.

        Args:
            zone: Zone name.

        Returns:
            Token count.
        """
        return self._zone_tokens.get(zone, 0)

    def get_fill_percentage(self) -> float:
        """Get overall context window fill percentage.

        Returns:
            Percentage from 0.0 to 100.0+.
        """
        if self.context_window <= 0:
            return 0.0
        return (self._count_all() / self.context_window) * 100.0

    def clear_zone(self, zone: str) -> None:
        """Remove all content from a zone.

        Args:
            zone: Zone name.
        """
        if zone in self._content:
            self._content[zone].clear()
            self._zone_tokens[zone] = 0
            self._compressed[zone] = False

    def clear_all(self) -> None:
        """Remove all content from all zones."""
        for zone in self._content:
            self._content[zone].clear()
            self._zone_tokens[zone] = 0
            self._compressed[zone] = False

    def _check_overflow(self) -> None:
        """Check and resolve context overflow.

        Strategy:
        1. If within budget: no action.
        2. Compress compressible zones (lowest priority first).
        3. Truncate from lowest-priority zones if still over.
        """
        total = self._count_all()
        if total <= self.context_window:
            return

        logger.warning(
            "Context overflow: %d/%d tokens used. Attempting compression.",
            total,
            self.context_window,
        )

        # Step 1: Compress low-priority compressible zones
        self._compress_low_priority()

        # Step 2: If still over, truncate from lowest priority
        if self._count_all() > self.context_window:
            self._truncate_low_priority()

    def _compress_low_priority(self) -> None:
        """Compress the lowest-priority compressible zones.

        In this implementation, "compression" for reference/archive zones
        means keeping only content identifiers when items exceed a certain
        count, and truncating long text content.

        For LLM-based compression, use LLMLinguaCompressor externally
        before calling add_to_zone().
        """
        # Sort zones by priority ascending (lowest first for compression)
        sorted_zones = sorted(
            self.zones_config.items(),
            key=lambda x: x[1].priority,
        )

        for zone_name, config in sorted_zones:
            if not config.compressible:
                continue
            if not self._content[zone_name]:
                continue

            # Compress long text content to first 500 chars + count marker
            for key, content in list(self._content[zone_name].items()):
                if isinstance(content, str) and len(content) > 500:
                    self._content[zone_name][key] = (
                        content[:500]
                        + f" ... [{len(content) - 500} more characters condensed]"
                    )
                elif isinstance(content, list) and len(content) > 3:
                    # Keep first and last items, note mid truncation
                    self._content[zone_name][key] = [
                        content[0],
                        {"role": "system", "content": f"[{len(content) - 2} items omitted]"},
                        content[-1],
                    ]

            self._zone_tokens[zone_name] = self._count_zone(zone_name)
            self._compressed[zone_name] = True

            if self._count_all() <= self.context_window:
                break

    def _truncate_low_priority(self) -> None:
        """Truncate content from lowest-priority zones until budget fits.

        Removes content from archive and reference zones first, dropping
        oldest items within each zone.
        """
        sorted_zones = sorted(
            self.zones_config.items(),
            key=lambda x: x[1].priority,
        )

        for zone_name, config in sorted_zones:
            if not self._content[zone_name]:
                continue

            while self._content[zone_name] and self._count_all() > self.context_window:
                # Remove oldest item (first in OrderedDict)
                oldest_key = next(iter(self._content[zone_name]))
                del self._content[zone_name][oldest_key]

            self._zone_tokens[zone_name] = self._count_zone(zone_name)

            if self._count_all() <= self.context_window:
                logger.info("Truncation resolved overflow")
                break

        if self._count_all() > self.context_window:
            logger.error(
                "Unable to resolve context overflow even after truncating all "
                "low-priority zones. %d tokens remaining over %d limit.",
                self._count_all(),
                self.context_window,
            )

    def _count_all(self) -> int:
        """Count total tokens across all zones."""
        total = 0
        for content_dict in self._content.values():
            for item in content_dict.values():
                if isinstance(item, dict):
                    total += self._count_message(item)
                elif isinstance(item, list):
                    for sub_item in item:
                        if isinstance(sub_item, dict):
                            total += self._count_message(sub_item)
                        elif isinstance(sub_item, str):
                            total += self.token_counter.count(sub_item, self.model)
                elif isinstance(item, str):
                    total += self.token_counter.count(item, self.model)
                else:
                    total += self.token_counter.count(str(item), self.model)
        return total

    def _count_zone(self, zone: str) -> int:
        """Count tokens in a specific zone."""
        total = 0
        for item in self._content[zone].values():
            if isinstance(item, dict):
                total += self._count_message(item)
            elif isinstance(item, list):
                for sub_item in item:
                    if isinstance(sub_item, dict):
                        total += self._count_message(sub_item)
                    elif isinstance(sub_item, str):
                        total += self.token_counter.count(sub_item, self.model)
            elif isinstance(item, str):
                total += self.token_counter.count(item, self.model)
            else:
                total += self.token_counter.count(str(item), self.model)
        return total

    def _count_message(self, msg: dict[str, Any]) -> int:
        """Count tokens for a single message dict."""
        content = msg.get("content", "")
        if isinstance(content, str):
            return self.token_counter.count(content, self.model)
        if isinstance(content, list):
            return sum(
                self.token_counter.count(
                    part.get("text", "") if isinstance(part, dict) else str(part),
                    self.model,
                )
                for part in content
            )
        return self.token_counter.count(str(content), self.model)

    def report(self) -> dict[str, Any]:
        """Generate a status report for the five-zone window.

        Returns:
            Dict with per-zone token usage and status.
        """
        total = self._count_all()
        zones_report: dict[str, dict] = {}

        for zone_name, config in sorted(
            self.zones_config.items(),
            key=lambda x: x[1].priority,
            reverse=True,
        ):
            token_count = self._zone_tokens[zone_name]
            item_count = len(self._content[zone_name])
            max_allowed = int(self.context_window * config.max_pct)
            within_budget = token_count <= max_allowed

            zones_report[zone_name] = {
                "tokens": token_count,
                "max_allowed": max_allowed,
                "items": item_count,
                "within_budget": within_budget,
                "compressed": self._compressed[zone_name],
                "pct_of_window": round(token_count / self.context_window * 100, 1) if self.context_window > 0 else 0.0,
                "priority": config.priority,
            }

        return {
            "context_window": self.context_window,
            "total_used": total,
            "total_remaining": self.context_window - total,
            "fill_pct": round(self.get_fill_percentage(), 1),
            "is_overflow": total > self.context_window,
            "zones": zones_report,
        }
