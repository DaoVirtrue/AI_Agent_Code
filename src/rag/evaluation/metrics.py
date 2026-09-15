"""Custom RAG evaluation metrics independent of RAGAS."""

import logging
import math
import re
from collections import Counter
from typing import Any, Optional, Callable

logger = logging.getLogger(__name__)


class RAGMetrics:
    """Standalone RAG quality metrics without external dependencies.

    Provides:
    - Retrieval metrics: Precision@k, Recall@k, MRR, NDCG, MAP
    - Generation metrics: BLEU, ROUGE-L, exact match
    - Combined metrics: answer correctness, citation accuracy
    """

    @staticmethod
    def precision_at_k(
        retrieved_ids: list[str], relevant_ids: list[str], k: int = 5
    ) -> float:
        """Precision@K: fraction of top-k results that are relevant."""
        if k <= 0:
            return 0.0
        retrieved_k = set(retrieved_ids[:k])
        relevant_set = set(relevant_ids)
        hits = len(retrieved_k & relevant_set)
        return hits / k

    @staticmethod
    def recall_at_k(
        retrieved_ids: list[str], relevant_ids: list[str], k: int = 5
    ) -> float:
        """Recall@K: fraction of all relevant items found in top-k."""
        if not relevant_ids:
            return 0.0
        retrieved_k = set(retrieved_ids[:k])
        relevant_set = set(relevant_ids)
        hits = len(retrieved_k & relevant_set)
        return hits / len(relevant_set)

    @staticmethod
    def mrr(retrieved_ids: list[str], relevant_ids: list[str]) -> float:
        """Mean Reciprocal Rank: 1/rank of first relevant result."""
        relevant_set = set(relevant_ids)
        for rank, doc_id in enumerate(retrieved_ids, 1):
            if doc_id in relevant_set:
                return 1.0 / rank
        return 0.0

    @staticmethod
    def ndcg_at_k(
        retrieved_ids: list[str],
        relevance_scores: dict[str, float],
        k: int = 5,
    ) -> float:
        """Normalized Discounted Cumulative Gain at K."""
        if k <= 0:
            return 0.0

        # DCG
        dcg = 0.0
        for i, doc_id in enumerate(retrieved_ids[:k]):
            rel = relevance_scores.get(doc_id, 0.0)
            dcg += rel / math.log2(i + 2)  # i+2 because log(1)=0

        # IDCG (ideal DCG)
        ideal_rels = sorted(relevance_scores.values(), reverse=True)[:k]
        idcg = 0.0
        for i, rel in enumerate(ideal_rels):
            idcg += rel / math.log2(i + 2)

        return dcg / idcg if idcg > 0 else 0.0

    @staticmethod
    def map_score(
        retrieved_lists: list[list[str]], relevant_lists: list[list[str]]
    ) -> float:
        """Mean Average Precision across multiple queries."""
        if not retrieved_lists:
            return 0.0

        ap_scores = []
        for retrieved, relevant in zip(retrieved_lists, relevant_lists):
            ap_scores.append(RAGMetrics._average_precision(retrieved, relevant))

        return sum(ap_scores) / len(ap_scores)

    @staticmethod
    def _average_precision(retrieved: list[str], relevant: list[str]) -> float:
        """Average precision for a single query."""
        relevant_set = set(relevant)
        if not relevant_set:
            return 0.0

        hits = 0
        sum_precisions = 0.0

        for i, doc_id in enumerate(retrieved, 1):
            if doc_id in relevant_set:
                hits += 1
                sum_precisions += hits / i

        return sum_precisions / len(relevant_set)

    # ---- Generation Metrics ----

    @staticmethod
    def exact_match(predicted: str, ground_truth: str) -> float:
        """Exact match accuracy (after normalization)."""
        pred_norm = predicted.strip().lower()
        truth_norm = ground_truth.strip().lower()
        return 1.0 if pred_norm == truth_norm else 0.0

    @staticmethod
    def bleu_score(predicted: str, reference: str, max_n: int = 4) -> float:
        """Compute BLEU score (character-level approximation)."""
        pred_tokens = predicted.lower().split()
        ref_tokens = reference.lower().split()

        if not pred_tokens:
            return 0.0

        precisions = []
        for n in range(1, max_n + 1):
            pred_ngrams = [tuple(pred_tokens[i:i+n]) for i in range(len(pred_tokens)-n+1)]
            ref_ngrams = [tuple(ref_tokens[i:i+n]) for i in range(len(ref_tokens)-n+1)]

            if not pred_ngrams:
                precisions.append(0.0)
                continue

            pred_counts = Counter(pred_ngrams)
            ref_counts = Counter(ref_ngrams)

            clipped = sum(min(pred_counts[ng], ref_counts[ng]) for ng in pred_counts)
            precisions.append(clipped / len(pred_ngrams) if pred_ngrams else 0.0)

        # Brevity penalty
        if len(pred_tokens) < len(ref_tokens):
            bp = math.exp(1 - len(ref_tokens) / max(len(pred_tokens), 1))
        else:
            bp = 1.0

        # Geometric mean of precisions
        log_sum = sum(math.log(p) for p in precisions if p > 0)
        if log_sum == 0:
            return 0.0
        geo_mean = math.exp(log_sum / max_n)

        return bp * geo_mean

    @staticmethod
    def rouge_l(predicted: str, reference: str) -> float:
        """ROUGE-L: Longest Common Subsequence based F-measure."""
        pred_tokens = predicted.lower().split()
        ref_tokens = reference.lower().split()

        lcs_length = RAGMetrics._lcs_length(pred_tokens, ref_tokens)

        if not pred_tokens or not ref_tokens:
            return 0.0

        precision = lcs_length / len(pred_tokens) if pred_tokens else 0.0
        recall = lcs_length / len(ref_tokens) if ref_tokens else 0.0

        if precision + recall == 0:
            return 0.0

        return 2 * precision * recall / (precision + recall)

    @staticmethod
    def _lcs_length(a: list, b: list) -> int:
        """Length of Longest Common Subsequence."""
        m, n = len(a), len(b)
        dp = [[0] * (n + 1) for _ in range(m + 1)]

        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if a[i-1] == b[j-1]:
                    dp[i][j] = dp[i-1][j-1] + 1
                else:
                    dp[i][j] = max(dp[i-1][j], dp[i][j-1])

        return dp[m][n]

    # ---- Combined Metrics ----

    @staticmethod
    def citation_accuracy(answer: str, sources: list[dict]) -> float:
        """Check if citations in the answer reference valid sources."""
        if not sources:
            return 1.0  # No citations needed if no sources

        # Find citation patterns like [1], [2], [source_name]
        citation_pattern = re.compile(r'\[(\d+)\]|\[([^\]]+)\]')
        citations = citation_pattern.findall(answer)

        if not citations:
            return 0.5  # Penalize for not citing

        source_ids = {s.get("id", "") for s in sources}
        valid = 0
        total = 0

        for num_cite, name_cite in citations:
            total += 1
            cite = num_cite or name_cite
            # Check if citation refers to a valid source
            if cite.isdigit():
                idx = int(cite)
                if 0 < idx <= len(sources):
                    valid += 1
            elif cite in source_ids:
                valid += 1

        return valid / total if total > 0 else 0.0

    @staticmethod
    def combined_quality_score(
        answer: str,
        query: str,
        contexts: list[str],
        ground_truth: Optional[str] = None,
    ) -> dict:
        """Compute a combined quality score from multiple metrics."""
        scores = {}

        # Faithfulness approximation
        if contexts:
            combined_ctx = " ".join(contexts).lower()
            ans_words = set(answer.lower().split())
            ctx_words = set(combined_ctx.split())
            scores["faithfulness"] = len(ans_words & ctx_words) / max(len(ans_words), 1) if ans_words else 1.0
        else:
            scores["faithfulness"] = 0.5

        # Relevancy
        q_words = set(query.lower().split())
        a_words = set(answer.lower().split())
        scores["relevancy"] = len(q_words & a_words) / max(len(q_words), 1) if q_words else 0.8

        # Conciseness (penalize overly long answers)
        ideal_length = max(50, len(query) * 3)
        length_ratio = len(answer) / ideal_length
        scores["conciseness"] = max(0.2, min(1.0, 1.0 / max(length_ratio, 0.5)))

        # Ground truth comparison
        if ground_truth:
            scores["rouge_l"] = RAGMetrics.rouge_l(answer, ground_truth)

        # Overall
        scores["overall"] = sum(scores.values()) / len(scores)

        return scores
