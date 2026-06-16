"""Streaming RAG service: combines token streaming with SSE, backpressure,
latency tracking, and security monitoring for end-to-end RAG responses.

This service orchestrates the full streaming pipeline:
1. Retrieve documents via the RAG pipeline
2. Build a prompt with retrieved context
3. Generate tokens (real LLM or simulated)
4. Format as SSE events
5. Apply backpressure for slow consumers
6. Track latency metrics
7. Scan for security issues
8. Send heartbeats to keep connections alive
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, AsyncIterator

from .sse_formatter import SSEFormatter
from .backpressure import BackpressureController
from .latency_tracker import LatencyTracker
from .stream_scanner import StreamingSecurityMonitor


class StreamingRAGService:
    """End-to-end streaming RAG service with SSE formatting, backpressure,
    latency tracking, and security monitoring.

    Orchestrates the complete streaming pipeline from document retrieval
    through token generation to SSE-formatted client delivery.

    Usage:
        service = StreamingRAGService(
            rag_pipeline=my_rag,
            sse_formatter=SSEFormatter(),
            backpressure=BackpressureController(max_size=100),
            latency_tracker=LatencyTracker(),
            security_monitor=my_monitor,
        )
        async for sse_event in service.stream_rag_response("What is RAG?", "tenant-1"):
            yield sse_event  # Send to HTTP client
    """

    def __init__(
        self,
        rag_pipeline: Any,
        sse_formatter: SSEFormatter,
        backpressure: BackpressureController,
        latency_tracker: LatencyTracker,
        security_monitor: StreamingSecurityMonitor,
    ) -> None:
        """Initialize the streaming RAG service.

        Args:
            rag_pipeline: A RAG pipeline object with a `retrieve` method
                          that returns a list of document dicts, and optionally
                          a `generate` or `stream_generate` async method
                          for LLM token generation.
            sse_formatter: SSEFormatter instance.
            backpressure: BackpressureController instance.
            latency_tracker: LatencyTracker instance.
            security_monitor: StreamingSecurityMonitor instance.
        """
        self._rag = rag_pipeline
        self._sse = sse_formatter
        self._bp = backpressure
        self._latency = latency_tracker
        self._security = security_monitor
        self._heartbeat_task: asyncio.Task | None = None

    async def stream_rag_response(
        self, query: str, tenant_id: str = "default"
    ) -> AsyncIterator[str]:
        """Execute the full streaming RAG pipeline.

        Pipeline stages:
        1. Retrieve relevant documents
        2. Build augmented prompt
        3. Stream tokens through security monitor
        4. Apply backpressure for slow consumers
        5. Format as SSE events
        6. Track latency metrics
        7. Send heartbeats

        Args:
            query: The user's query string.
            tenant_id: Tenant identifier for multi-tenant deployments.

        Yields:
            SSE-formatted event strings ready for HTTP response streaming.
        """
        request_id = str(uuid.uuid4())[:8]
        stream_id = f"rag-{request_id}"

        # Start latency tracking
        self._latency.start_request()

        # Start the heartbeat keep-alive
        heartbeat_task = asyncio.ensure_future(self._send_heartbeats(interval=15))
        self._heartbeat_task = heartbeat_task

        total_tokens = 0
        finish_reason = "stop"

        try:
            # --- Stage 1: Retrieve documents ---
            retrieved_docs = await self._retrieve_documents(query, tenant_id)

            # --- Stage 2: Build augmented prompt ---
            augmented_prompt = self._build_prompt(query, retrieved_docs)

            # --- Stage 3: Send metadata event ---
            metadata_event = self._sse.metadata_event({
                "request_id": request_id,
                "tenant_id": tenant_id,
                "query": query,
                "num_docs_retrieved": len(retrieved_docs),
                "model": getattr(self._rag, "model_name", "unknown"),
            })
            yield metadata_event

            # --- Stage 4: Signal stream start ---
            yield self._sse.stream_start_event(request_id)

            # --- Stage 5: Generate and stream tokens ---
            token_count = 0
            is_first_token = True

            # Get the token generator (real LLM or simulated)
            token_generator = self._get_token_generator(augmented_prompt)

            async for raw_token in token_generator:
                # Security scan
                safe, processed_token = await self._security.monitor_token(
                    raw_token, stream_id
                )

                if not safe:
                    finish_reason = "security_blocked"
                    yield self._sse.error_event(
                        "Response blocked due to security policy",
                        code="security_blocked",
                    )
                    break

                # Track latency
                if is_first_token:
                    self._latency.on_first_token()
                    is_first_token = False
                else:
                    self._latency.on_token()

                # Apply backpressure (blocks if consumer is slow)
                await self._bp.produce(processed_token)
                token_count += 1

                # Format as SSE token event
                sse_event = self._sse.token_event(processed_token)
                yield sse_event

            total_tokens = token_count

        except asyncio.CancelledError:
            finish_reason = "interrupted"
            total_tokens = token_count

        except Exception as exc:
            finish_reason = "error"
            yield self._sse.error_event(str(exc), code="stream_error")

        finally:
            # Cancel heartbeat
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

            # --- Stage 6: Send completion event ---
            latency_stats = self._latency.stats()
            bp_stats = self._bp.stats()

            yield self._sse.stream_end_event(
                request_id=request_id,
                total_tokens=total_tokens,
                finish_reason=finish_reason,
            )

            yield self._sse.done_event({
                "request_id": request_id,
                "total_tokens": total_tokens,
                "finish_reason": finish_reason,
                "latency": latency_stats,
                "backpressure": bp_stats,
                "security": self._security.get_detection_summary(),
            })

            # End latency tracking
            self._latency.end_request()

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    async def _retrieve_documents(self, query: str, tenant_id: str) -> list[dict]:
        """Retrieve relevant documents from the RAG pipeline.

        Args:
            query: The user's query.
            tenant_id: Tenant identifier.

        Returns:
            List of document dicts with at least 'content' and 'score' keys.
        """
        try:
            # If the RAG pipeline has an async retrieve method
            if hasattr(self._rag, "aretrieve"):
                return await self._rag.aretrieve(query, tenant_id=tenant_id)
            elif hasattr(self._rag, "retrieve"):
                result = self._rag.retrieve(query, tenant_id=tenant_id)
                # Handle sync methods by wrapping in asyncio
                if asyncio.iscoroutine(result):
                    return await result
                return result
            else:
                return []
        except Exception:
            return []

    def _build_prompt(self, query: str, documents: list[dict]) -> str:
        """Build an augmented prompt with retrieved context.

        Args:
            query: The user's query.
            documents: Retrieved document dicts.

        Returns:
            A formatted prompt string ready for LLM generation.
        """
        if not documents:
            return query

        context_parts: list[str] = []
        for i, doc in enumerate(documents, 1):
            content = doc.get("content", "")
            title = doc.get("title", "")
            source = doc.get("source", "")
            score = doc.get("score", 0.0)

            header = f"[Document {i}]"
            if title:
                header += f" Title: {title}"
            if source:
                header += f" Source: {source}"
            if score:
                header += f" Relevance: {score:.2f}"

            context_parts.append(f"{header}\n{content}")

        context_text = "\n\n".join(context_parts)

        prompt = (
            "You are a helpful assistant. Use the following retrieved documents "
            "to answer the user's question. If the documents do not contain "
            "sufficient information, say so honestly.\n\n"
            f"=== Retrieved Documents ===\n"
            f"{context_text}\n"
            f"=== End Documents ===\n\n"
            f"User Question: {query}\n\n"
            f"Answer:"
        )

        return prompt

    async def _get_token_generator(self, prompt: str) -> AsyncIterator[str]:
        """Get a token-by-token async generator for the prompt.

        Tries to use the RAG pipeline's streaming generate method first,
        then falls back to a synchronous generate split into tokens,
        then to a simulated token generator.

        Args:
            prompt: The prompt to generate from.

        Yields:
            Individual token strings.
        """
        # Try async streaming generate
        if hasattr(self._rag, "astream_generate"):
            try:
                async for token in self._rag.astream_generate(prompt):
                    yield token
                return
            except Exception:
                pass

        # Try sync stream_generate
        if hasattr(self._rag, "stream_generate"):
            try:
                for token in self._rag.stream_generate(prompt):
                    yield str(token)
                    await asyncio.sleep(0)  # Yield control to event loop
                return
            except Exception:
                pass

        # Try async generate (non-streaming)
        if hasattr(self._rag, "agenerate"):
            try:
                result = await self._rag.agenerate(prompt)
                # Split the result into token-like chunks for streaming
                for char in result:
                    yield char
                    await asyncio.sleep(0.02)  # Small delay for streaming feel
                return
            except Exception:
                pass

        # Try sync generate
        if hasattr(self._rag, "generate"):
            try:
                result = self._rag.generate(prompt)
                if asyncio.iscoroutine(result):
                    result = await result
                for char in str(result):
                    yield char
                    await asyncio.sleep(0.02)
                return
            except Exception:
                pass

        # Fallback: simulated streaming
        fallback_text = (
            "Based on the retrieved documents, I can provide the following information. "
            "The documents contain relevant context about your query. "
            "Please note that the response quality depends on the retrieved content."
        )
        for word in fallback_text.split():
            yield word + " "
            await asyncio.sleep(0.03)

    async def _send_heartbeats(self, interval: int = 15) -> None:
        """Send periodic heartbeat events to keep the connection alive.

        Runs as a background task during the stream. Sends SSE heartbeat
        comments at the specified interval.

        Args:
            interval: Seconds between heartbeat pings.
        """
        try:
            while True:
                await asyncio.sleep(interval)
                # Heartbeats are produced to the backpressure queue but
                # are SSE comments that don't trigger client events
                hb = self._sse.heartbeat_event()
                await self._bp.produce(hb)
        except asyncio.CancelledError:
            pass

    async def get_stats(self) -> dict:
        """Get comprehensive streaming statistics.

        Returns:
            Dictionary with latency, backpressure, and security stats.
        """
        return {
            "latency": self._latency.stats(),
            "backpressure": self._bp.stats(),
            "security": self._security.get_detection_summary(),
        }

    async def close(self) -> None:
        """Clean up the service. Closes the backpressure controller."""
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        await self._bp.close()
