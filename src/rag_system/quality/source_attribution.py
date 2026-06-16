"""Source attribution quality analysis.

Evaluates how well the RAG answer attributes information to its sources.
Checks citation correctness, format compliance, and coverage.
"""

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SourceAttribution:
    """Analyze source attribution quality in RAG answers.

    Checks:
    - Whether citations are present when sources are used
    - Whether citations reference valid (provided) sources
    - Citation format compliance
    - Coverage: are all key claims cited?
    - Source relevance scoring
    """

    # Common citation patterns
    CITATION_PATTERNS = [
        re.compile(r'\[(\d+)\]'),              # [1]
        re.compile(r'\[([^\]]+)\]'),           # [source_name]
        re.compile(r'\(([^)]+),\s*\d{4}\)'),   # (Author, 2024)
        re.compile(r'\[Source\s+(\d+)\]'),     # [Source 1]
        re.compile(r'\[\d+\]'),                 # [1] (general)
    ]

    def __init__(self):
        """Initialize source attribution analyzer."""
        logger.info("SourceAttribution initialized")

    def analyze(self, answer: str, sources: list[dict]) -> dict:
        """Analyze source attribution quality.

        Args:
            answer: Generated answer text
            sources: List of source document dicts with {id, content, score}

        Returns:
            Dict with attribution metrics
        """
        # Find all citations in the answer
        citations = self._extract_citations(answer)
        source_ids = {s.get("id", str(i)) for i, s in enumerate(sources)}

        # Check each citation against provided sources
        valid_citations = []
        invalid_citations = []
        for citation in citations:
            if self._is_valid_citation(citation, source_ids, sources):
                valid_citations.append(citation)
            else:
                invalid_citations.append(citation)

        # Compute metrics
        has_sources = len(sources) > 0
        has_citations = len(citations) > 0

        # Citation coverage: are citations present?
        citation_present_score = 1.0 if has_citations else (0.0 if has_sources else 1.0)

        # Citation validity: do citations reference real sources?
        if citations:
            citation_validity = len(valid_citations) / len(citations)
        else:
            citation_validity = 1.0 if not has_sources else 0.0

        # Source coverage: how many sources are cited?
        cited_source_indices = set()
        for vc in valid_citations:
            if vc["type"] == "numeric":
                cited_source_indices.add(vc["index"] - 1)  # Convert 1-based to 0-based

        if has_sources:
            source_coverage = len(cited_source_indices) / len(sources)
        else:
            source_coverage = 1.0

        # Overall attribution score
        overall = (citation_present_score * 0.3 +
                   citation_validity * 0.4 +
                   source_coverage * 0.3)

        return {
            "overall_score": overall,
            "citation_present_score": citation_present_score,
            "citation_validity": citation_validity,
            "source_coverage": source_coverage,
            "total_citations": len(citations),
            "valid_citations": len(valid_citations),
            "invalid_citations": len(invalid_citations),
            "total_sources": len(sources),
            "cited_sources": len(cited_source_indices),
            "valid_citation_details": valid_citations[:10],
            "invalid_citation_details": invalid_citations[:10],
            "assessment": self._get_assessment(overall),
        }

    def _extract_citations(self, text: str) -> list[dict]:
        """Extract citation references from text."""
        citations = []

        # Extract numeric citations: [1], [2], etc.
        for match in re.finditer(r'\[(\d+)\]', text):
            idx = int(match.group(1))
            citations.append({
                "type": "numeric",
                "index": idx,
                "text": match.group(0),
                "position": match.start(),
            })

        # Extract named citations: [Source X], [document_name]
        for match in re.finditer(r'\[(?:Source|Ref|Doc)\.?\s*[:\s]?\s*([^\]]+)\]', text, re.IGNORECASE):
            citations.append({
                "type": "named",
                "name": match.group(1).strip(),
                "text": match.group(0),
                "position": match.start(),
            })

        return citations

    def _is_valid_citation(self, citation: dict, source_ids: set, sources: list) -> bool:
        """Check if a citation references a real source."""
        if citation["type"] == "numeric":
            idx = citation["index"]
            return 1 <= idx <= len(sources)

        if citation["type"] == "named":
            name = citation["name"].lower()
            for source in sources:
                source_content = source.get("content", "").lower()
                source_id = source.get("id", "").lower()
                if name in source_id or name in source_content[:100]:
                    return True

        return False

    def _get_assessment(self, score: float) -> str:
        """Get human-readable assessment."""
        if score >= 0.8:
            return "Excellent source attribution"
        elif score >= 0.6:
            return "Good source attribution, minor improvements possible"
        elif score >= 0.4:
            return "Moderate attribution, some claims lack citation"
        elif score >= 0.2:
            return "Poor attribution, most claims unsupported"
        else:
            return "No meaningful source attribution"

    def suggest_improvements(self, analysis: dict) -> list[str]:
        """Generate actionable improvement suggestions based on analysis."""
        suggestions = []

        if analysis["citation_present_score"] < 0.5:
            suggestions.append("Add inline citations to support key claims with source references")

        if analysis["citation_validity"] < 0.8:
            suggestions.append("Verify citations reference actual sources; remove or fix invalid ones")

        if analysis["source_coverage"] < 0.5:
            suggestions.append("Utilize more of the available sources in your answer")

        if analysis["total_citations"] == 0 and analysis["total_sources"] > 0:
            suggestions.append("Cite sources even when they provide background context")

        return suggestions
