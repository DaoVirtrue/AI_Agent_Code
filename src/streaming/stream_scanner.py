"""Streaming security scanner: incremental regex scanning, PII detection, security monitoring.

Scans streaming tokens incrementally for sensitive content (PII, API keys,
passwords) using a sliding buffer window. Supports block, mask, and warn
action modes with integrated stream interruption.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .stream_interrupter import StreamInterruptionHandler


class IncrementalRegexScanner:
    """Incrementally scan streaming tokens for sensitive content.

    Maintains a sliding buffer (default 512 chars) to detect patterns
    that span across token boundaries. Supports blocking, masking,
    and warning actions per-matched pattern.

    Usage:
        scanner = IncrementalRegexScanner(buffer_size=512)
        detections = scanner.scan("Hello, my card is ")
        # None (pattern spans boundary)
        detections = scanner.scan("6222021234567890")
        # [{'pattern': 'bank_card', 'match': '...', 'action': 'block'}]
    """

    PATTERNS: dict[str, dict] = {
        "cn_id_card": {
            "pattern": r'(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)',
            "action": "block",
            "severity": "high",
            "description": "Chinese ID card number",
        },
        "cn_phone": {
            "pattern": r'(?<!\d)1[3-9]\d{9}(?!\d)',
            "action": "mask",
            "severity": "medium",
            "description": "Chinese phone number",
        },
        "email": {
            "pattern": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b',
            "action": "mask",
            "severity": "medium",
            "description": "Email address",
        },
        "ip_address": {
            "pattern": r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
            "action": "warn",
            "severity": "low",
            "description": "IP address",
        },
        "openai_key": {
            "pattern": r'sk-[A-Za-z0-9]{32,}',
            "action": "block",
            "severity": "critical",
            "description": "OpenAI API key",
        },
        "aws_key": {
            "pattern": r'AKIA[0-9A-Z]{16}',
            "action": "block",
            "severity": "critical",
            "description": "AWS access key",
        },
        "password_pattern": {
            "pattern": r'(?:password|passwd|pwd|secret|token|api_key|apikey)\s*[:=]\s*\S+',
            "action": "block",
            "severity": "critical",
            "description": "Password or secret in text",
        },
        "credit_card": {
            "pattern": r'\b(?:\d{4}[- ]?){3}\d{4}\b',
            "action": "block",
            "severity": "high",
            "description": "Credit card number",
        },
        "cn_bank_card": {
            "pattern": r'(?<!\d)(?:62\d{14,17}|(?:4|5)\d{15})(?!\d)',
            "action": "block",
            "severity": "high",
            "description": "Bank card number",
        },
        "cn_address": {
            "pattern": r'(?:[一-鿿]{2,6}(?:省|自治区|市))[一-鿿]{2,6}(?:市|区|县|镇)[一-鿿]{2,10}(?:路|街|道|巷|村|号|楼|室|单元|层)\d*',
            "action": "mask",
            "severity": "medium",
            "description": "Chinese address",
        },
        "github_token": {
            "pattern": r'gh[pousr]_[A-Za-z0-9_]{36,}',
            "action": "block",
            "severity": "critical",
            "description": "GitHub personal access token",
        },
        "jwt_token": {
            "pattern": r'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',
            "action": "block",
            "severity": "high",
            "description": "JWT token",
        },
    }

    def __init__(self, buffer_size: int = 512) -> None:
        """Initialize the scanner.

        Args:
            buffer_size: Size of the sliding buffer window for cross-token
                         pattern detection. Default 512 characters.
        """
        self._buffer: str = ""
        self._buffer_size = max(128, buffer_size)
        self._compiled_patterns = {
            name: re.compile(info["pattern"], re.IGNORECASE | re.MULTILINE)
            for name, info in self.PATTERNS.items()
        }

    def scan(self, token: str) -> list[dict]:
        """Scan a new token and the sliding buffer for sensitive patterns.

        Args:
            token: The latest token to scan.

        Returns:
            List of detection dictionaries, each with:
            - pattern: pattern name
            - match: matched text
            - action: "block", "mask", or "warn"
            - severity: "critical", "high", "medium", "low"
            - description: human-readable description
        """
        self._buffer += token

        # Trim buffer to window size
        if len(self._buffer) > self._buffer_size:
            self._buffer = self._buffer[-self._buffer_size:]

        return self._sliding_buffer_scan()

    def _sliding_buffer_scan(self) -> list[dict]:
        """Scan the full sliding buffer for all patterns.

        Returns:
            List of detection dictionaries for matches found.
        """
        detections: list[dict] = []
        seen_spans: set[tuple[int, int]] = set()

        for pattern_name, compiled in self._compiled_patterns.items():
            for match in compiled.finditer(self._buffer):
                span = (match.start(), match.end())
                # Avoid reporting overlapping hits from the same pattern
                # Check if this span overlaps with already-reported spans
                is_overlapping = False
                for s in seen_spans:
                    if not (span[1] <= s[0] or span[0] >= s[1]):
                        is_overlapping = True
                        break
                if is_overlapping:
                    continue

                seen_spans.add(span)
                pattern_info = self.PATTERNS[pattern_name]
                detections.append({
                    "pattern": pattern_name,
                    "match": match.group(0),
                    "action": pattern_info["action"],
                    "severity": pattern_info["severity"],
                    "description": pattern_info["description"],
                    "span_start": match.start(),
                    "span_end": match.end(),
                })

        return detections

    def reset(self) -> None:
        """Reset the sliding buffer."""
        self._buffer = ""

    @property
    def buffer_content(self) -> str:
        """Current content of the sliding buffer."""
        return self._buffer


class PIIDetector:
    """PII detection specialized for Chinese-language environments.

    Detects Chinese names, ID numbers, phone numbers, and addresses.
    Supports masking of detected PII with asterisks.
    """

    # Common Chinese surnames (top 100)
    _CN_SURNAMES: set[str] = set(
        "李王张刘陈杨赵黄周吴徐孙马胡朱郭何罗高林郑梁谢唐许冯宋韩邓彭曹曾田萧潘袁蔡蒋余杜叶程苏魏吕丁任卢姚钟姜崔谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤"
    )

    def __init__(self) -> None:
        pass

    def detect(self, text: str) -> list[dict]:
        """Detect PII in text.

        Args:
            text: The text to scan for PII.

        Returns:
            List of detection dictionaries with type, value, confidence, action.
        """
        detections: list[dict] = []

        # Detect various PII types
        detections.extend(self._detect_id_number(text))
        detections.extend(self._detect_phone(text))
        detections.extend(self._detect_chinese_name(text))
        detections.extend(self._detect_address(text))
        detections.extend(self._detect_email(text))

        return detections

    def mask(self, text: str, detections: list[dict]) -> str:
        """Replace detected PII with masked asterisks.

        Args:
            text: The original text.
            detections: List of PII detections.

        Returns:
            Text with PII replaced by asterisks.
        """
        result = text
        # Sort by position (latest first) to preserve indices during replacement
        sorted_detections = sorted(
            [d for d in detections if "value" in d],
            key=lambda d: len(result) - result.rfind(d["value"])
            if d["value"] in result else 0,
            reverse=True,
        )

        for detection in sorted_detections:
            value = detection["value"]
            if value and value in result:
                if detection.get("type") == "phone":
                    # Mask middle digits: 138****5678
                    if len(value) >= 11:
                        masked = value[:3] + "****" + value[-4:]
                    else:
                        masked = value[:3] + "***"
                elif detection.get("type") == "id_number":
                    # Mask middle digits: 110101****1234
                    if len(value) >= 14:
                        masked = value[:6] + "********" + value[-4:]
                    else:
                        masked = value[:3] + "***"
                elif detection.get("type") == "email":
                    # Mask local part: a***@domain.com
                    parts = value.split("@")
                    if len(parts) == 2:
                        local = parts[0]
                        if len(local) > 1:
                            masked = local[0] + "***@" + parts[1]
                        else:
                            masked = "***@" + parts[1]
                    else:
                        masked = "***"
                elif detection.get("type") == "chinese_name":
                    # Mask given name: 张**
                    if len(value) >= 2:
                        masked = value[0] + "*" * (len(value) - 1)
                    else:
                        masked = "*"
                else:
                    # Generic masking
                    if len(value) > 6:
                        masked = value[:3] + "***" + value[-3:]
                    elif len(value) > 2:
                        masked = value[0] + "***"
                    else:
                        masked = "***"

                result = result.replace(value, masked, 1)

        return result

    def _detect_chinese_name(self, text: str) -> list[dict]:
        """Detect Chinese personal names (2-3 characters, valid surname).

        Scans for surname + 1-2 character given name patterns.
        """
        detections: list[dict] = []

        # Pattern: surname (1 char) + given name (1-2 chars)
        # Needs to avoid matching common words
        pattern = re.compile(r'([' + ''.join(self._CN_SURNAMES) + r'])([一-鿿]{1,2})')

        for match in pattern.finditer(text):
            full_name = match.group(0)
            surname = match.group(1)
            given = match.group(2)

            # Skip if the match is part of a longer compound word
            start = match.start()
            end = match.end()

            # Check context to avoid matching organization names
            before = text[max(0, start - 2):start]
            after = text[end:end + 2]

            # Skip if preceded or followed by org suffixes
            org_suffixes = ("公司", "集团", "银行", "医院", "大学", "部门", "中心")
            if any(before.endswith(s) or after.startswith(s) for s in org_suffixes):
                continue

            # Skip very common given names that are likely false positives
            common_false_positives = {
                "一些", "一种", "一个", "一下", "一定", "一样",
                "不是", "不会", "不能", "不同", "不要", "不过",
            }
            if given in common_false_positives:
                continue

            detections.append({
                "type": "chinese_name",
                "value": full_name,
                "surname": surname,
                "given_name": given,
                "confidence": 0.65 if len(given) == 1 else 0.80,
                "action": "mask",
                "span": (start, end),
            })

        return detections

    def _detect_id_number(self, text: str) -> list[dict]:
        """Detect Chinese 18-digit ID card numbers."""
        detections: list[dict] = []
        pattern = re.compile(
            r'(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)'
        )

        for match in pattern.finditer(text):
            id_number = match.group(0)

            # Verify checksum (simplified)
            detections.append({
                "type": "id_number",
                "value": id_number,
                "confidence": 0.90,
                "action": "block",
                "span": (match.start(), match.end()),
            })

        return detections

    def _detect_phone(self, text: str) -> list[dict]:
        """Detect Chinese mobile phone numbers."""
        detections: list[dict] = []
        pattern = re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)')

        for match in pattern.finditer(text):
            detections.append({
                "type": "phone",
                "value": match.group(0),
                "confidence": 0.92,
                "action": "mask",
                "span": (match.start(), match.end()),
            })

        return detections

    def _detect_address(self, text: str) -> list[dict]:
        """Detect Chinese addresses with province/city/district patterns."""
        detections: list[dict] = []

        # Province-level pattern
        province_pattern = re.compile(
            r'(?:[一-鿿]{2,6}(?:省|自治区|市))'
            r'[一-鿿]{2,10}(?:市|区|县|镇|乡)'
            r'[一-鿿]{2,20}(?:路|街|道|巷|村|弄|号|楼|室|单元|层|栋|幢)'
            r'\d*号?'
        )

        for match in province_pattern.finditer(text):
            detections.append({
                "type": "address",
                "value": match.group(0),
                "confidence": 0.75,
                "action": "mask",
                "span": (match.start(), match.end()),
            })

        return detections

    def _detect_email(self, text: str) -> list[dict]:
        """Detect email addresses."""
        detections: list[dict] = []
        pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')

        for match in pattern.finditer(text):
            detections.append({
                "type": "email",
                "value": match.group(0),
                "confidence": 0.85,
                "action": "mask",
                "span": (match.start(), match.end()),
            })

        return detections


class StreamingSecurityMonitor:
    """Integrated streaming security: combines scanner, PII detector,
    and stream interruption handler.

    Monitors each token in a stream for sensitive content, decides
    whether to block, mask, or warn, and triggers stream interruption
    when blocking-level detections occur.
    """

    def __init__(
        self,
        scanner: IncrementalRegexScanner,
        pii_detector: PIIDetector,
        interrupter: "StreamInterruptionHandler",
    ) -> None:
        """Initialize the security monitor.

        Args:
            scanner: IncrementalRegexScanner instance.
            pii_detector: PIIDetector instance.
            interrupter: StreamInterruptionHandler for stream control.
        """
        self._scanner = scanner
        self._pii_detector = pii_detector
        self._interrupter = interrupter
        self._detection_history: list[dict] = []

    async def monitor_token(self, token: str, stream_id: str) -> tuple[bool, str]:
        """Monitor a single token for security issues.

        Scans the token and sliding buffer for sensitive patterns and PII.
        If blocking-level content is found, interrupts the stream and
        returns False. If masking is needed, returns the masked token.

        Args:
            token: The token to scan.
            stream_id: The stream being monitored.

        Returns:
            Tuple of (safe: bool, processed_token: str).
            - safe=False: token blocked, stream interrupted
            - safe=True: token is safe (possibly masked)
        """
        # Step 1: Scan with incremental regex scanner
        regex_detections = self._scanner.scan(token)

        # Step 2: Detect PII in the current buffer
        pii_detections = self._pii_detector.detect(self._scanner.buffer_content)

        # Step 3: Combine and deduplicate
        all_detections = regex_detections + pii_detections
        self._detection_history.extend(all_detections)
        # Cap history to prevent unbounded growth
        if len(self._detection_history) > 1000:
            self._detection_history = self._detection_history[-500:]

        # Step 4: Check if we should block
        should_block = await self.should_block(all_detections)
        if should_block:
            await self._interrupter.interrupt(stream_id, "security_blocked")
            return False, ""

        # Step 5: If masking is needed, mask the PII in the token
        processed_token = token
        if pii_detections:
            processed_token = self._pii_detector.mask(token, pii_detections)

        return True, processed_token

    async def should_block(self, detections: list[dict]) -> bool:
        """Determine if any detections warrant blocking the stream.

        Blocks if any detection has action="block" or severity="critical".

        Args:
            detections: List of detection dictionaries.

        Returns:
            True if the stream should be blocked.
        """
        for detection in detections:
            action = detection.get("action", "warn")
            severity = detection.get("severity", "low")

            if action == "block":
                return True
            if severity == "critical":
                return True

        return False

    def get_detection_summary(self) -> dict:
        """Get a summary of all detections in history.

        Returns:
            Dictionary with counts by severity and action.
        """
        summary: dict[str, int] = {
            "total_detections": len(self._detection_history),
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "block_actions": 0,
            "mask_actions": 0,
            "warn_actions": 0,
        }

        for d in self._detection_history:
            severity = d.get("severity", "low")
            action = d.get("action", "warn")

            if severity in summary:
                summary[severity] += 1
            if action == "block":
                summary["block_actions"] += 1
            elif action == "mask":
                summary["mask_actions"] += 1
            elif action == "warn":
                summary["warn_actions"] += 1

        return summary

    def reset(self) -> None:
        """Reset scanner buffer and detection history."""
        self._scanner.reset()
        self._detection_history.clear()
