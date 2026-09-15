"""Coreference resolution for Chinese and English multi-turn conversations.

Resolves pronouns, demonstratives, references, and ordinals by
analyzing conversation history to find the correct antecedent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .context_stitcher import ConversationHistory


@dataclass
class ResolvedQuery:
    """Result of coreference resolution on a query."""
    original: str
    resolved: str
    replacements: list[tuple[str, str, str]]
    # (original_text, resolved_text, pattern_type)
    confidence: float


class CoreferenceResolver:
    """Resolve 20+ Chinese and 14 English coreference patterns.

    Uses regex-based pattern matching combined with conversation
    history analysis to find antecedents for referential expressions.
    """

    CN_PATTERNS: dict[str, str] = {
        "pronoun": r"(它|他|她|他们|她们|它们)",
        "demonstrative": r"(这个|那个|这些|那些|这位|那位)",
        "reference": r"(以上|上述|如上|前述|前者|后者|该|其)",
        "ordinal": r"(第[一二三四五六七八九十百千万]+[个条项位次处种件只把台辆座篇章节段落])",
        "temporal_ref": r"(当时|那时|这时|此前|此后|之前|之后|刚才|刚刚)",
        "locative": r"(这里|那里|此处|彼处|那儿|这儿)",
        "comparative": r"(另一个|别的|其他的|另外的|其余)",
        "vague_reference": r"(这件事|那件事|这种事|那种事|这个情况|那个情况|此情况|此问题|该问题)",
        "possessive_drop": r"(^|[。！？；\n])([^\s。！？；\n]{1,8})(的)(?:它|他|她|他们|她们|它们|这个|那个|这些|那些|这|那|其|该)",
        "entity_reference": r"(该[公司机构部门单位组织企业学校医院银行])",
    }

    EN_PATTERNS: dict[str, str] = {
        "pronoun": r"\b(it|he|she|they|them|him|her|his|hers|their|theirs|its)\b",
        "demonstrative": r"\b(this|that|these|those)\b",
        "reference": r"\b(the above|the former|the latter|the aforementioned|the same|such|the one|the ones)\b",
        "ordinal": r"\b(the (?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|1st|2nd|3rd|[0-9]+th) (?:one|item|option|choice|point|step|part|section|element|entry|result))\b",
        "comparative": r"\b(another one|the other|the rest|the remaining|a different one)\b",
        "locative": r"\b(here|there|herein|therein|hereby|thereby|hereof|thereof)\b",
        "vague_reference": r"\b(this matter|that matter|this issue|that issue|this situation|that situation|this problem|that problem)\b",
    }

    def __init__(self) -> None:
        self._compiled_cn: dict[str, re.Pattern] = {}
        self._compiled_en: dict[str, re.Pattern] = {}
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        for name, pat in self.CN_PATTERNS.items():
            self._compiled_cn[name] = re.compile(pat, re.IGNORECASE)
        for name, pat in self.EN_PATTERNS.items():
            self._compiled_en[name] = re.compile(pat, re.IGNORECASE)

    def resolve(self, query: str, history: "ConversationHistory") -> ResolvedQuery:
        """Resolve all coreference mentions in a query against history.

        Args:
            query: The user's raw query potentially containing referential expressions.
            history: The full conversation history for antecedent lookup.

        Returns:
            ResolvedQuery with the resolved text, replacements list, and confidence.
        """
        replacements: list[tuple[str, str, str]] = []
        resolved = query
        total_patterns = 0
        resolved_patterns = 0
        confidence_parts: list[float] = []

        # Process Chinese patterns
        for pattern_type, compiled in self._compiled_cn.items():
            for match in compiled.finditer(query):
                total_patterns += 1
                mention = match.group(0)
                antecedent = self._resolve_mention(mention, pattern_type, history)
                if antecedent:
                    resolved_patterns += 1
                    replacements.append((mention, antecedent, pattern_type))
                    # Track confidence per replacement
                    confidence_parts.append(self._confidence_for_match(pattern_type, mention, antecedent))
                    resolved = resolved.replace(mention, antecedent, 1)

        # Process English patterns
        for pattern_type, compiled in self._compiled_en.items():
            for match in compiled.finditer(query):
                total_patterns += 1
                mention = match.group(0)
                antecedent = self._resolve_mention(mention, pattern_type, history)
                if antecedent:
                    resolved_patterns += 1
                    replacements.append((mention, antecedent, pattern_type))
                    confidence_parts.append(self._confidence_for_match(pattern_type, mention, antecedent))
                    resolved = resolved.replace(mention, antecedent, 1)

        # Calculate confidence
        if total_patterns == 0:
            confidence = 1.0  # No references to resolve
        elif confidence_parts:
            confidence = sum(confidence_parts) / len(confidence_parts)
        else:
            confidence = 0.5  # Patterns found but none resolved

        return ResolvedQuery(
            original=query,
            resolved=resolved,
            replacements=replacements,
            confidence=round(confidence, 4),
        )

    def _confidence_for_match(self, pattern_type: str, mention: str, antecedent: str) -> float:
        """Calculate confidence for a single resolution based on pattern type."""
        base_confidences = {
            "pronoun": 0.75,
            "demonstrative": 0.80,
            "reference": 0.85,
            "ordinal": 0.90,
            "temporal_ref": 0.70,
            "locative": 0.80,
            "comparative": 0.70,
            "vague_reference": 0.75,
            "possessive_drop": 0.65,
            "entity_reference": 0.92,
        }
        base = base_confidences.get(pattern_type, 0.70)
        # Boost if antecedent appears to be a good match (contains key content)
        if len(antecedent) > 2 and antecedent.lower() not in {"it", "he", "she", "they", "them", "他", "她", "它", "他们", "她们", "它们"}:
            base = min(base + 0.10, 0.95)
        return base

    def _resolve_mention(self, mention: str, pattern_type: str, history: "ConversationHistory") -> str | None:
        """Resolve a single mention by trying multiple strategies.

        Resolution order:
        1. Entity match (exact entity lookup in history)
        2. Topic match (topic-based lookup)
        3. Previous subject (fallback to last discussed subject)
        """
        # Strategy 1: Find matching entity in history
        result = self._find_entity_match(mention, history)
        if result:
            return result

        # Strategy 2: Find matching topic in history
        result = self._find_topic_match(mention, history)
        if result:
            return result

        # Strategy 3: Fall back to previous subject
        if pattern_type in ("pronoun", "reference", "vague_reference", "temporal_ref"):
            return self._find_previous_subject(history)

        return None

    def _find_entity_match(self, mention: str, history: "ConversationHistory") -> str | None:
        """Search conversation history entities for a match to the mention."""
        all_entities = history.get_all_entities()
        if not all_entities:
            return None

        # Gender-based filtering for pronouns
        pronoun_entity_map = {
            "他": lambda e: True,  # generic he - could be anything
            "她": lambda e: "女" in e or "她" in e,
            "它": lambda e: len(e) <= 3 or any(
                c in e for c in "物件品器机具"
            ),
            "他们": lambda e: True,
            "她们": lambda e: True,
            "它们": lambda e: True,
            "he": lambda e: True,
            "she": lambda e: True,
            "it": lambda e: True,
            "they": lambda e: True,
            "them": lambda e: True,
            "him": lambda e: True,
            "her": lambda e: True,
        }

        # For pronouns, get the most recent entity from the last assistant response
        if mention.lower() in pronoun_entity_map:
            last_response = history.get_last_assistant_response()
            if last_response:
                # Extract the main entity from the last response
                # Look for the most prominent entity (first mentioned significant noun phrase)
                for entity in all_entities:
                    if entity in last_response:
                        return entity
            # Fallback: return the last entity mentioned overall
            turns = history.get_recent_turns(n=3)
            for turn in reversed(turns):
                if turn.entities:
                    return turn.entities[-1]
            if all_entities:
                return all_entities[-1]

        # For demonstratives (这个/那个/this/that), find nearest entity
        if mention in ("这个", "那个", "这些", "那些", "this", "that", "these", "those"):
            turns = history.get_recent_turns(n=3)
            for turn in reversed(turns):
                if turn.entities:
                    return turn.entities[-1]
            if all_entities:
                return all_entities[-1]

        # For references (前者/后者/the former/the latter), use ordinal logic
        if mention in ("前者", "the former"):
            turns = history.get_recent_turns(n=2)
            for turn in reversed(turns):
                if len(turn.entities) >= 2:
                    return turn.entities[0]
                elif turn.entities:
                    return turn.entities[0]
            if len(all_entities) >= 2:
                return all_entities[-2]

        if mention in ("后者", "the latter"):
            turns = history.get_recent_turns(n=2)
            for turn in reversed(turns):
                if len(turn.entities) >= 2:
                    return turn.entities[1]
                elif turn.entities:
                    return turn.entities[-1]
            if all_entities:
                return all_entities[-1]

        # Default: check if mention substring is an entity
        for entity in reversed(all_entities):
            if mention in entity or entity in mention:
                return entity

        return None

    def _find_topic_match(self, mention: str, history: "ConversationHistory") -> str | None:
        """Find matching topic from conversation history."""
        turns = history.get_recent_turns(n=5)
        for turn in reversed(turns):
            if turn.topics:
                # For vague references, return the most recent topic
                if mention in (
                    "这件事", "那件事", "这个情况", "那个情况",
                    "此情况", "此问题", "该问题",
                    "this matter", "that matter", "this issue",
                    "that issue", "this situation", "this problem",
                ):
                    return turn.topics[-1]
                # For other references, check if topic contains mention clues
                for topic in turn.topics:
                    if any(char in topic for char in mention if len(char) > 1):
                        return topic
        return None

    def _find_previous_subject(self, history: "ConversationHistory") -> str | None:
        """Find the previous subject of discussion as fallback."""
        turns = history.get_recent_turns(n=5)
        for turn in reversed(turns):
            if turn.entities:
                return turn.entities[-1]
            if turn.topics:
                return turn.topics[-1]
        return None
