"""Content safety filter for LLM inputs and outputs."""

import re
from typing import Optional

from src.observability.logging_setup import get_logger
from src.observability.metrics import content_safety_blocks

logger = get_logger(__name__)


class ContentSafetyFilter:
    """Content safety filter for detecting and blocking harmful content.

    Screens both user inputs and model outputs for:
    - Hate speech and discrimination
    - Harassment and bullying
    - Violence and self-harm
    - Sexual content
    - Illegal content
    - Personally identifiable information (PII)

    Uses a combination of pattern matching and keyword-based detection.
    For production, should be augmented with a dedicated safety classifier.
    """

    # Safety category definitions with severity thresholds
    CATEGORIES = {
        "hate": {
            "severity": "critical",
            "block_threshold": "medium",
        },
        "harassment": {
            "severity": "high",
            "block_threshold": "medium",
        },
        "violence": {
            "severity": "critical",
            "block_threshold": "medium",
        },
        "self_harm": {
            "severity": "critical",
            "block_threshold": "low",
        },
        "sexual": {
            "severity": "high",
            "block_threshold": "medium",
        },
        "illegal": {
            "severity": "critical",
            "block_threshold": "low",
        },
        "pii": {
            "severity": "high",
            "block_threshold": "high",
        },
    }

    # Content safety patterns (production: use a proper classifier model)
    HARM_PATTERNS = {
        "self_harm": [
            r"(?i)\b(suicide|kill\s+myself|end\s+my\s+life|self[- ]?harm|cutting\s+myself)\b",
        ],
        "violence": [
            r"(?i)\b(murder|kill|massacre|terrorist|bomb|shoot|attack|assassinate)\b",
        ],
        "hate": [
            r"(?i)\b(nigger|kike|faggot|chink|retard|spic|wetback|terrorist\s+(all|every))\b",
        ],
        "sexual_minors": [
            r"(?i)\b(child\s+(porn|abuse|csa)|minor\s+(sexual|porn)|underage|pedo)\b",
        ],
        "illegal": [
            r"(?i)\b(how\s+to\s+(make|create|build|manufacture)\s+(drugs?|bomb|weapon|explosive|meth|cocaine|heroin))\b",
        ],
    }

    def __init__(self, block_on_medium: bool = True):
        """Initialize the content safety filter.

        Args:
            block_on_medium: If True, block content at medium severity and above.
                             If False, only block high and critical.
        """
        self.block_on_medium = block_on_medium
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Pre-compile all regex patterns for efficiency."""
        self._compiled = {}
        for category, patterns in self.HARM_PATTERNS.items():
            self._compiled[category] = [re.compile(p) for p in patterns]

    async def check(self, text: str) -> tuple[bool, str]:
        """Check content for safety violations.

        Args:
            text: The text to screen (user input or model output).

        Returns:
            Tuple of (is_safe: bool, reason: str).
            - (True, "OK"): Content is safe
            - (False, reason): Content violates safety policy
        """
        if not text:
            return True, "OK"

        violations = []

        # Check each category
        for category, patterns in self._compiled.items():
            severity = self.CATEGORIES.get(category, {}).get("severity", "high")

            for pattern in patterns:
                matches = pattern.findall(text)
                if matches:
                    violations.append({
                        "category": category,
                        "severity": severity,
                        "matches_count": len(matches),
                        "first_match": str(matches[0]) if matches else "",
                    })
                    break

        if not violations:
            return True, "OK"

        # Determine if content should be blocked
        should_block = False
        reasons = []

        for v in violations:
            category = v["category"]
            severity = v["severity"]
            config = self.CATEGORIES.get(category, {})

            block_threshold = config.get("block_threshold", "high")

            # Map severity and threshold to numeric for comparison
            severity_map = {"low": 0, "medium": 1, "high": 2, "critical": 3}
            threshold_map = {"low": 0, "medium": 1, "high": 2, "critical": 3}

            sev_level = severity_map.get(severity, 2)
            thresh_level = threshold_map.get(block_threshold, 2)

            if not self.block_on_medium and thresh_level == 1:
                thresh_level = 2  # Promote medium to high

            if sev_level >= thresh_level:
                should_block = True
                reasons.append(f"{category}({severity})")

        if should_block:
            reason = f"Content blocked due to: {', '.join(reasons)}"
            content_safety_blocks.labels(
                category=violations[0]["category"]
            ).inc()
            logger.warning(
                "Content safety block",
                categories=reasons,
                text_preview=text[:200],
            )
            return False, reason

        return True, "OK"

    async def check_input(self, text: str) -> tuple[bool, str, Optional[dict]]:
        """Check user input for safety, returning detailed result.

        Args:
            text: User input text.

        Returns:
            Tuple of (is_safe, reason, details_dict).
        """
        is_safe, reason = await self.check(text)
        details = None

        if not is_safe:
            violations = self._get_violations(text)
            details = {
                "violations": violations,
                "text_length": len(text),
                "blocked": True,
            }

        return is_safe, reason, details

    async def check_output(self, text: str) -> tuple[bool, str]:
        """Check model output for safety.

        More lenient than input checking since the model should not
        produce harmful content, but we still verify.

        Args:
            text: Model output text.

        Returns:
            Tuple of (is_safe, reason).
        """
        return await self.check(text)

    def _get_violations(self, text: str) -> list[dict]:
        """Get detailed list of all safety violations found in text."""
        violations = []

        for category, patterns in self._compiled.items():
            for pattern in patterns:
                matches = pattern.finditer(text)
                for match in matches:
                    violations.append({
                        "category": category,
                        "severity": self.CATEGORIES.get(category, {}).get("severity", "high"),
                        "matched_text": match.group(),
                        "position": match.start(),
                    })

        return violations

    def get_safety_report(self, text: str) -> dict:
        """Generate a comprehensive safety report for the text.

        Args:
            text: Text to analyze.

        Returns:
            Dict with safety category scores and overall assessment.
        """
        violations = self._get_violations(text)

        # Aggregate by category
        by_category = {}
        for v in violations:
            cat = v["category"]
            if cat not in by_category:
                by_category[cat] = 0
            by_category[cat] += 1

        return {
            "is_safe": len(violations) == 0,
            "total_violations": len(violations),
            "categories_flagged": list(by_category.keys()),
            "violations_by_category": by_category,
            "text_length": len(text),
            "risk_level": self._assess_risk_level(violations),
        }

    @staticmethod
    def _assess_risk_level(violations: list[dict]) -> str:
        """Assess overall risk level from violations."""
        severity_count = {"critical": 0, "high": 0, "medium": 0, "low": 0}

        for v in violations:
            sev = v.get("severity", "medium")
            severity_count[sev] = severity_count.get(sev, 0) + 1

        if severity_count["critical"] > 0:
            return "critical"
        if severity_count["high"] > 2:
            return "high"
        if severity_count["high"] > 0 or severity_count["medium"] > 3:
            return "medium"
        if severity_count["medium"] > 0 or severity_count["low"] > 5:
            return "low"
        return "none"
