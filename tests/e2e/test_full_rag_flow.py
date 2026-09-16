"""End-to-end tests for the full RAG flow: index -> retrieve -> generate -> evaluate.

Uses the real RAG pipeline with an in-memory vector store (no external DB/Redis),
so the full flow is exercised without infrastructure.
"""

import numpy as np
import pytest

from src.rag.pipeline import RAGPipeline
from src.rag.indexing.vector_store import InMemoryVectorStore


class _HashEmbedder:
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


class TestFullRAGFlow:
    """End-to-end: upload -> index -> list -> retrieve -> generate -> delete."""

    @pytest.mark.asyncio
    async def test_full_crud_flow(self, pipeline):
        # 1. index a document
        content = ("Paris is the capital of France. " * 30).encode("utf-8")
        result = await pipeline.index_document(
            document_id="doc-1", filename="france.txt", content=content, tenant_id="default",
        )
        assert result["status"] == "completed"

        # 2. list documents
        listing = await pipeline.list_documents(tenant_id="default")
        assert listing["total"] == 1

        # 3. retrieve
        retrieval = await pipeline.retrieve("capital of France", top_k=3)
        assert len(retrieval.chunks) > 0

        # 4. generate
        gen = await pipeline.generate("capital of France", [c.content for c in retrieval.chunks])
        assert len(gen.answer) > 0

        # 5. delete
        deleted = await pipeline.delete_document("doc-1", tenant_id="default")
        assert deleted is True
        listing = await pipeline.list_documents(tenant_id="default")
        assert listing["total"] == 0

    @pytest.mark.asyncio
    async def test_multi_document_retrieval(self, pipeline):
        # Index two documents on different topics
        await pipeline.index_document(document_id="doc-france", filename="france.txt",
            content=("Paris is the capital of France. Eiffel Tower. " * 20).encode("utf-8"))
        await pipeline.index_document(document_id="doc-china", filename="china.txt",
            content=("Beijing is the capital of China. Great Wall. " * 20).encode("utf-8"))

        # Query should retrieve the France doc
        retrieval = await pipeline.retrieve("Eiffel Tower", top_k=2)
        assert len(retrieval.chunks) > 0
        # The top result should come from the France doc
        assert any("France" in c.content for c in retrieval.chunks)

    @pytest.mark.asyncio
    async def test_evaluate_flow(self, pipeline):
        await pipeline.index_document(document_id="doc-ai", filename="ai.txt",
            content=("Artificial intelligence is transforming industries. " * 15).encode("utf-8"))

        result = await pipeline.evaluate(queries=["What is AI?"], expected_answers=["AI"])
        assert result["num_queries"] == 1
        assert 0.0 <= result["overall_score"] <= 1.0
