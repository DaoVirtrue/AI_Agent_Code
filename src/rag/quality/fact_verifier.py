"""Fact verification for RAG-generated answers.

Verifies factual claims in generated answers against source documents
to detect and flag unsupported statements.
"""

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


class FactVerifier:
    """Verify factual claims in RAG answers against source documents.

    Decomposes an answer into individual factual claims, then checks
    each claim against the retrieved context. Claims not supported by
    any source are flagged as potentially hallucinated.
    """

    VERIFICATION_PROMPT = """Determine if the following claim is SUPPORTED, PARTIALLY_SUPPORTED, or UNSUPPORTED based on the provided context.

Claim: {claim}

Context:
{context}

Respond with ONLY one word: SUPPORTED, PARTIALLY_SUPPORTED, or UNSUPPORTED."""

    def __init__(self, llm_client=None, verification_threshold: float = 0.5):
        """Initialize fact verifier.

        Args:
            llm_client: Optional LLM for nuanced verification
            verification_threshold: Overlap threshold for heuristic mode
        """
        self.llm_client = llm_client
        self.verification_threshold = verification_threshold
        logger.info("FactVerifier initialized (llm=%s)", "available" if llm_client else "heuristic")

    async def verify(
        self,
        answer: str,
        sources: list[dict],
        query: Optional[str] = None,
    ) -> dict:
        """Verify all factual claims in an answer against sources.

        Args:
            answer: Generated answer text
            sources: List of {id, content, score} source documents
            query: Original query for context

        Returns:
            Dict with {verification_status, claims, overall_score, summary}
        """
        # Step 1: Extract claims from the answer
        claims = self._extract_claims(answer)

        if not claims:
            return {
                "verification_status": "unverifiable",
                "claims": [],
                "overall_score": 1.0,
                "summary": "No discrete claims could be extracted from the answer.",
            }

        # Step 2: Build context from sources
        context = self._build_context(sources)

        # Step 3: Verify each claim
        verified_claims = []
        supported_count = 0

        for claim in claims:
            if self.llm_client:
                result = await self._llm_verify_claim(claim, context)
            else:
                result = self._heuristic_verify_claim(claim, context)

            verified_claims.append({
                "claim": claim,
                "status": result["status"],
                "confidence": result.get("confidence", 0.5),
                "evidence": result.get("evidence", ""),
            })

            if result["status"] == "SUPPORTED":
                supported_count += 1

        # Step 4: Compute overall score
        total = len(verified_claims)
        overall_score = supported_count / total if total > 0 else 1.0

        status = "verified" if overall_score >= 0.8 else (
            "partially_verified" if overall_score >= 0.5 else "poorly_supported"
        )

        return {
            "verification_status": status,
            "claims": verified_claims,
            "overall_score": overall_score,
            "total_claims": total,
            "supported_claims": supported_count,
            "summary": f"{supported_count}/{total} claims supported by sources ({overall_score:.0%})",
        }

    def _extract_claims(self, text: str) -> list[str]:
        """Extract individual factual claims from text.

        Splits by sentences, filters for factual content (sentences with
        verbs, numbers, named entities, or comparison language).
        """
        # Split into sentences
        sentences = re.split(r'(?<=[.!?。！？])\s+', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return [text]

        claims = []
        for sentence in sentences:
            # Filter out meta-commentary and qualifying statements
            if self._is_factual_claim(sentence):
                claims.append(sentence)

        return claims if claims else [text]

    def _is_factual_claim(self, sentence: str) -> bool:
        """Check if a sentence looks like a factual claim."""
        # Skip very short sentences
        if len(sentence.split()) < 3:
            return False

        # Skip meta-statements
        meta_patterns = [
            r'^(?:I think|I believe|In my opinion|Perhaps|Maybe)',
            r'^(?:However|Therefore|In conclusion|To summarize)',
            r'^(?:Please note|Note that|It is worth noting)',
        ]
        for pattern in meta_patterns:
            if re.match(pattern, sentence, re.IGNORECASE):
                return False

        # Check for factual indicators: numbers, proper nouns, relational language
        has_number = bool(re.search(r'\d+', sentence))
        has_proper = bool(re.search(r'[A-Z][a-z]+\s[A-Z]', sentence))
        has_assertion = bool(re.search(r'\b(?:is|are|was|were|has|have|had|will|can|must|should)\b', sentence.lower()))

        return has_number or has_proper or has_assertion

    def _build_context(self, sources: list[dict]) -> str:
        """Build verification context from source documents."""
        context_parts = []
        for i, source in enumerate(sources):
            content = source.get("content", "")
            context_parts.append(f"[Source {i+1}] {content}")
        return "\n\n".join(context_parts)

    async def _llm_verify_claim(self, claim: str, context: str) -> dict:
        """Verify a claim using LLM."""
        prompt = self.VERIFICATION_PROMPT.format(
            claim=claim,
            context=context[:2000],
        )

        try:
            if hasattr(self.llm_client, 'generate'):
                response = await self.llm_client.generate(prompt)
            else:
                response = str(self.llm_client(prompt))

            status_text = str(response).strip().upper()

            if "UNSUPPORTED" in status_text:
                status = "UNSUPPORTED"
                confidence = 0.3
            elif "PARTIALLY" in status_text:
                status = "PARTIALLY_SUPPORTED"
                confidence = 0.6
            else:
                status = "SUPPORTED"
                confidence = 0.9

            return {
                "status": status,
                "confidence": confidence,
                "evidence": "",
            }
        except Exception as e:
            logger.warning("LLM verification error: %s", e)
            return self._heuristic_verify_claim(claim, context)

    def _heuristic_verify_claim(self, claim: str, context: str) -> dict:
        """Heuristic claim verification using term overlap."""
        claim_lower = claim.lower()
        context_lower = context.lower()

        # Tokenize
        claim_words = set(claim_lower.split())
        context_words = set(context_lower.split())

        # Remove common words
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                      "being", "have", "has", "had", "do", "does", "did", "will",
                      "would", "could", "should", "may", "might", "can", "shall",
                      "to", "of", "in", "for", "on", "with", "at", "by", "from",
                      "this", "that", "these", "those", "it", "its", "and", "but", "or"}

        claim_keywords = {w for w in claim_words if w not in stop_words and len(w) > 2}
        context_keywords = {w for w in context_words if w not in stop_words}

        if not claim_keywords:
            return {"status": "UNSUPPORTED", "confidence": 0.0, "evidence": ""}

        overlap = len(claim_keywords & context_keywords) / len(claim_keywords)

        if overlap >= 0.7:
            status = "SUPPORTED"
            confidence = overlap
        elif overlap >= 0.4:
            status = "PARTIALLY_SUPPORTED"
            confidence = overlap
        else:
            status = "UNSUPPORTED"
            confidence = overlap

        return {"status": status, "confidence": confidence, "evidence": ""}

    async def verify_batch(
        self,
        answers: list[str],
        sources_list: list[list[dict]],
    ) -> list[dict]:
        """Verify multiple answers against their respective sources."""
        results = []
        for answer, sources in zip(answers, sources_list):
            result = await self.verify(answer, sources)
            results.append(result)
        return results
