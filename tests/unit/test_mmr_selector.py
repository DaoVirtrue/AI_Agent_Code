"""Unit tests for Maximal Marginal Relevance (MMR) document selector."""

import pytest
import math


class TestMMRSelector:
    """Tests for the MMR document/chunk selector."""

    @pytest.fixture
    def selector(self):
        """Create an MMR selector."""
        from src.rag.mmr_selector import MMRSelector
        return MMRSelector(diversity_lambda=0.5)

    @pytest.fixture
    def sample_chunks(self):
        """Create sample document chunks with embeddings."""
        return [
            self._make_chunk("id-1", "Paris is the capital of France", [1.0, 0.8, 0.2]),
            self._make_chunk("id-2", "Paris is a beautiful city in Europe", [0.9, 1.0, 0.1]),
            self._make_chunk("id-3", "The French Revolution changed France", [0.1, 0.2, 1.0]),
            self._make_chunk("id-4", "Tokyo is the capital of Japan", [-0.5, -0.3, 0.0]),
            self._make_chunk("id-5", "France is in Western Europe", [0.7, 0.6, 0.2]),
            self._make_chunk("id-6", "Japan is an island nation in East Asia", [-0.6, -0.4, 0.1]),
            self._make_chunk("id-7", "Paris has many famous museums", [0.8, 0.9, 0.0]),
            self._make_chunk("id-8", "French cuisine is world-renowned", [0.5, 0.7, 0.3]),
        ]

    @staticmethod
    def _make_chunk(chunk_id, content, embedding):
        """Create a chunk-like object for testing."""
        class Chunk:
            def __init__(self):
                self.chunk_id = chunk_id
                self.content = content
                self.embedding = embedding
                self.score = 0.85
        return Chunk()

    def test_select_top_k(self, selector, sample_chunks):
        """Test that MMR selects exactly k chunks."""
        query_embedding = [1.0, 0.8, 0.2]
        selected = selector.select(sample_chunks, query_embedding, top_k=3)
        assert len(selected) == 3

    def test_select_respects_diversity(self, selector, sample_chunks):
        """Test that MMR promotes diversity in selections."""
        query_embedding = [1.0, 0.8, 0.2]

        # Low diversity (lambda=1.0 = max relevance, no diversity)
        rel_only = type(selector)(diversity_lambda=1.0)
        rel_selected = rel_only.select(sample_chunks, query_embedding, top_k=3)

        # High diversity (lambda=0.0 = max diversity, no relevance)
        div_only = type(selector)(diversity_lambda=0.0)
        div_selected = div_only.select(sample_chunks, query_embedding, top_k=3)

        # They should select differently
        rel_ids = [c.chunk_id for c in rel_selected]
        div_ids = [c.chunk_id for c in div_selected]
        assert rel_ids != div_ids

    def test_select_with_lambda_params(self, sample_chunks):
        """Test MMR with different lambda values."""
        query_embedding = [1.0, 0.8, 0.2]

        for lam in [0.0, 0.25, 0.5, 0.75, 1.0]:
            sel = type(self.selector)(diversity_lambda=lam)
            result = sel.select(sample_chunks, query_embedding, top_k=3)
            assert len(result) == 3

    def test_select_returns_empty_for_empty_chunks(self, selector):
        """Test that MMR returns empty list for empty input."""
        result = selector.select([], [1.0, 0.5, 0.0], top_k=5)
        assert result == []

    def test_select_handles_k_larger_than_input(self, selector, sample_chunks):
        """Test MMR when k > number of chunks."""
        query_embedding = [1.0, 0.8, 0.2]
        result = selector.select(sample_chunks, query_embedding, top_k=100)
        assert len(result) == len(sample_chunks)

    def test_select_k_zero_returns_empty(self, selector, sample_chunks):
        """Test that k=0 returns empty result."""
        query_embedding = [1.0, 0.8, 0.2]
        result = selector.select(sample_chunks, query_embedding, top_k=0)
        assert result == []

    def test_cosine_similarity(self, selector):
        """Test cosine similarity computation."""
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        sim = selector._cosine_similarity(a, b)
        assert abs(sim - 0.0) < 0.01

        a = [1.0, 2.0, 3.0]
        sim = selector._cosine_similarity(a, a)
        assert abs(sim - 1.0) < 0.01

    def test_selection_order_matters(self, selector, sample_chunks):
        """Test that the first selected item is most relevant to the query."""
        query_embedding = [1.0, 0.8, 0.2]
        selected = selector.select(sample_chunks, query_embedding, top_k=3)
        # First item should be the one most similar to query
        assert len(selected) >= 1
        first_content = selected[0].content
        assert "Paris" in first_content  # Most relevant to query
