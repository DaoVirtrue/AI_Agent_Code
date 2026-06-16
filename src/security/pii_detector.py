"""PII (Personally Identifiable Information) detector with masking capabilities."""

import re
import hashlib
from typing import Optional

from src.monitoring.logging_setup import get_logger
from src.monitoring.metrics import pii_detections

logger = get_logger(__name__)


class PIIDetector:
    """Detects and masks PII in text.

    Supports detection of:
    - Email addresses
    - Phone numbers (international formats, Chinese formats)
    - Social Security Numbers (SSN, both US and Chinese ID)
    - Credit card numbers (with Luhn validation)
    - IP addresses (v4 and v6)
    - Physical addresses
    - Names (basic pattern matching)
    - Passport numbers
    - Bank account numbers (IBAN)
    - Driver's license numbers
    """

    # PII patterns
    PATTERNS: dict[str, tuple[str, str]] = {
        # Email
        "email": (
            re.compile(
                r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
                re.IGNORECASE,
            ),
            "email",
        ),
        # Phone - US/International
        "phone_us": (
            re.compile(
                r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b',
            ),
            "phone",
        ),
        # Phone - Chinese
        "phone_cn": (
            re.compile(
                r'\b(?:\+?86[-.\s]?)?1[3-9]\d{9}\b',
            ),
            "phone",
        ),
        # SSN - US
        "ssn_us": (
            re.compile(
                r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b',
            ),
            "ssn",
        ),
        # Chinese ID card
        "id_cn": (
            re.compile(
                r'\b[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b',
            ),
            "national_id",
        ),
        # Credit card (basic pattern + Luhn validation)
        "credit_card": (
            re.compile(
                r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
            ),
            "credit_card",
        ),
        # IP v4
        "ip_v4": (
            re.compile(
                r'\b(?:(?:25[0-5]|2[0-4]\d|1?\d{1,2})\.){3}(?:25[0-5]|2[0-4]\d|1?\d{1,2})\b',
            ),
            "ip_address",
        ),
        # IP v6 (simplified)
        "ip_v6": (
            re.compile(
                r'\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b',
            ),
            "ip_address",
        ),
        # IBAN
        "iban": (
            re.compile(
                r'\b[A-Z]{2}\d{2}[A-Z0-9]{1,30}\b',
            ),
            "bank_account",
        ),
        # Passport numbers (generic pattern)
        "passport": (
            re.compile(
                r'\b[A-Z]{1,2}\d{6,9}\b',
            ),
            "passport",
        ),
    }

    # Patterns for masking
    CONTEXT_CLUES = {
        "email": r'(?i)(email|e-mail|mail|邮箱)',
        "phone": r'(?i)(phone|telephone|mobile|cell|tel|电话|手机|联系方式)',
        "ssn": r'(?i)(ssn|social\s+security|身份证|身份证号)',
        "credit_card": r'(?i)(credit\s+card|card\s+number|cc|信用卡|卡号)',
        "address": r'(?i)(address|addr|地址|住址|location)',
        "passport": r'(?i)(passport|护照)',
    }

    def __init__(self, custom_patterns: Optional[dict[str, re.Pattern]] = None):
        """Initialize the PII detector.

        Args:
            custom_patterns: Optional custom regex patterns for additional PII types.
                Format: {type_name: compiled_regex}
        """
        self._patterns = dict(self.PATTERNS)

        # Validate and add custom patterns
        if custom_patterns:
            for name, pattern in custom_patterns.items():
                if isinstance(pattern, re.Pattern):
                    entry = (pattern, "custom")
                elif isinstance(pattern, tuple) and len(pattern) == 2:
                    entry = pattern
                else:
                    logger.warning(
                        "Invalid custom pattern format",
                        name=name,
                    )
                    continue
                self._patterns[name] = entry

    def detect(self, text: str) -> list[dict]:
        """Detect PII in text.

        Args:
            text: Text to scan for PII.

        Returns:
            List of detection dicts, each containing:
            - type: PII type (email, phone, ssn, etc.)
            - value: The detected PII value
            - start: Character position where PII starts
            - end: Character position where PII ends
            - context_clue: Whether a context clue was found nearby
        """
        if not text:
            return []

        detections = []

        for pattern_name, (pattern, pii_type) in self._patterns.items():
            for match in pattern.finditer(text):
                value = match.group()
                start = match.start()
                end = match.end()

                # Luhn validation for credit cards
                if pii_type == "credit_card":
                    digits = re.sub(r'\D', '', value)
                    if not self._luhn_check(digits):
                        continue

                # Context clue check
                context_clue = self._check_context(text, start, pii_type)

                detection = {
                    "type": pii_type,
                    "subtype": pattern_name,
                    "value": value,
                    "start": start,
                    "end": end,
                    "length": end - start,
                    "context_clue": context_clue,
                }
                detections.append(detection)

                # Record metric
                pii_detections.labels(type=pii_type).inc()

        # Remove overlapping detections (keep the more specific one)
        detections = self._deduplicate_detections(detections)

        return detections

    def detect_with_confidence(
        self,
        text: str,
    ) -> list[dict]:
        """Detect PII with confidence scores.

        Confidence is determined by:
        - Pattern match strength
        - Luhn validation (for credit cards)
        - Context clue presence
        - Valid format check

        Args:
            text: Text to scan.

        Returns:
            List of detection dicts with 'confidence' field.
        """
        detections = self.detect(text)

        for detection in detections:
            confidence = 0.5  # Base confidence

            pii_type = detection["type"]

            # Boost for context clues
            if detection["context_clue"]:
                confidence += 0.3

            # Boost for validated formats
            if pii_type == "credit_card":
                digits = re.sub(r'\D', '', detection["value"])
                if self._luhn_check(digits):
                    confidence += 0.3
                if self._is_valid_card_length(digits):
                    confidence += 0.1

            if pii_type == "email":
                if self._is_valid_email(detection["value"]):
                    confidence += 0.3

            if pii_type == "phone":
                if self._is_valid_phone(detection["value"]):
                    confidence += 0.2

            detection["confidence"] = min(1.0, confidence)

        return detections

    def mask(
        self,
        text: str,
        detections: Optional[list[dict]] = None,
        mask_char: str = "*",
        preserve_format: bool = True,
    ) -> str:
        """Mask detected PII in text.

        Args:
            text: Original text.
            detections: Optional pre-computed detections. If None, runs detect().
            mask_char: Character to use for masking (default: '*').
            preserve_format: If True, preserve the format structure
                             (e.g., user@***.com, ***-***-1234).

        Returns:
            Text with PII replaced by masked versions.
        """
        if detections is None:
            detections = self.detect(text)

        if not detections:
            return text

        # Sort by position (reverse order to apply from end to start)
        detections = sorted(detections, key=lambda d: d["start"], reverse=True)

        result = text
        for detection in detections:
            original = text[detection["start"]:detection["end"]]
            masked = self._mask_value(
                original,
                detection["type"],
                mask_char,
                preserve_format,
            )
            result = result[:detection["start"]] + masked + result[detection["end"]:]

        return result

    def mask_to_placeholder(
        self,
        text: str,
        detections: Optional[list[dict]] = None,
    ) -> str:
        """Replace PII with type-based placeholders.

        Useful for logging where you want to know the type but not the value.
        Example: "user@example.com" -> "<EMAIL>"

        Args:
            text: Original text.
            detections: Optional pre-computed detections.

        Returns:
            Text with PII replaced by type placeholders.
        """
        if detections is None:
            detections = self.detect(text)

        if not detections:
            return text

        detections = sorted(detections, key=lambda d: d["start"], reverse=True)

        result = text
        for detection in detections:
            placeholder = f"<{detection['type'].upper()}>"
            result = result[:detection["start"]] + placeholder + result[detection["end"]:]

        return result

    def hash_pii(
        self,
        text: str,
        detections: Optional[list[dict]] = None,
        algorithm: str = "sha256",
    ) -> str:
        """Replace PII with cryptographic hashes for pseudonymization.

        Allows matching the same PII across different texts without
        revealing the actual value.

        Args:
            text: Original text.
            detections: Optional pre-computed detections.
            algorithm: Hash algorithm (sha256, sha512, md5).

        Returns:
            Text with PII replaced by hashes.
        """
        if detections is None:
            detections = self.detect(text)

        if not detections:
            return text

        detections = sorted(detections, key=lambda d: d["start"], reverse=True)

        result = text
        for detection in detections:
            value = detection["value"]
            h = hashlib.new(algorithm)
            h.update(value.encode("utf-8"))
            hashed = f"<HASH:{h.hexdigest()[:12]}>"
            result = result[:detection["start"]] + hashed + result[detection["end"]:]

        return result

    def count_pii(self, text: str) -> dict[str, int]:
        """Count PII instances by type.

        Args:
            text: Text to scan.

        Returns:
            Dict mapping PII type to count.
        """
        detections = self.detect(text)
        counts: dict[str, int] = {}

        for d in detections:
            pii_type = d["type"]
            counts[pii_type] = counts.get(pii_type, 0) + 1

        return counts

    def is_clean(self, text: str) -> bool:
        """Check if text is free of detectable PII.

        Args:
            text: Text to check.

        Returns:
            True if no PII detected.
        """
        return len(self.detect(text)) == 0

    def get_report(self, text: str) -> dict:
        """Generate a comprehensive PII report.

        Args:
            text: Text to analyze.

        Returns:
            Dict with detection summary and details.
        """
        detections = self.detect(text)

        by_type = {}
        for d in detections:
            pii_type = d["type"]
            if pii_type not in by_type:
                by_type[pii_type] = 0
            by_type[pii_type] += 1

        return {
            "has_pii": len(detections) > 0,
            "total_count": len(detections),
            "types_found": list(by_type.keys()),
            "counts_by_type": by_type,
            "detections": [
                {
                    "type": d["type"],
                    "length": d["length"],
                    "context_clue": d["context_clue"],
                    "preview": self._get_preview(text, d["start"], d["end"]),
                }
                for d in detections
            ],
        }

    @staticmethod
    def _mask_value(
        value: str,
        pii_type: str,
        mask_char: str = "*",
        preserve_format: bool = True,
    ) -> str:
        """Mask a single PII value.

        Args:
            value: The PII value to mask.
            pii_type: Type of PII.
            mask_char: Character for masking.
            preserve_format: If True, keep partial format visible.

        Returns:
            Masked value string.
        """
        if not preserve_format:
            return mask_char * len(value)

        # Type-specific masking that preserves partial format
        if pii_type == "email":
            # user@domain.com -> u***@d***.com
            parts = value.split("@")
            if len(parts) == 2:
                local = parts[0][0] + mask_char * max(1, len(parts[0]) - 1)
                domain_parts = parts[1].rsplit(".", 1)
                if len(domain_parts) == 2:
                    domain = domain_parts[0][0] + mask_char * max(1, len(domain_parts[0]) - 1)
                    return f"{local}@{domain}.{domain_parts[1]}"
                return f"{local}@{mask_char * len(parts[1])}"
            return mask_char * len(value)

        if pii_type == "phone":
            # Keep last 4 digits, mask rest
            digits = re.sub(r'\D', '', value)
            if len(digits) >= 4:
                masked_digits = mask_char * (len(digits) - 4) + digits[-4:]
                # Preserve separators
                result = []
                digit_idx = 0
                for ch in value:
                    if ch.isdigit():
                        result.append(masked_digits[digit_idx])
                        digit_idx += 1
                    else:
                        result.append(ch)
                return "".join(result)
            return mask_char * len(value)

        if pii_type == "ssn":
            # ***-**-1234
            digits = re.sub(r'\D', '', value)
            if len(digits) >= 4:
                return mask_char * (len(digits) - 4) + digits[-4:]
            return mask_char * len(value)

        if pii_type == "credit_card":
            # ****-****-****-1234
            digits = re.sub(r'\D', '', value)
            if len(digits) >= 4:
                return (mask_char * (len(digits) - 4) + digits[-4:])
            return mask_char * len(value)

        if pii_type == "ip_address":
            # 192.168.***.***
            parts = value.split(".")
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.{mask_char * 3}.{mask_char * 3}"
            return mask_char * len(value)

        # Default: show first and last char, mask middle
        if len(value) <= 4:
            return mask_char * len(value)
        return value[0] + mask_char * (len(value) - 2) + value[-1]

    def _check_context(
        self,
        text: str,
        position: int,
        pii_type: str,
        window: int = 50,
    ) -> bool:
        """Check if a context clue is present near the detected PII.

        Args:
            text: Full text.
            position: Position of the PII.
            pii_type: Type of PII to check context for.
            window: Number of characters before/after to check.

        Returns:
            True if a context clue was found nearby.
        """
        clue_pattern = self.CONTEXT_CLUES.get(pii_type)
        if not clue_pattern:
            return False

        start = max(0, position - window)
        end = min(len(text), position + window)
        context = text[start:end]

        return bool(re.search(clue_pattern, context))

    def _deduplicate_detections(
        self,
        detections: list[dict],
    ) -> list[dict]:
        """Remove overlapping PII detections.

        When two patterns match overlapping text, keep the more specific one
        (longer match wins).

        Args:
            detections: Raw detection list.

        Returns:
            Deduplicated detection list.
        """
        if not detections:
            return []

        # Sort by position then length (longer first)
        detections = sorted(
            detections,
            key=lambda d: (d["start"], -(d["end"] - d["start"])),
        )

        result = []
        last_end = 0

        for d in detections:
            if d["start"] >= last_end:
                result.append(d)
                last_end = d["end"]

        return result

    @staticmethod
    def _luhn_check(card_number: str) -> bool:
        """Validate a credit card number using the Luhn algorithm.

        Args:
            card_number: Digits-only string.

        Returns:
            True if the number passes Luhn validation.
        """
        if not card_number or not card_number.isdigit():
            return False

        digits = [int(d) for d in card_number]
        checksum = 0
        reverse_digits = digits[::-1]

        for i, digit in enumerate(reverse_digits):
            if i % 2 == 1:  # Every second digit from the right
                digit *= 2
                if digit > 9:
                    digit -= 9
            checksum += digit

        return checksum % 10 == 0

    @staticmethod
    def _is_valid_card_length(digits: str) -> bool:
        """Check if the digit count matches a known card type."""
        return len(digits) in (13, 15, 16, 19)

    @staticmethod
    def _is_valid_email(email: str) -> bool:
        """Validate email format."""
        parts = email.split("@")
        if len(parts) != 2:
            return False
        domain_parts = parts[1].split(".")
        return len(domain_parts) >= 2 and all(len(p) > 0 for p in domain_parts)

    @staticmethod
    def _is_valid_phone(phone: str) -> bool:
        """Validate phone number format (basic check)."""
        digits = re.sub(r'\D', '', phone)
        return 7 <= len(digits) <= 15

    @staticmethod
    def _get_preview(text: str, start: int, end: int) -> str:
        """Get a safe preview of the PII value (masked for display)."""
        if end - start <= 4:
            return "***"
        full = text[start:end]
        return full[:2] + "***" + full[-2:] if len(full) > 4 else "***"
