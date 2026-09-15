"""Quality verification module for RAG-generated answers.

Provides fact verification, source attribution analysis, hallucination
detection, and ensemble answer voting to improve RAG output quality.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .fact_verifier import FactVerifier
from .source_attribution import SourceAttribution
from .hallucination_detect import HallucinationDetector
from .answer_voting import AnswerVoting


@dataclass
class VerificationResult:
    """Result of fact verification."""
    claim: str
    is_supported: bool
    evidence: str = ""
    confidence: float = 0.0
    source_id: str = ""


@dataclass
class AttributionResult:
    """Result of source attribution analysis."""
    statement: str
    source_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0
    is_attributed: bool = False


@dataclass
class HallucinationReport:
    """Report of hallucination detection."""
    has_hallucinations: bool
    risk_score: float = 0.0
    suspicious_spans: list[dict[str, Any]] = field(default_factory=list)
    overall_confidence: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class VoteResult:
    """Result of answer voting across multiple generations."""
    winning_answer: str
    vote_counts: dict[str, int] = field(default_factory=dict)
    confidence: float = 0.0
    consensus_reached: bool = False
    all_answers: list[dict[str, Any]] = field(default_factory=list)


__all__ = [
    "FactVerifier",
    "SourceAttribution",
    "HallucinationDetector",
    "AnswerVoting",
    "VerificationResult",
    "AttributionResult",
    "HallucinationReport",
    "VoteResult",
]
