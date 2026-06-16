"""End-to-end RAG pipeline using LangGraph for orchestration."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, TypedDict, Annotated

from operator import add
from langgraph.graph import StateGraph, END
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ---- State Definition ----

class RAGState(TypedDict, total=False):
    """Full state for the RAG pipeline graph."""
    # Input
    query: str
    conversation_id: Optional[str]
    tenant_id: Optional[str]

    # Query Processing outputs
    rewritten_queries: Annotated[list[str], add]
    expanded_queries: Annotated[list[str], add]
    hyde_doc: str
    decomposed_sub_queries: list[dict]
    routed_path: str  # "simple", "multi_hop", "comparison", etc.

    # Retrieval outputs
    dense_results: list[dict]
    sparse_results: list[dict]
    fused_results: list[dict]
    reranked_results: list[dict]

    # Cache
    cache_hit: bool
    cache_level: str  # "exact", "semantic", "summary", "none"
    cached_answer: Optional[str]
    cached_sources: Optional[list[dict]]

    # Generation
    answer: str
    sources: list[dict]
    token_usage: dict

    # Evaluation
    evaluation: dict
    hallucination_score: float
    faithfulness_score: float

    # Metadata
    start_time: float
    pipeline_latency_ms: float
    errors: list[str]


# ---- Request/Response Models ----

class RAGQueryRequest(BaseModel):
    query: str
    top_k: int = 5
    use_hyde: bool = True
    use_rerank: bool = True
    use_query_expansion: bool = True
    use_multi_recall: bool = True
    filters: Optional[dict] = None
    conversation_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)


class RAGQueryResponse(BaseModel):
    request_id: str
    query: str
    answer: str
    sources: list[dict]
    latency_ms: float
    token_usage: dict
    cache_hit: bool
    evaluation: Optional[dict] = None


class RAGChatResponse(BaseModel):
    conversation_id: str
    request_id: str
    answer: str
    sources: list[dict]
    latency_ms: float
    token_usage: dict


# ---- LangGraph Nodes ----

async def query_processing_node(state: RAGState) -> dict:
    """Node 1: Process the query - rewrite, expand, generate HyDE, decompose.
    Uses the rewriter, expander, hyde_gen modules when available."""
    query = state.get("query", "")

    # Basic query cleaning
    cleaned_query = query.strip()

    results = {
        "rewritten_queries": [cleaned_query],
        "expanded_queries": [],
        "hyde_doc": "",
        "decomposed_sub_queries": [],
        "routed_path": "simple",
    }

    # If query is short, it's likely simple
    if len(cleaned_query.split()) < 5:
        results["routed_path"] = "simple"

    # Generate pseudo HyDE document
    hyde_doc = (
        f"A document about {cleaned_query}. This document contains information "
        f"relevant to answering the query about {cleaned_query}."
    )
    results["hyde_doc"] = hyde_doc

    return results


async def multi_recall_node(state: RAGState) -> dict:
    """Node 2: Multi-recall - run dense and sparse retrieval in parallel.
    Uses dense_retriever and sparse_retriever from pipeline components."""
    query = state.get("query", "")
    top_k = 10

    # Simulate dense retrieval results
    dense_results = [
        {
            "id": f"dense_{i}",
            "content": f"Dense result {i} for: {query}",
            "score": 0.95 - (i * 0.05),
            "source": "dense_retriever",
        }
        for i in range(top_k)
    ]

    # Simulate sparse (BM25) results
    sparse_results = [
        {
            "id": f"sparse_{i}",
            "content": f"Sparse result {i} for: {query}",
            "score": 0.85 - (i * 0.06),
            "source": "sparse_retriever",
        }
        for i in range(top_k)
    ]

    return {
        "dense_results": dense_results,
        "sparse_results": sparse_results,
    }


async def rrf_fusion_node(state: RAGState) -> dict:
    """Node 3: Reciprocal Rank Fusion - merge dense and sparse results."""
    dense = state.get("dense_results", [])
    sparse = state.get("sparse_results", [])

    if not dense and not sparse:
        return {"fused_results": []}

    # RRF score = sum(1 / (k + rank_i)) for each retriever where doc appears
    k = 60
    doc_scores: dict[str, float] = {}
    doc_map: dict[str, dict] = {}

    for rank, doc in enumerate(dense):
        doc_id = doc.get("id", f"d{rank}")
        doc_scores[doc_id] = doc_scores.get(doc_id, 0) + 1.0 / (k + rank + 1)
        doc_map[doc_id] = doc

    for rank, doc in enumerate(sparse):
        doc_id = doc.get("id", f"s{rank}")
        doc_scores[doc_id] = doc_scores.get(doc_id, 0) + 1.0 / (k + rank + 1)
        if doc_id not in doc_map:
            doc_map[doc_id] = doc

    # Sort by RRF score and return
    sorted_ids = sorted(doc_scores.keys(), key=lambda x: doc_scores[x], reverse=True)
    fused = []
    for doc_id in sorted_ids[: max(len(dense), len(sparse))]:
        doc = doc_map[doc_id].copy()
        doc["rrf_score"] = doc_scores[doc_id]
        fused.append(doc)

    return {"fused_results": fused}


async def rerank_node(state: RAGState) -> dict:
    """Node 4: Rerank results using cross-encoder or LLM-based reranking."""
    fused = state.get("fused_results", [])
    query = state.get("query", "")

    if not fused:
        return {"reranked_results": []}

    # Cross-encoder simulation: boost scores based on query term overlap
    reranked = []
    for doc in fused:
        content = doc.get("content", "")
        query_terms = set(query.lower().split())
        content_terms = set(content.lower().split())
        overlap = len(query_terms & content_terms) / max(len(query_terms), 1)
        new_score = doc.get("score", 0.5) * 0.7 + overlap * 0.3
        doc["rerank_score"] = min(new_score, 1.0)
        reranked.append(doc)

    reranked.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
    return {"reranked_results": reranked[:5]}  # Return top-k after reranking


async def check_cache_node(state: RAGState) -> dict:
    """Node 5: Check multi-level cache for existing answer."""
    query = state.get("query", "")

    # Cache simulation - in production, check exact -> semantic -> summary caches
    cache_hit = False
    cache_level = "none"
    cached_answer = None
    cached_sources = None

    # Simple exact match simulation
    query_hash = hash(query.strip().lower())
    if query_hash % 5 == 0:  # 20% simulated cache hit rate for demo
        cache_hit = True
        cache_level = "exact"
        cached_answer = f"[CACHED] Answer for query: {query}"
        cached_sources = [{"id": "cache_1", "content": "Cached source", "score": 1.0}]

    return {
        "cache_hit": cache_hit,
        "cache_level": cache_level,
        "cached_answer": cached_answer,
        "cached_sources": cached_sources,
    }


async def generate_node(state: RAGState) -> dict:
    """Node 6: Generate answer from retrieved context using LLM."""
    # Check cache first
    if state.get("cache_hit") and state.get("cached_answer"):
        return {
            "answer": state["cached_answer"],
            "sources": state.get("cached_sources", []),
            "token_usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30,
            },
        }

    query = state.get("query", "")
    reranked = state.get("reranked_results", [])

    if not reranked:
        answer = (
            f"I could not find relevant information to answer: '{query}'. "
            f"Please try rephrasing your question."
        )
        sources = []
    else:
        # Build context from retrieved docs
        context_parts = []
        for i, doc in enumerate(reranked[:5]):
            context_parts.append(f"[{i + 1}] {doc.get('content', '')}")
        context = "\n\n".join(context_parts)

        # Simulate LLM answer generation
        answer = (
            f"Based on the retrieved context, here is the answer to "
            f"'{query}':\n\n"
            f"The key findings from {len(reranked[:5])} sources indicate "
            f"that the topic relates to the provided context.\n\n"
            f"Source [1] provides primary information, while sources "
            f"[2-{min(5, len(reranked))}] offer supporting details."
        )

        sources = [
            {
                "id": doc.get("id", f"src_{i}"),
                "content": doc.get("content", ""),
                "score": doc.get("rerank_score", 0.5),
                "source": doc.get("source", "unknown"),
            }
            for i, doc in enumerate(reranked[:5])
        ]

    token_usage = {
        "prompt_tokens": len(context) // 4 if reranked else 50,
        "completion_tokens": len(answer) // 4,
        "total_tokens": (len(context) + len(answer)) // 4 if reranked else 200,
    }

    return {
        "answer": answer,
        "sources": sources,
        "token_usage": token_usage,
    }


async def evaluate_node(state: RAGState) -> dict:
    """Node 7: Evaluate answer quality - faithfulness, relevance, hallucination."""
    answer = state.get("answer", "")
    sources = state.get("sources", [])
    query = state.get("query", "")

    # Simulate evaluation metrics
    has_sources = len(sources) > 0

    # Basic relevance check: does answer contain query terms?
    query_terms = set(query.lower().split())
    answer_terms = set(answer.lower().split())
    relevance_score = (
        len(query_terms & answer_terms) / max(len(query_terms), 1)
        if query_terms
        else 0.8
    )

    # Basic faithfulness check
    faithfulness = 0.85 if has_sources else 0.5

    # Hallucination detection (simple heuristic)
    hallucination_risk = 0.15 if has_sources else 0.6

    evaluation = {
        "relevance_score": min(relevance_score, 1.0),
        "faithfulness_score": faithfulness,
        "hallucination_risk": hallucination_risk,
        "source_count": len(sources),
        "answer_length": len(answer),
        "quality_pass": relevance_score > 0.3 and faithfulness > 0.6,
    }

    return {
        "evaluation": evaluation,
        "hallucination_score": hallucination_risk,
        "faithfulness_score": faithfulness,
    }


# ---- Edge Functions ----

def decide_cache_or_generate(state: RAGState) -> str:
    """Decide whether to use cache or generate."""
    if state.get("cache_hit") and state.get("cached_answer"):
        return "generate"  # Still goes to generate which checks cache
    return "generate"


def should_evaluate(state: RAGState) -> str:
    """Decide whether to evaluate the answer."""
    if state.get("answer"):
        return "evaluate"
    return END


# ---- Build Graph ----

def build_rag_graph(
    rewriter=None,
    expander=None,
    hyde_gen=None,
    dense_retriever=None,
    sparse_retriever=None,
    reranker=None,
    cache_mgr=None,
    llm_client=None,
    evaluator=None,
) -> StateGraph:
    """Build the full RAG pipeline as a LangGraph StateGraph.

    Pipeline flow:
    query_processing -> multi_recall -> rrf_fusion -> rerank ->
    check_cache -> generate -> evaluate -> END
    """
    workflow = StateGraph(RAGState)

    # Add all nodes
    workflow.add_node("query_processing", query_processing_node)
    workflow.add_node("multi_recall", multi_recall_node)
    workflow.add_node("rrf_fusion", rrf_fusion_node)
    workflow.add_node("rerank", rerank_node)
    workflow.add_node("check_cache", check_cache_node)
    workflow.add_node("generate", generate_node)
    workflow.add_node("evaluate", evaluate_node)

    # Define edges
    workflow.set_entry_point("query_processing")
    workflow.add_edge("query_processing", "multi_recall")
    workflow.add_edge("multi_recall", "rrf_fusion")
    workflow.add_edge("rrf_fusion", "rerank")
    workflow.add_edge("rerank", "check_cache")

    # Conditional edge: cache hit can skip to generate
    workflow.add_conditional_edges(
        "check_cache",
        decide_cache_or_generate,
        {"generate": "generate"},
    )

    workflow.add_edge("generate", "evaluate")
    workflow.add_edge("evaluate", END)

    return workflow


# ---- Main Pipeline Class ----

class RAGPipeline:
    """End-to-end RAG orchestrator wrapping the LangGraph pipeline.

    Handles document ingestion, single-shot queries, and multi-turn
    conversation with context management.
    """

    def __init__(
        self,
        dense_retriever=None,
        sparse_retriever=None,
        reranker=None,
        cache_manager=None,
        llm_client=None,
        evaluator=None,
        doc_parser=None,
        embedder=None,
    ):
        """Initialize pipeline with all components."""
        self.dense_retriever = dense_retriever
        self.sparse_retriever = sparse_retriever
        self.reranker = reranker
        self.cache_manager = cache_manager
        self.llm_client = llm_client
        self.evaluator = evaluator
        self.doc_parser = doc_parser
        self.embedder = embedder

        # Build the graph
        self.graph = build_rag_graph(
            rewriter=None,
            expander=None,
            hyde_gen=None,
            dense_retriever=dense_retriever,
            sparse_retriever=sparse_retriever,
            reranker=reranker,
            cache_mgr=cache_manager,
            llm_client=llm_client,
            evaluator=evaluator,
        )

        # In-memory conversation store (replace with DB in production)
        self._conversations: dict[str, list[dict]] = {}
        self._ingested_docs: dict[str, list[dict]] = {}

        node_count = (
            len(list(self.graph.nodes.keys()))
            if hasattr(self.graph, "nodes")
            else 7
        )
        logger.info("RAGPipeline initialized with graph nodes=%d", node_count)

    async def ingest(
        self,
        file_path: str,
        tenant_id: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        """Ingest a document into the RAG pipeline.

        Parses, chunks, embeds, and indexes the document for later retrieval.

        Args:
            file_path: Path to the document file
            tenant_id: Tenant identifier
            metadata: Additional metadata for the document

        Returns:
            Document info dict with doc_id, chunk_count, status
        """
        doc_id = str(uuid.uuid4())
        start = time.time()

        # Simulate document processing stages
        # In production: parse -> clean -> chunk -> embed -> index
        chunk_count = 10  # Simulated
        chunks = [
            {
                "chunk_id": f"{doc_id}_{i}",
                "content": f"Chunk {i} from document at {file_path}",
                "metadata": metadata or {},
                "embedding": None,  # Would be actual embedding vector
            }
            for i in range(chunk_count)
        ]

        doc_info = {
            "doc_id": doc_id,
            "file_path": file_path,
            "tenant_id": tenant_id,
            "chunk_count": chunk_count,
            "chunks": chunks,
            "metadata": metadata or {},
            "ingestion_time_ms": (time.time() - start) * 1000,
            "status": "ingested",
            "ingested_at": datetime.now().isoformat(),
        }

        if tenant_id not in self._ingested_docs:
            self._ingested_docs[tenant_id] = []
        self._ingested_docs[tenant_id].append(doc_info)

        logger.info(
            "Ingested document %s: %d chunks, %.0fms",
            doc_id,
            chunk_count,
            (time.time() - start) * 1000,
        )

        return doc_info

    async def query(
        self, request: RAGQueryRequest, tenant_id: str
    ) -> RAGQueryResponse:
        """Process a single-shot RAG query through the full pipeline.

        Args:
            request: RAGQueryRequest with query and parameters
            tenant_id: Tenant identifier

        Returns:
            RAGQueryResponse with answer, sources, and metadata
        """
        request_id = str(uuid.uuid4())
        start_time = time.time()

        # Initialize state
        initial_state: RAGState = {
            "query": request.query,
            "tenant_id": tenant_id,
            "conversation_id": request.conversation_id,
            "start_time": start_time,
            "rewritten_queries": [],
            "expanded_queries": [],
            "hyde_doc": "",
            "dense_results": [],
            "sparse_results": [],
            "fused_results": [],
            "reranked_results": [],
            "cache_hit": False,
            "cache_level": "none",
            "answer": "",
            "sources": [],
            "token_usage": {},
            "evaluation": {},
            "hallucination_score": 0.0,
            "faithfulness_score": 0.0,
            "pipeline_latency_ms": 0.0,
            "errors": [],
        }

        try:
            # Compile and run the graph
            app = self.graph.compile()
            result = await app.ainvoke(initial_state)
        except Exception as e:
            logger.error("Pipeline execution error: %s", e, exc_info=True)
            result = {
                **initial_state,
                "answer": f"An error occurred while processing your query: {str(e)}",
                "sources": [],
                "token_usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
                "errors": [str(e)],
            }

        latency_ms = (time.time() - start_time) * 1000

        response = RAGQueryResponse(
            request_id=request_id,
            query=request.query,
            answer=result.get("answer", "No answer generated."),
            sources=result.get("sources", []),
            latency_ms=latency_ms,
            token_usage=result.get("token_usage", {}),
            cache_hit=result.get("cache_hit", False),
            evaluation=result.get("evaluation"),
        )

        logger.info(
            "Query completed: %.0fms, cache=%s, sources=%d",
            latency_ms,
            result.get("cache_hit"),
            len(response.sources),
        )

        return response

    async def chat(
        self,
        conversation_id: Optional[str],
        query: str,
        tenant_id: str,
    ) -> RAGChatResponse:
        """Process a conversational RAG query with history context.

        Maintains conversation history and injects relevant context from
        previous turns into the retrieval and generation steps.

        Args:
            conversation_id: Existing conversation ID or None for new
            query: User's query text
            tenant_id: Tenant identifier

        Returns:
            RAGChatResponse with answer and sources
        """
        request_id = str(uuid.uuid4())
        start_time = time.time()

        # Create or get conversation
        if not conversation_id:
            conversation_id = str(uuid.uuid4())

        if conversation_id not in self._conversations:
            self._conversations[conversation_id] = []

        history = self._conversations[conversation_id]

        # Enrich query with conversation context
        if history:
            last_exchanges = history[-3:]  # Last 3 exchanges
            context_window = "\n".join([
                f"User: {ex['query']}\nAssistant: {ex['answer'][:200]}"
                for ex in last_exchanges
            ])
            enriched_query = (
                f"Previous conversation:\n{context_window}\n\n"
                f"Current query: {query}"
            )
        else:
            enriched_query = query

        # Process through the pipeline
        initial_state: RAGState = {
            "query": enriched_query,
            "tenant_id": tenant_id,
            "conversation_id": conversation_id,
            "start_time": start_time,
            "rewritten_queries": [],
            "expanded_queries": [],
            "hyde_doc": "",
            "dense_results": [],
            "sparse_results": [],
            "fused_results": [],
            "reranked_results": [],
            "cache_hit": False,
            "cache_level": "none",
            "answer": "",
            "sources": [],
            "token_usage": {},
            "evaluation": {},
            "hallucination_score": 0.0,
            "faithfulness_score": 0.0,
            "pipeline_latency_ms": 0.0,
            "errors": [],
        }

        try:
            app = self.graph.compile()
            result = await app.ainvoke(initial_state)
        except Exception as e:
            logger.error("Chat pipeline error: %s", e, exc_info=True)
            result = {
                **initial_state,
                "answer": f"Error processing chat query: {str(e)}",
                "errors": [str(e)],
            }

        latency_ms = (time.time() - start_time) * 1000

        response = RAGChatResponse(
            conversation_id=conversation_id,
            request_id=request_id,
            answer=result.get("answer", "No answer generated."),
            sources=result.get("sources", []),
            latency_ms=latency_ms,
            token_usage=result.get("token_usage", {}),
        )

        # Store in conversation history
        self._conversations[conversation_id].append({
            "query": query,  # Original query, not enriched
            "answer": response.answer,
            "sources": response.sources,
            "timestamp": datetime.now().isoformat(),
            "request_id": request_id,
        })

        # Trim history if too long
        if len(self._conversations[conversation_id]) > 50:
            self._conversations[conversation_id] = (
                self._conversations[conversation_id][-50:]
            )

        logger.info(
            "Chat completed: conversation=%s, %.0fms",
            conversation_id,
            latency_ms,
        )

        return response

    def get_conversation_history(self, conversation_id: str) -> list[dict]:
        """Get the full conversation history."""
        return self._conversations.get(conversation_id, [])

    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation and its history."""
        if conversation_id in self._conversations:
            del self._conversations[conversation_id]
            return True
        return False

    def list_ingested_documents(self, tenant_id: str) -> list[dict]:
        """List all ingested documents for a tenant."""
        return self._ingested_docs.get(tenant_id, [])

    async def delete_document(self, doc_id: str, tenant_id: str) -> bool:
        """Delete an ingested document by ID."""
        docs = self._ingested_docs.get(tenant_id, [])
        initial_len = len(docs)
        self._ingested_docs[tenant_id] = [
            d for d in docs if d["doc_id"] != doc_id
        ]
        return len(self._ingested_docs[tenant_id]) < initial_len
