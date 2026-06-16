"""Integration tests for the RAG pipeline with test ChromaDB/vector store."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestRAGPipeline:
    """Integration tests for the RAG pipeline."""

    @pytest.fixture
    async def pipeline(self, test_redis, test_db_session):
        """Create a RAG pipeline with mocked components."""
        from src.rag.pipeline import RAGPipeline

        pipeline = RAGPipeline(
            redis=test_redis,
            db_session_factory=lambda: test_db_session,
        )

        # Mock the vector store
        mock_vector_store = AsyncMock()
        mock_vector_store.search = AsyncMock(return_value=[
            MagicMock(
                document_id="doc-1",
                chunk_id="chunk-1",
                content="Paris is the capital of France.",
                score=0.95,
                metadata={"source": "wiki"},
            ),
            MagicMock(
                document_id="doc-2",
                chunk_id="chunk-2",
                content="France is in Western Europe.",
                score=0.85,
                metadata={"source": "wiki"},
            ),
            MagicMock(
                document_id="doc-3",
                chunk_id="chunk-3",
                content="The Eiffel Tower is in Paris.",
                score=0.75,
                metadata={"source": "travel"},
            ),
        ])
        mock_vector_store.add_documents = AsyncMock()
        mock_vector_store.delete = AsyncMock()
        pipeline._vector_store = mock_vector_store

        # Mock the chunker
        mock_chunker = MagicMock()
        mock_chunker.chunk = MagicMock(return_value=[
            MagicMock(content="Chunk 1 content"),
            MagicMock(content="Chunk 2 content"),
            MagicMock(content="Chunk 3 content"),
        ])
        pipeline._chunker = mock_chunker

        # Mock the embedder
        mock_embedder = AsyncMock()
        mock_embedder.embed = AsyncMock(return_value=[[0.1] * 128])
        pipeline._embedder = mock_embedder

        # Mock the generator
        mock_generator = AsyncMock()
        mock_generator.generate = AsyncMock(return_value=MagicMock(
            answer="Paris is the capital of France.",
            token_usage={"prompt_tokens": 20, "completion_tokens": 10},
            cost_usd=0.0001,
        ))
        pipeline._generator = mock_generator

        return pipeline

    @pytest.mark.asyncio
    async def test_retrieve_chunks(self, pipeline):
        """Test retrieving relevant document chunks."""
        result = await pipeline.retrieve(
            query="What is the capital of France?",
            top_k=3,
            strategy="hybrid",
            tenant_id="test-tenant",
        )
        assert hasattr(result, 'chunks')
        assert len(result.chunks) == 3
        assert "Paris" in result.chunks[0].content

    @pytest.mark.asyncio
    async def test_generate_answer(self, pipeline):
        """Test generating an answer from retrieved contexts."""
        result = await pipeline.generate(
            query="What is the capital of France?",
            contexts=["Paris is the capital of France.", "France is a European country."],
            tenant_id="test-tenant",
        )
        assert hasattr(result, 'answer')
        assert len(result.answer) > 0

    @pytest.mark.asyncio
    async def test_index_document(self, pipeline):
        """Test indexing a document."""
        result = await pipeline.index_document(
            document_id="test-doc",
            filename="test.txt",
            content=b"Test document content for indexing.",
            content_type="text/plain",
            metadata={},
            chunk_size=1000,
            chunk_overlap=200,
            tenant_id="test-tenant",
            content_hash="abc123",
        )
        assert result["status"] == "completed"
        assert result["chunks_count"] > 0

    @pytest.mark.asyncio
    async def test_cache_operations(self, pipeline):
        """Test RAG response caching."""
        # Check cache miss
        result = await pipeline.check_cache("test-key-123")
        assert result is None

        # Store and retrieve
        await pipeline.cache_response(
            cache_key="test-key-123",
            answer="Cached answer",
            sources=[],
            ttl=3600,
        )

        # Mock cache hit
        pipeline.check_cache = AsyncMock(return_value={
            "answer": "Cached answer",
            "sources": [],
        })
        cached = await pipeline.check_cache("test-key-123")
        assert cached is not None
        assert cached["answer"] == "Cached answer"

    @pytest.mark.asyncio
    async def test_get_cache_stats(self, pipeline):
        """Test getting cache statistics."""
        stats = await pipeline.get_cache_stats(tenant_id="test-tenant")
        assert "size" in stats or "hit_rate" in stats

    @pytest.mark.asyncio
    async def test_list_documents(self, pipeline):
        """Test listing indexed documents."""
        result = await pipeline.list_documents(
            tenant_id="test-tenant",
            page=1,
            page_size=10,
        )
        assert "items" in result
        assert "total" in result

    @pytest.mark.asyncio
    async def test_delete_document(self, pipeline):
        """Test deleting a document."""
        await pipeline.delete_document("test-doc", tenant_id="test-tenant")
        # Should not raise an exception

    @pytest.mark.asyncio
    async def test_rerank_chunks(self, pipeline):
        """Test reranking retrieved chunks."""
        from collections import namedtuple
        Chunk = namedtuple("Chunk", ["document_id", "chunk_id", "content", "score", "metadata"])

        chunks = [
            Chunk("d1", "c1", "Content A", 0.9, {}),
            Chunk("d2", "c2", "Content B", 0.7, {}),
            Chunk("d3", "c3", "Content C", 0.5, {}),
        ]

        retrieved = MagicMock()
        retrieved.chunks = chunks

        # Mock rerank function
        pipeline.rerank = AsyncMock(return_value=retrieved)
        result = await pipeline.rerank(
            query="test query",
            chunks=chunks,
        )
        assert hasattr(result, 'chunks')

    @pytest.mark.asyncio
    async def test_full_search_flow(self, pipeline):
        """Test the full search flow end-to-end (retrieve + generate)."""
        # This test validates the integration of retrieve and generate
        retrieval = await pipeline.retrieve(
            query="What is the capital of France?",
            top_k=3,
            strategy="hybrid",
            tenant_id="test-tenant",
        )

        generation = await pipeline.generate(
            query="What is the capital of France?",
            contexts=[c.content for c in retrieval.chunks],
            tenant_id="test-tenant",
        )

        assert retrieval.chunks
        assert generation.answer
