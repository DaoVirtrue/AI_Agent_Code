"""
5-layer prompt injection defense system.

Layers:
1. Input sanitization – normalize, strip dangerous patterns
2. Injection pattern detection – regex and heuristic based
3. Role boundary addition – XML/Markdown delimiters to separate user from system
4. Output filtering – remove potential leaked system instructions
5. Audit logging – record detection results for analysis
"""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Maximum allowed user input length before truncation.
MAX_INPUT_LENGTH = 32_000


class InjectionDefense:
    """5-layer prompt injection defense system.

    Layers:
    1. Input sanitization - normalize, strip dangerous patterns
    2. Injection pattern detection - regex and heuristic based
    3. Role boundary addition - XML/Markdown delimiters to separate user from system
    4. Output filtering - remove potential leaked system instructions
    5. Audit logging - record detection results for analysis

    Usage::

        defense = InjectionDefense()
        sanitized = defense.sanitize_input(user_text)
        is_injection, matches = defense.detect_injection_attempt(sanitized)
        if is_injection:
            log.warning("Injection attempt detected: %s", matches)
    """

    # ------------------------------------------------------------------
    # Injection patterns (regex)
    # ------------------------------------------------------------------

    INJECTION_PATTERNS: list[str] = [
        # English patterns
        r"(?i)ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?|messages?)",
        r"(?i)you\s+are\s+now\s+(a\s+)?(different|new|another)",
        r"(?i)(forget|disregard)\s+(everything|all)\s+(you|I)\s+(said|told|mentioned)",
        r"(?i)new\s+system\s+(prompt|message|instruction)",
        r"(?i)pretend\s+(you\s+are|to\s+be)",
        r"(?i)act\s+as\s+(if\s+)?(you\s+are|a\s+different)",
        r"(?i)DAN\s+(mode|prompt|jailbreak)",
        r"(?i)developer\s+mode",
        r"(?i)system\s*:\s*",  # Attempt to inject system-level prefix
        r"(?i)<\|system\|>",  # Special token injection
        r"(?i)\[system\]",  # Another variant
        # Chinese patterns
        r"(?i)你(\s+)?是(\s+)?一个",  # "you are a..."
        r"(?i)现在(\s+)?开始",  # "now begin..."
        r"(?i)忽略(\s+)?以上",  # "ignore above..."
        r"(?i)忘记(\s+)?(所有|一切)",  # "forget everything"
        # Separator-based injections
        r"[-=*_#]{3,}\s*(system|instructions?|prompts?|rules?)",
        r"\"\"\".*?(system|instructions?|prompts?).*?\"\"\"",
        r"<\|.*?\|>",  # Special tokens
    ]

    # Characters considered dangerous for prompt injection
    DANGEROUS_CHARS_PATTERN: re.Pattern = re.compile(
        r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]"
    )

    # Patterns that could indicate system prompt leakage in outputs
    OUTPUT_LEAK_PATTERNS: list[str] = [
        r"(?i)you\s+are\s+(a\s+)?(helpful|an?\s+AI|Claude|GPT|assistant)",
        r"(?i)(your\s+)?system\s+(instructions?|prompts?|messages?)\s+(are|is|were)",
        r"(?i)Here\s+(is|are)\s+(my|the)\s+(instructions?|prompts?)",
        r"(?i)<system>(.*?)</system>",
        r"(?i)\[system\](.*?)\[/system\]",
        r"(?i)You\s+must\s+(always|never|follow)",
        r"(?i)Your\s+primary\s+(directive|goal|task)",
    ]

    # Common separator patterns to normalize
    _SEPARATOR_RE = re.compile(r"^[-=*_#]{3,}\s*$", re.MULTILINE)
    _WHITESPACE_RE = re.compile(r"[ \t]+")
    _NEWLINE_RE = re.compile(r"\n{3,}")

    def __init__(self) -> None:
        """Initialize with compiled regex patterns and audit log storage."""
        self._compiled_patterns: list[re.Pattern] = [
            re.compile(p) for p in self.INJECTION_PATTERNS
        ]
        self._compiled_leak_patterns: list[re.Pattern] = [
            re.compile(p) for p in self.OUTPUT_LEAK_PATTERNS
        ]
        self._audit_log: list[dict[str, Any]] = []
        logger.info(
            "InjectionDefense initialized with %d injection patterns, "
            "%d leak patterns",
            len(self.INJECTION_PATTERNS),
            len(self.OUTPUT_LEAK_PATTERNS),
        )

    # ------------------------------------------------------------------
    # Layer 1: Input Sanitization
    # ------------------------------------------------------------------

    def sanitize_input(self, text: str) -> str:
        """Sanitize user input before it interacts with prompts.

        Performs:
        - Remove null bytes and control characters (except common whitespace).
        - Normalize excessive whitespace.
        - Collapse repeated newlines (3+ -> 2).
        - Strip leading/trailing whitespace.
        - Truncate to MAX_INPUT_LENGTH if exceeded.
        - Remove fenced separator lines that could be used for injection.

        Args:
            text: The raw user input string.

        Returns:
            Sanitized string safe for prompt inclusion.
        """
        if not text:
            return ""

        # Remove dangerous control characters
        sanitized = self.DANGEROUS_CHARS_PATTERN.sub("", text)

        # Normalize horizontal whitespace (tabs -> spaces, collapse multiple spaces)
        sanitized = self._WHITESPACE_RE.sub(" ", sanitized)

        # Collapse excessive blank lines (3+ newlines -> 2)
        sanitized = self._NEWLINE_RE.sub("\n\n", sanitized)

        # Strip fenced separators (----- , ===== , ######, etc.)
        sanitized = self._SEPARATOR_RE.sub("", sanitized)

        # Strip leading/trailing whitespace
        sanitized = sanitized.strip()

        # Truncate to max length
        if len(sanitized) > MAX_INPUT_LENGTH:
            logger.warning(
                "Input truncated from %d to %d chars", len(sanitized), MAX_INPUT_LENGTH
            )
            # Try to cut at a sentence boundary near the limit
            cut_point = MAX_INPUT_LENGTH
            for sep in (". ", "。", "\n", " "):
                pos = sanitized.rfind(sep, MAX_INPUT_LENGTH - 500, MAX_INPUT_LENGTH)
                if pos > 0:
                    cut_point = pos + len(sep)
                    break
            sanitized = sanitized[:cut_point].rstrip()

        return sanitized

    # ------------------------------------------------------------------
    # Layer 2: Injection Detection
    # ------------------------------------------------------------------

    def detect_injection_attempt(self, text: str) -> tuple[bool, list[dict[str, Any]]]:
        """Detect potential injection attempts using regex and heuristics.

        Scans the text against compiled regex patterns and also runs
        heuristic checks: character entropy (high randomness may indicate
        encoded payloads), excessive repetition, unusual length patterns.

        Args:
            text: The (possibly sanitized) user input to examine.

        Returns:
            A tuple of (is_injection: bool, matches: list[dict]).
            Each match dict contains: pattern, match_text, start, end, index.
        """
        if not text:
            return False, []

        matches: list[dict[str, Any]] = []

        # Regex-based detection
        for idx, pattern in enumerate(self._compiled_patterns):
            for m in pattern.finditer(text):
                matches.append({
                    "pattern": self.INJECTION_PATTERNS[idx],
                    "pattern_index": idx,
                    "match_text": m.group(),
                    "start": m.start(),
                    "end": m.end(),
                })

        # Heuristic: character entropy check
        entropy = self._compute_entropy(text)
        if entropy > 5.5 and len(text) > 50:
            matches.append({
                "pattern": "heuristic:high_entropy",
                "pattern_index": -1,
                "match_text": f"entropy={entropy:.2f}",
                "start": 0,
                "end": min(len(text), 100),
            })

        # Heuristic: excessive character repetition
        repetition_score = self._compute_repetition(text)
        if repetition_score > 0.6 and len(text) > 20:
            matches.append({
                "pattern": "heuristic:high_repetition",
                "pattern_index": -1,
                "match_text": f"repetition_score={repetition_score:.2f}",
                "start": 0,
                "end": min(len(text), 100),
            })

        # Heuristic: unusual ratio of special characters
        special_ratio = self._compute_special_char_ratio(text)
        if special_ratio > 0.35 and len(text) > 30:
            matches.append({
                "pattern": "heuristic:high_special_chars",
                "pattern_index": -1,
                "match_text": f"special_ratio={special_ratio:.2f}",
                "start": 0,
                "end": min(len(text), 100),
            })

        is_injection = len(matches) > 0
        if is_injection:
            logger.warning(
                "Injection attempt detected: %d matches in input of %d chars",
                len(matches),
                len(text),
            )

        return is_injection, matches

    # ------------------------------------------------------------------
    # Layer 3: Role Boundary Addition
    # ------------------------------------------------------------------

    def add_role_boundaries(self, system_prompt: str) -> str:
        """Wrap system prompt in XML-style role boundaries to make it harder
        for injection to override.

        Adds clear delimitation markers that separate system instructions
        from user content, making it structurally harder for user input
        to escape into the system role.

        Args:
            system_prompt: The system prompt / instructions string.

        Returns:
            The system prompt wrapped in role boundary markers.
        """
        wrapped = (
            '<|system_role start|>\n'
            f'{system_prompt.strip()}\n'
            '<|system_role end|>\n'
            '<|user_role start|>'
        )
        logger.debug("Added role boundaries to system prompt (%d chars)", len(system_prompt))
        return wrapped

    def wrap_user_input(self, user_input: str) -> str:
        """Wrap user input with role boundary delimiters.

        This is the counterpart to add_role_boundaries – it wraps user
        content so the model can clearly distinguish it from system text.

        Args:
            user_input: The (sanitized) user input.

        Returns:
            User input wrapped with end-of-user delimiter.
        """
        wrapped = f'{user_input}\n<|user_role end|>'
        return wrapped

    # ------------------------------------------------------------------
    # Layer 4: Output Filtering
    # ------------------------------------------------------------------

    def filter_output(self, text: str) -> str:
        """Filter model output to remove potential leaked system instructions.

        Scans the output for patterns that look like system prompt fragments
        and redacts them, replacing with a placeholder.

        Args:
            text: The raw model output string.

        Returns:
            Filtered output with leaked system fragments redacted.
        """
        if not text:
            return text

        filtered = text
        redaction_count = 0

        for idx, pattern in enumerate(self._compiled_leak_patterns):
            if pattern.search(filtered):
                # Redact: replace the matched region with a placeholder
                filtered, subs = pattern.subn("[REDACTED]", filtered)
                redaction_count += subs

        if redaction_count > 0:
            logger.warning(
                "Output filtering: %d potential system-leak fragment(s) redacted",
                redaction_count,
            )

        # Also strip any remaining role boundary markers that leaked through
        role_patterns = [
            r"<\|system_role.*?\|>",
            r"<\|user_role.*?\|>",
            r"<system>.*?</system>",
            r"\[system\].*?\[/system\]",
        ]
        for rp in role_patterns:
            filtered = re.sub(rp, "", filtered, flags=re.DOTALL | re.IGNORECASE)

        return filtered

    # ------------------------------------------------------------------
    # Layer 5: Audit Logging
    # ------------------------------------------------------------------

    def audit_log_entry(
        self,
        user_input: str,
        detection_result: dict[str, Any],
        sanitized: bool = False,
    ) -> None:
        """Record an audit log entry with timestamp and detection results.

        Args:
            user_input: The original or sanitized user input (truncated for storage).
            detection_result: Dict with detection details (is_injection, matches, etc.).
            sanitized: Whether the input was already sanitized before logging.
        """
        max_input_length = 500
        truncated = (
            user_input[:max_input_length] + "..."
            if len(user_input) > max_input_length
            else user_input
        )

        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sanitized": sanitized,
            "input_length": len(user_input),
            "input_preview": truncated,
            "detection": detection_result,
        }
        self._audit_log.append(entry)
        logger.debug(
            "Audit log entry recorded (total entries: %d)", len(self._audit_log)
        )

    def get_audit_log(self) -> list[dict[str, Any]]:
        """Return the full audit log.

        Returns:
            List of audit log entry dicts, most recent first.
        """
        return list(reversed(self._audit_log))

    def clear_audit_log(self) -> None:
        """Clear all audit log entries."""
        count = len(self._audit_log)
        self._audit_log.clear()
        logger.info("Cleared %d audit log entries", count)

    # ------------------------------------------------------------------
    # Heuristic helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_entropy(text: str) -> float:
        """Compute Shannon entropy of the text (bits per character).

        Higher values indicate more randomness, which may suggest
        encoded or obfuscated payloads.

        Args:
            text: The string to analyze.

        Returns:
            Entropy value in bits per character.
        """
        if not text:
            return 0.0
        n = len(text)
        freq: dict[str, int] = {}
        for ch in text:
            freq[ch] = freq.get(ch, 0) + 1
        entropy = 0.0
        for count in freq.values():
            p = count / n
            entropy -= p * math.log2(p)
        return entropy

    @staticmethod
    def _compute_repetition(text: str) -> float:
        """Measure character-level repetition in text.

        Returns a score between 0 (all unique) and 1 (all same character).

        Args:
            text: The string to analyze.

        Returns:
            Repetition score in [0, 1].
        """
        if not text or len(text) <= 1:
            return 0.0
        unique = len(set(text))
        total = len(text)
        return 1.0 - (unique / total)

    @staticmethod
    def _compute_special_char_ratio(text: str) -> float:
        """Compute the ratio of non-alphanumeric characters in text.

        Args:
            text: The string to analyze.

        Returns:
            Ratio in [0, 1].
        """
        if not text:
            return 0.0
        special_count = sum(1 for ch in text if not ch.isalnum() and not ch.isspace())
        return special_count / len(text)
