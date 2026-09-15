"""Hallucination detection for RAG-generated answers.

Detects when the LLM generates information not present in the source
documents, using multiple detection strategies.
"""

import logging
import re
from collections import Counter
from typing import Any, Optional

logger = logging.getLogger(__name__)


class HallucinationDetector:
    """Multi-strategy hallucination detection.

    Strategies:
    1. Lexical overlap: Check answer words against source words
    2. Named entity verification: Are entities in the answer from sources?
    3. Numeric consistency: Do numbers match sources?
    4. LLM-based detection: Use LLM to identify unsupported statements
    """

    def __init__(self, llm_client=None, overlap_threshold: float = 0.4):
        """Initialize hallucination detector.

        Args:
            llm_client: Optional LLM for nuanced detection
            overlap_threshold: Lexical overlap threshold
        """
        self.llm_client = llm_client
        self.overlap_threshold = overlap_threshold
        logger.info("HallucinationDetector initialized (llm=%s)", "available" if llm_client else "heuristic")

    async def detect(
        self,
        answer: str,
        sources: list[dict],
        query: Optional[str] = None,
    ) -> dict:
        """Detect potential hallucinations in the answer.

        Args:
            answer: Generated answer text
            sources: Source documents
            query: Original query

        Returns:
            Dict with {hallucination_score, risk_level, flagged_spans, metrics}
        """
        if not answer:
            return {
                "hallucination_score": 0.0,
                "risk_level": "none",
                "flagged_spans": [],
                "metrics": {},
            }

        # Strategy 1: Lexical overlap
        overlap_score = self._lexical_overlap_score(answer, sources)

        # Strategy 2: Named entity check
        entity_score = self._entity_consistency_score(answer, sources)

        # Strategy 3: Numeric consistency
        numeric_score = self._numeric_consistency_score(answer, sources)

        # Combine scores
        combined_score = (overlap_score * 0.4 + entity_score * 0.3 + numeric_score * 0.3)

        # Strategy 4: LLM-based detection (if available)
        if self.llm_client:
            llm_flags = await self._llm_detect(answer, sources)
        else:
            llm_flags = self._heuristic_flag(answer, sources, combined_score)

        # Determine risk level
        risk_level = self._determine_risk_level(combined_score)

        return {
            "hallucination_score": round(1.0 - combined_score, 3),
            "risk_level": risk_level,
            "flagged_spans": llm_flags,
            "metrics": {
                "lexical_overlap": round(overlap_score, 3),
                "entity_consistency": round(entity_score, 3),
                "numeric_consistency": round(numeric_score, 3),
                "combined_confidence": round(combined_score, 3),
            },
        }

    def _lexical_overlap_score(self, answer: str, sources: list[dict]) -> float:
        """Compute lexical overlap between answer and sources."""
        if not sources:
            return 0.5  # Neutral when no sources

        answer_words = set(answer.lower().split())

        # Combine all source text
        source_text = " ".join(s.get("content", "") for s in sources).lower()
        source_words = set(source_text.split())

        # Remove stop words for more meaningful comparison
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                      "have", "has", "had", "do", "does", "did", "will", "would",
                      "could", "should", "may", "might", "can", "shall", "to", "of",
                      "in", "for", "on", "with", "at", "by", "from", "this", "that",
                      "these", "those", "it", "its", "and", "but", "or", "not", "no",
                      "if", "then", "else", "when", "where", "how", "what", "which",
                      "who", "whom", "i", "you", "he", "she", "they", "we", "me", "him",
                      "her", "us", "them", "my", "your", "his", "our", "their"}

        answer_keywords = {w for w in answer_words if w not in stop_words and len(w) > 2}
        source_keywords = {w for w in source_words if w not in stop_words and len(w) > 2}

        if not answer_keywords:
            return 1.0

        overlap = len(answer_keywords & source_keywords) / len(answer_keywords)
        return min(overlap, 1.0)

    def _entity_consistency_score(self, answer: str, sources: list[dict]) -> float:
        """Check if named entities in answer appear in sources."""
        # Extract potential named entities (capitalized multi-word phrases)
        entities = set(re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', answer))

        if not entities:
            return 1.0  # No entities to check

        source_text = " ".join(s.get("content", "") for s in sources)
        found_entities = sum(1 for e in entities if e in source_text)

        return found_entities / len(entities)

    def _numeric_consistency_score(self, answer: str, sources: list[dict]) -> float:
        """Check if numbers in answer are consistent with sources."""
        # Extract numbers from answer
        answer_numbers = set(re.findall(r'\b\d+(?:\.\d+)?%?\b', answer))

        if not answer_numbers:
            return 1.0  # No numbers to check

        source_text = " ".join(s.get("content", "") for s in sources)
        found_numbers = sum(1 for n in answer_numbers if n in source_text)

        return found_numbers / len(answer_numbers)

    async def _llm_detect(self, answer: str, sources: list[dict]) -> list[dict]:
        """Use LLM to flag potentially hallucinated spans."""
        context = " ".join(s.get("content", "")[:200] for s in sources[:3])[:1500]

        prompt = f"""Analyze whether the following answer is fully supported by the provided context.
For any statement NOT supported by the context, extract the exact text span.

Context:
{context}

Answer:
{answer[:1000]}

Respond in JSON format:
{{"is_fully_supported": true/false, "unsupported_spans": ["exact text span 1", ...]}}"""

        try:
            import json
            if hasattr(self.llm_client, 'generate'):
                response = await self.llm_client.generate(prompt)
            else:
                response = str(self.llm_client(prompt))

            result = json.loads(str(response))
            spans = result.get("unsupported_spans", [])
            return [{"text": span, "reason": "LLM-flagged as unsupported"} for span in spans]
        except Exception as e:
            logger.warning("LLM hallucination detection error: %s", e)
            return self._heuristic_flag(answer, sources, 0.5)

    def _heuristic_flag(self, answer: str, sources: list[dict], score: float) -> list[dict]:
        """Heuristic flagging of potentially hallucinated spans."""
        flags = []

        if score < self.overlap_threshold:
            # Flag sentences with low source overlap
            sentences = re.split(r'(?<=[.!?])\s+', answer)
            source_text = " ".join(s.get("content", "") for s in sources).lower()

            for sentence in sentences:
                s_words = set(sentence.lower().split())
                src_words = set(source_text.split())

                if s_words:
                    sent_overlap = len(s_words & src_words) / len(s_words)
                    if sent_overlap < self.overlap_threshold:
                        flags.append({
                            "text": sentence[:200],
                            "reason": f"Low source overlap ({sent_overlap:.1%})",
                        })

        return flags[:5]  # Limit to top 5 flags

    def _determine_risk_level(self, score: float) -> str:
        """Determine risk level based on confidence score."""
        if score >= 0.85:
            return "low"
        elif score >= 0.65:
            return "moderate"
        elif score >= 0.45:
            return "high"
        else:
            return "critical"

    async def detect_batch(
        self,
        answers: list[str],
        sources_list: list[list[dict]],
    ) -> list[dict]:
        """Detect hallucinations in a batch of answers."""
        results = []
        for answer, sources in zip(answers, sources_list):
            result = await self.detect(answer, sources)
            results.append(result)
        return results
