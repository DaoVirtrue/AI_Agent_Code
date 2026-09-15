"""Five-layer prompt injection defense system."""

import re
from typing import Optional

from src.observability.logging_setup import get_logger
from src.observability.metrics import injection_attempts

logger = get_logger(__name__)


class InjectionDefense:
    """Five-layer defense against prompt injection attacks.

    Layer 1: Input Sanitization - Remove/strip dangerous characters and patterns
    Layer 2: Pattern Detection - Identify known injection attack patterns
    Layer 3: Role Boundary Enforcement - Add delimiters between user and system content
    Layer 4: Semantic Analysis - LLM-based detection of subtle injection attempts
    Layer 5: Output Filtering - Sanitize model outputs for leaked system prompts
    """

    # Known injection patterns
    INJECTION_PATTERNS = [
        # Instruction override
        (r"(?i)(ignore|forget|disregard)\s+(all\s+)?(previous|above|prior|earlier)\s+(instructions?|prompts?|rules?|guidelines?)", "instruction_override", "high"),
        (r"(?i)you\s+are\s+now\s+(a\s+)?(DAN|jailbreak|evil|unrestricted|unfiltered)", "roleplay_override", "critical"),
        (r"(?i)(pretend|imagine|act\s+as\s+if)\s+you\s+(are|were)\s+(not|no\s+longer)", "impersonation", "high"),
        # System prompt extraction
        (r"(?i)(tell|show|reveal|output|print|display|repeat|write)\s+(me\s+)?(your\s+)?(system\s+)?(prompt|instructions?|rules?|guidelines?|policy)", "prompt_extraction", "high"),
        (r"(?i)(what|repeat|echo)\s+(is\s+)?(the\s+)?(beginning|start|first)\s+(of\s+)?(your\s+)?(instructions?|prompt)", "prompt_extraction", "high"),
        (r"(?i)(your\s+)?(system\s+)?(prompt|instructions?)\s+(is|are|was|were)", "prompt_extraction", "medium"),
        # Context manipulation
        (r"(?i)(this\s+is\s+)?(urgent|emergency|critical).*(override|bypass|skip)", "urgency_exploit", "medium"),
        (r"(?i)(admin|administrator|root|superuser|developer\s+mode).*(command|access|override|mode)", "authority_claim", "high"),
        # Token/Session attacks
        (r"(?i)(leak|expose|reveal)\s+(the\s+)?(token|api.key|secret|password|credential)", "credential_leak", "critical"),
        (r"(?i)\b[A-Za-z0-9+/]{40,}={0,2}\b", "token_pattern", "low"),
        # Encoded injection
        (r"(?i)(base64|hex|rot13|decode|decrypt|deobfuscate)\s+(this|the|following)", "encoded_command", "medium"),
        # Separation attacks
        (r"\n{3,}(system|user|assistant):", "separation_attack", "medium"),
        (r"(?i)<<<(\s*END\s*)?SYSTEM(\s*END\s*)?>>>", "delimiter_attack", "medium"),
        # Multi-language attacks
        (r"(?i)(忽略|忘记|无视|删除)\s*(所有|之前的|上面的|前面的)?\s*(指令|提示|规则|准则|要求)", "chinese_injection", "high"),
        (r"(?i)(请|现在|立刻).*(泄露|暴露|显示|输出|说出).*(系统|提示|指令|规则)", "chinese_extraction", "high"),
    ]

    # Role boundary markers
    ROLE_BOUNDARIES = {
        "system": '<|SYSTEM_START|>\n{}\n<|SYSTEM_END|>',
        "user": '<|USER_START|>\n{}\n<|USER_END|>',
        "assistant": '<|ASSISTANT_START|>\n{}\n<|ASSISTANT_END|>',
    }

    def __init__(self, enable_semantic_analysis: bool = False):
        """Initialize the injection defense system.

        Args:
            enable_semantic_analysis: If True, use LLM for Layer 4 semantic analysis.
        """
        self.enable_semantic_analysis = enable_semantic_analysis
        self._compiled_patterns = [
            (re.compile(pattern), attack_type, severity)
            for pattern, attack_type, severity in self.INJECTION_PATTERNS
        ]

    def sanitize_input(self, text: str) -> str:
        """Layer 1: Sanitize user input.

        Removes or neutralizes:
        - Null bytes
        - Excessive whitespace
        - Unicode control characters
        - HTML/XML tags (optionally)
        - System message separators

        Args:
            text: Raw user input text.

        Returns:
            Sanitized text string.
        """
        if not text:
            return ""

        # Remove null bytes
        text = text.replace('\x00', '')

        # Remove Unicode control characters (except common whitespace)
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)

        # Normalize excessive whitespace
        text = re.sub(r'\n{4,}', '\n\n\n', text)  # Max 3 consecutive newlines
        text = re.sub(r' {3,}', '  ', text)       # Max 2 consecutive spaces

        # Strip leading/trailing whitespace
        text = text.strip()

        # Remove system message separators that could be used for injection
        separators = [
            '<|SYSTEM_START|>', '<|SYSTEM_END|>',
            '<|USER_START|>', '<|USER_END|>',
            '<|ASSISTANT_START|>', '<|ASSISTANT_END|>',
            '<<<SYSTEM>>>', '<<<USER>>>',
        ]
        for sep in separators:
            text = text.replace(sep, '')

        return text

    def detect_attempt(self, text: str) -> dict:
        """Layer 2: Detect prompt injection attempts.

        Scans the input for known injection patterns and returns
        a structured detection result.

        Args:
            text: User input text to scan.

        Returns:
            Dict with detection results:
            - is_attack: bool
            - patterns_found: list of matched pattern names
            - severity: highest severity level found
            - matches: list of (pattern, match_text) tuples
        """
        if not text:
            return {
                "is_attack": False,
                "patterns_found": [],
                "severity": "none",
                "matches": [],
            }

        patterns_found = []
        matches = []
        max_severity = "none"

        severity_rank = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

        for pattern, attack_type, severity in self._compiled_patterns:
            found = pattern.findall(text)
            if found:
                if attack_type not in patterns_found:
                    patterns_found.append(attack_type)
                if isinstance(found[0], tuple):
                    matches.append((attack_type, " | ".join(str(f) for f in found[0])))
                else:
                    matches.append((attack_type, str(found[0])))
                if severity_rank.get(severity, 0) > severity_rank.get(max_severity, 0):
                    max_severity = severity

        is_attack = len(patterns_found) > 0 and max_severity in ("high", "critical")

        if is_attack:
            injection_attempts.labels(severity=max_severity).inc()
            logger.warning(
                "Injection attempt detected",
                severity=max_severity,
                patterns=patterns_found,
                text_preview=text[:200],
            )

        return {
            "is_attack": is_attack,
            "patterns_found": patterns_found,
            "severity": max_severity,
            "matches": matches,
        }

    def add_role_boundaries(self, prompt: str) -> str:
        """Layer 3: Add role boundary markers between system/user content.

        Wraps content in explicit role markers to prevent the user from
        impersonating the system or assistant roles.

        Args:
            prompt: The complete prompt to add boundaries to.

        Returns:
            Prompt with role boundary markers added.
        """
        # Detect existing roles in the prompt
        lines = prompt.split('\n')
        result_lines = []

        current_role = None
        current_content = []

        for line in lines:
            role_match = re.match(
                r'^(system|user|assistant)\s*:\s*(.*)',
                line,
                re.IGNORECASE,
            )
            if role_match:
                # Flush previous role
                if current_role and current_content:
                    boundary = self.ROLE_BOUNDARIES.get(
                        current_role, '<|{}|>\n{{}}\n<|/{}|>'.format(current_role.upper(), current_role.upper())
                    )
                    result_lines.append(boundary.format('\n'.join(current_content)))

                current_role = role_match.group(1).lower()
                current_content = [role_match.group(2)]
            else:
                if current_role is None:
                    current_role = "user"
                current_content.append(line)

        # Flush final role
        if current_role and current_content:
            boundary = self.ROLE_BOUNDARIES.get(
                current_role, '<|{}|>\n{{}}\n<|/{}|>'.format(current_role.upper(), current_role.upper())
            )
            result_lines.append(boundary.format('\n'.join(current_content)))

        return '\n\n'.join(result_lines)

    def filter_output(self, text: str) -> str:
        """Layer 5: Sanitize model outputs.

        Detects and removes:
        - Leaked system prompts
        - Role boundary markers
        - Sensitive information patterns in output

        Args:
            text: Model output text.

        Returns:
            Filtered output text.
        """
        if not text:
            return ""

        # Remove any role boundary markers the model might output
        for key, template in self.ROLE_BOUNDARIES.items():
            start = template.split('\n')[0]
            end = template.split('\n')[-1]
            text = text.replace(start, '').replace(end, '')

        # Remove system prompt patterns
        system_prompt_indicators = [
            r'(?i)you\s+are\s+a\s+(helpful\s+)?(AI\s+)?assistant',
            r'(?i)your\s+primary\s+(goal|objective|function)\s+is',
            r'(?i)always\s+(respond|answer|reply)\s+(in|with|using)',
        ]
        for pattern in system_prompt_indicators:
            text = re.sub(pattern, '[filtered]', text)

        return text.strip()

    async def semantic_analysis(self, text: str) -> dict:
        """Layer 4: LLM-based semantic analysis for subtle injection attempts.

        Uses an LLM to detect injection attempts that bypass pattern matching,
        including:
        - Social engineering in prompts
        - Persuasion tactics
        - Logic traps
        - Multi-turn manipulation setups

        Args:
            text: User input text to analyze.

        Returns:
            Dict with semantic analysis results.
        """
        if not self.enable_semantic_analysis:
            return {"suspicious": False, "score": 0.0}

        # This would call an LLM for semantic analysis
        # For now, return a sensible default
        detection_result = self.detect_attempt(text)
        if detection_result["severity"] in ("medium", "high", "critical"):
            return {"suspicious": True, "score": 0.9}
        return {"suspicious": False, "score": 0.1}

    def full_defense(self, user_input: str) -> dict:
        """Run all defense layers against user input.

        Returns a comprehensive defense report.

        Args:
            user_input: Raw user input text.

        Returns:
            Dict with sanitized text and detection results.
        """
        # Layer 1: Sanitize
        sanitized = self.sanitize_input(user_input)

        # Layer 2: Pattern detection
        detection = self.detect_attempt(sanitized)

        # Layer 3: Add role boundaries
        bounded = self.add_role_boundaries(sanitized) if not detection["is_attack"] else sanitized

        # Layer 5: Pre-filter (output filtering applied after generation)

        return {
            "original": user_input[:500],
            "sanitized": sanitized,
            "bounded": bounded,
            "is_attack": detection["is_attack"],
            "severity": detection["severity"],
            "patterns_found": detection["patterns_found"],
            "matches_count": len(detection["matches"]),
            "should_block": detection["severity"] in ("critical",),
            "should_flag": detection["severity"] in ("high", "critical"),
        }
