"""Integration tests for the real RAG pipeline (no mock, real retrieve/generate)."""

import numpy as np
import pytest

from src.rag.pipeline import RAGPipeline
from src.rag.indexing.vector_store import InMemoryVectorStore


class _HashEmbedder:
    """Deterministic hash embedder (no external model required)."""

    def __init__(self, dim=64):
        self._dim = dim
        self.name = "hash-embedder"

    async def embed(self, texts):
        import hashlib
        out = []
        for text in texts:
            vec = np.zeros(self._dim, dtype=float)
            for token in text.lower().split():
                h = int(hashlib.md5(token.encode()).hexdigest(), 16)
                vec[h % self._dim] += 1.0
            norm = np.linalg.norm(vec)
            out.append(vec / norm if norm > 0 else vec)
        return out

    async def embed_query(self, query):
        return (await self.embed([query]))[0]


@pytest.fixture
def pipeline():
    return RAGPipeline(vector_store=InMemoryVectorStore(), embedder=_HashEmbedder(), chunk_size=200, chunk_overlap=50)


class TestRAGPipeline:
    """Integration tests: index -> retrieve -> generate full flow."""

    @pytest.mark.asyncio
    async def test_index_and_retrieve(self, pipeline):
        content = ("Machine learning is a branch of AI. " * 20).encode("utf-8")
        result = await pipeline.index_document(document_id="doc-1", filename="ml.txt", content=content)
        assert result["status"] == "completed"
        assert result["chunks_count"] > 0

        retrieval = await pipeline.retrieve("machine learning", top_k=3)
        assert len(retrieval.chunks) > 0
        assert retrieval.chunks[0].document_id == "doc-1"

    @pytest.mark.asyncio
    async def test_full_flow(self, pipeline):
        content = ("The capital of France is Paris. " * 20).encode("utf-8")
        await pipeline.index_document(document_id="doc-1", filename="france.txt", content=content)

        retrieval = await pipeline.retrieve("capital of France", top_k=2)
        contexts = [c.content for c in retrieval.chunks]
        generation = await pipeline.generate("capital of France", contexts)

        assert len(generation.answer) > 0

    @pytest.mark.asyncio
    async def test_evaluate(self, pipeline):
        content = ("AI transforms industries. " * 10).encode("utf-8")
        await pipeline.index_document(document_id="doc-1", filename="ai.txt", content=content)

        result = await pipeline.evaluate(queries=["What is AI?"], expected_answers=["AI is ..."])
        assert "faithfulness" in result
        assert result["num_queries"] == 1
