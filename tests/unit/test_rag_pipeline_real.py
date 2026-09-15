"""Unit tests for the real RAG pipeline (ingest -> retrieve -> generate)."""

import numpy as np
import pytest

from src.rag.pipeline import RAGPipeline, RetrievalChunk, RetrievalResult, GenerationResult
from src.rag.indexing.vector_store import InMemoryVectorStore, VectorDocument


class _HashEmbedder:
    """Deterministic hash embedder for tests (no external model)."""

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
    store = InMemoryVectorStore()
    embedder = _HashEmbedder()
    return RAGPipeline(vector_store=store, embedder=embedder, chunk_size=200, chunk_overlap=50)


class TestRAGPipeline:
    """Tests for the real RAG pipeline."""

    @pytest.mark.asyncio
    async def test_index_document(self, pipeline):
        content = ("Paris is the capital of France. " * 20).encode("utf-8")
        result = await pipeline.index_document(
            document_id="doc-1",
            filename="test.txt",
            content=content,
            content_type="text/plain",
        )
        assert result["status"] == "completed"
        assert result["chunks_count"] > 0

    @pytest.mark.asyncio
    async def test_retrieve_returns_chunks(self, pipeline):
        content = ("The capital of France is Paris. " * 20).encode("utf-8")
        await pipeline.index_document(
            document_id="doc-1", filename="f.txt", content=content
        )
        result = await pipeline.retrieve("capital of France", top_k=3)
        assert isinstance(result, RetrievalResult)
        assert len(result.chunks) > 0
        assert result.chunks[0].document_id == "doc-1"

    @pytest.mark.asyncio
    async def test_generate_extractive_fallback(self, pipeline):
        content = ("Machine learning is a branch of AI. " * 20).encode("utf-8")
        await pipeline.index_document(document_id="doc-1", filename="f.txt", content=content)
        retrieval = await pipeline.retrieve("machine learning", top_k=2)
        contexts = [c.content for c in retrieval.chunks]
        gen = await pipeline.generate("machine learning", contexts)
        assert isinstance(gen, GenerationResult)
        assert len(gen.answer) > 0

    @pytest.mark.asyncio
    async def test_rerank_sorts(self, pipeline):
        chunks = [
            RetrievalChunk(document_id="d1", chunk_id="c1", content="Paris is the capital", score=0.5),
            RetrievalChunk(document_id="d2", chunk_id="c2", content="unrelated topic", score=0.5),
        ]
        result = await pipeline.rerank("Paris capital", chunks)
        assert result.chunks[0].document_id == "d1"

    @pytest.mark.asyncio
    async def test_cache_operations(self, pipeline):
        assert await pipeline.check_cache("k1") is None
        await pipeline.cache_response("k1", "answer", [])
        cached = await pipeline.check_cache("k1")
        assert cached is not None
        assert cached["answer"] == "answer"

    @pytest.mark.asyncio
    async def test_list_and_delete_documents(self, pipeline):
        content = b"test content " * 100
        await pipeline.index_document(document_id="doc-a", filename="a.txt", content=content)
        listing = await pipeline.list_documents(tenant_id="default")
        assert listing["total"] == 1

        deleted = await pipeline.delete_document("doc-a")
        assert deleted is True
        listing = await pipeline.list_documents(tenant_id="default")
        assert listing["total"] == 0

    @pytest.mark.asyncio
    async def test_evaluate_returns_scores(self, pipeline):
        content = ("Artificial intelligence transforms industries. " * 10).encode("utf-8")
        await pipeline.index_document(document_id="doc-1", filename="f.txt", content=content)
        result = await pipeline.evaluate(queries=["What is AI?"], expected_answers=["AI is ..."])
        assert "faithfulness" in result
        assert "overall_score" in result
        assert result["num_queries"] == 1
