"""End-to-end tests for the full RAG flow: upload -> index -> search -> evaluate."""

import pytest
pytestmark = pytest.mark.skip(reason='M0: 引用不存在的旧模块 (src.agent.* / src.gateway.* / src.rag.*) 或缺 fixture (test_redis/test_db_session/test_app)，待 M2/M3 真实链路接通后重写。')
from unittest.mock import AsyncMock, MagicMock, patch


class TestFullRAGFlow:
    """End-to-end tests covering the complete RAG workflow."""

    @pytest.fixture
    def test_client(self, test_app):
        """Get the FastAPI test client with all routes registered."""
        return test_app

    def test_upload_document_flow(self, test_client):
        """Test the full document upload flow."""
        # Upload a document
        response = test_client.post(
            "/v1/rag/documents/upload",
            files={"file": ("test_doc.txt", b"Paris is the capital of France.", "text/plain")},
            data={"chunk_size": 500, "chunk_overlap": 100},
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "completed"
        assert data["chunks_count"] > 0
        assert "document_id" in data

    def test_rag_search_flow(self, test_client):
        """Test the RAG search flow."""
        response = test_client.post(
            "/v1/rag/search",
            json={
                "query": "What is the capital of France?",
                "top_k": 5,
                "retrieval_strategy": "hybrid",
            },
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "sources" in data
        assert "latency_ms" in data
        assert "cost_usd" in data

    def test_rag_chat_flow(self, test_client):
        """Test the RAG chat flow."""
        response = test_client.post(
            "/v1/rag/chat",
            json={
                "query": "Tell me about France",
                "top_k": 5,
                "retrieval_strategy": "hybrid",
            },
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data

    def test_evaluate_rag_quality(self, test_client):
        """Test RAG evaluation workflow."""
        response = test_client.post(
            "/v1/rag/evaluate",
            json={
                "queries": ["What is the capital of France?"],
                "expected_answers": ["Paris"],
                "metrics": ["faithfulness", "relevance"],
                "top_k": 5,
            },
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200

    def test_cache_stats(self, test_client):
        """Test getting cache statistics."""
        response = test_client.get(
            "/v1/rag/cache/stats",
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "size" in data or "hit_rate" in data

    def test_list_documents(self, test_client):
        """Test listing documents."""
        response = test_client.get(
            "/v1/rag/documents?page=1&page_size=10",
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200

    def test_delete_document(self, test_client):
        """Test document deletion."""
        response = test_client.delete(
            "/v1/rag/documents/test-doc-1",
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200

    def test_full_crud_flow(self, test_client):
        """Test complete CRUD lifecycle: upload -> list -> delete."""
        # Upload
        upload_response = test_client.post(
            "/v1/rag/documents/upload",
            files={"file": ("crud_test.txt", b"Test content for CRUD lifecycle.", "text/plain")},
            headers={"X-API-Key": "test-key"},
        )
        assert upload_response.status_code == 201
        doc_id = upload_response.json()["document_id"]

        # List - verify uploaded
        list_response = test_client.get(
            "/v1/rag/documents",
            headers={"X-API-Key": "test-key"},
        )
        assert list_response.status_code == 200

        # Delete
        delete_response = test_client.delete(
            f"/v1/rag/documents/{doc_id}",
            headers={"X-API-Key": "test-key"},
        )
        assert delete_response.status_code == 200

    def test_gateway_chat_completion(self, test_client):
        """Test gateway chat completion through API."""
        response = test_client.post(
            "/v1/gateway/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello!"}],
                "temperature": 0.7,
                "max_tokens": 100,
            },
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert "model" in data
        assert "usage" in data

    def test_gateway_list_models(self, test_client):
        """Test listing models through API."""
        response = test_client.get(
            "/v1/gateway/models",
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200

    def test_health_endpoints(self, test_client):
        """Test all health check endpoints."""
        # Full health
        response = test_client.get("/health")
        assert response.status_code == 200

        # Readiness
        response = test_client.get("/ready")
        assert response.status_code in (200, 503)

        # Liveness
        response = test_client.get("/live")
        assert response.status_code == 200

    def test_agent_run(self, test_client):
        """Test agent execution through API."""
        response = test_client.post(
            "/v1/agent/run",
            json={
                "task": "Search for information about Paris",
                "agent_type": "react",
                "tools": ["search"],
                "max_steps": 3,
                "model": "gpt-4o",
            },
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        assert "steps" in data
        assert "status" in data

    def test_prompt_render(self, test_client):
        """Test prompt template rendering through API."""
        response = test_client.post(
            "/v1/prompts/render",
            json={
                "template_name": "test_template",
                "variables": {"name": "World"},
            },
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "rendered" in data
        assert "token_count" in data
        assert "World" in data["rendered"]

    def test_mcp_list_tools(self, test_client):
        """Test MCP tools listing through API."""
        response = test_client.post(
            "/v1/mcp/tools/list",
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
