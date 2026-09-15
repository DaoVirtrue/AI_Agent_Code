"""Independent verifier for agent outputs.

Key design principle from the architecture doc (section 2.3): **the Verifier
must NOT be an LLM self-assessment.** A sub-agent deceiving the main
orchestrator is a real attack surface; verification must be done by a
separate, deterministic service.

This module provides:

- ``Verifier`` — the abstract contract.
- ``SchemaVerifier`` — validates that the output conforms to a JSON schema
  or required structure (deterministic, no LLM).
- ``ContainsVerifier`` — validates the output contains required keywords /
  answers a specific question.
- ``VerificationResult`` — pass/fail + reason.
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Result of a verification pass."""

    passed: bool
    reason: str = ""
    details: dict = field(default_factory=dict)


class Verifier(ABC):
    """Abstract contract for an independent output verifier."""

    @abstractmethod
    def verify(self, output: Any, context: Optional[dict] = None) -> VerificationResult:
        """Verify an agent output against an independent criterion."""


class SchemaVerifier(Verifier):
    """Deterministic schema verification (no LLM involved).

    Validates that an output (a dict or JSON string) contains the required
    keys with the required types.
    """

    def __init__(self, required_keys: list[str]):
        self.required_keys = required_keys

    def verify(self, output: Any, context: Optional[dict] = None) -> VerificationResult:
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except json.JSONDecodeError:
                return VerificationResult(False, "output is not valid JSON")

        if not isinstance(output, dict):
            return VerificationResult(False, f"expected dict, got {type(output).__name__}")

        missing = [k for k in self.required_keys if k not in output]
        if missing:
            return VerificationResult(
                False, f"missing required keys: {missing}", {"missing": missing}
            )
        return VerificationResult(True, "schema valid", {"required_keys": self.required_keys})


class ContainsVerifier(Verifier):
    """Deterministic keyword / regex presence check."""

    def __init__(self, required_terms: list[str]):
        self.required_terms = required_terms

    def verify(self, output: Any, context: Optional[dict] = None) -> VerificationResult:
        text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
        text_lower = text.lower()

        missing = [t for t in self.required_terms if t.lower() not in text_lower]
        if missing:
            return VerificationResult(False, f"missing required terms: {missing}", {"missing": missing})
        return VerificationResult(True, "contains all required terms")


class CompositeVerifier(Verifier):
    """Combines multiple verifiers with AND semantics."""

    def __init__(self, verifiers: list[Verifier]):
        self.verifiers = verifiers

    def verify(self, output: Any, context: Optional[dict] = None) -> VerificationResult:
        for v in self.verifiers:
            result = v.verify(output, context)
            if not result.passed:
                return result
        return VerificationResult(True, "all verifiers passed")
