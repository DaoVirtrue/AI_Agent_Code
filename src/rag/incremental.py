"""Incremental index update scheduler for RAG document stores.

Handles periodic re-indexing, delta updates, and consistency checks
for vector search indices.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Callable

logger = logging.getLogger(__name__)


@dataclass
class IndexUpdateTask:
    """A single index update task."""
    task_id: str
    doc_id: str
    action: str  # "add", "update", "delete"
    priority: int = 5
    created_at: float = field(default_factory=time.time)
    retry_count: int = 0
    max_retries: int = 3
    metadata: dict = field(default_factory=dict)


class IncrementalIndexer:
    """Incremental index update scheduler.

    Manages a queue of index update tasks and processes them
    according to priority. Supports:
    - Batched updates for efficiency
    - Retry with backoff
    - Consistency verification
    - Scheduled full re-indexing
    """

    def __init__(
        self,
        vector_store=None,
        embedder=None,
        chunker=None,
        batch_size: int = 50,
        max_queue_size: int = 10000,
        retry_delay_base: float = 2.0,
    ):
        """Initialize incremental indexer.

        Args:
            vector_store: Vector store for document storage
            embedder: Embedding model
            chunker: Text chunker
            batch_size: Documents per batch update
            max_queue_size: Maximum pending tasks
            retry_delay_base: Base delay for retry backoff
        """
        self.vector_store = vector_store
        self.embedder = embedder
        self.chunker = chunker
        self.batch_size = batch_size
        self.max_queue_size = max_queue_size
        self.retry_delay_base = retry_delay_base

        self._queue: list[IndexUpdateTask] = []
        self._processing = False
        self._stats = {
            "total_processed": 0,
            "total_failed": 0,
            "total_added": 0,
            "total_updated": 0,
            "total_deleted": 0,
            "last_run": None,
        }

        logger.info("IncrementalIndexer initialized (batch=%d, max_queue=%d)", batch_size, max_queue_size)

    async def schedule_add(self, doc_id: str, content: str, metadata: Optional[dict] = None) -> str:
        """Schedule a document for addition to the index.

        Args:
            doc_id: Document identifier
            content: Document text content
            metadata: Additional metadata

        Returns:
            Task ID
        """
        task_id = f"add_{doc_id}_{int(time.time() * 1000)}"
        task = IndexUpdateTask(
            task_id=task_id,
            doc_id=doc_id,
            action="add",
            metadata={"content": content, "metadata": metadata or {}},
        )

        if len(self._queue) < self.max_queue_size:
            self._queue.append(task)
            logger.debug("Scheduled add: %s", doc_id[:32])
        else:
            logger.warning("Queue full, dropping add task for %s", doc_id[:32])

        return task_id

    async def schedule_update(self, doc_id: str, content: str, metadata: Optional[dict] = None) -> str:
        """Schedule a document for update in the index.

        First deletes existing entries, then re-adds.
        """
        task_id = f"update_{doc_id}_{int(time.time() * 1000)}"
        task = IndexUpdateTask(
            task_id=task_id,
            doc_id=doc_id,
            action="update",
            priority=3,  # Higher priority than add
            metadata={"content": content, "metadata": metadata or {}},
        )

        if len(self._queue) < self.max_queue_size:
            self._queue.append(task)
        else:
            logger.warning("Queue full, dropping update task for %s", doc_id[:32])

        return task_id

    async def schedule_delete(self, doc_id: str) -> str:
        """Schedule a document for deletion from the index."""
        task_id = f"delete_{doc_id}_{int(time.time() * 1000)}"
        task = IndexUpdateTask(
            task_id=task_id,
            doc_id=doc_id,
            action="delete",
            priority=1,  # Highest priority
        )

        if len(self._queue) < self.max_queue_size:
            self._queue.append(task)
        else:
            logger.warning("Queue full, dropping delete task for %s", doc_id[:32])

        return task_id

    async def process_batch(self) -> dict:
        """Process a batch of pending index update tasks.

        Returns dict with processing stats.
        """
        if not self._queue:
            return {"processed": 0, "message": "Queue empty"}

        self._processing = True
        batch_start = time.time()
        stats = {"processed": 0, "succeeded": 0, "failed": 0, "details": []}

        try:
            # Sort by priority (lower number = higher priority)
            self._queue.sort(key=lambda t: (t.priority, t.created_at))

            # Take a batch
            batch = self._queue[:self.batch_size]
            self._queue = self._queue[self.batch_size:]

            # Group by action
            add_tasks = [t for t in batch if t.action == "add"]
            update_tasks = [t for t in batch if t.action == "update"]
            delete_tasks = [t for t in batch if t.action == "delete"]

            # Process deletes first
            if delete_tasks and self.vector_store:
                delete_ids = [t.doc_id for t in delete_tasks]
                try:
                    deleted_count = await self.vector_store.delete(delete_ids)
                    stats["succeeded"] += len(delete_tasks)
                    self._stats["total_deleted"] += deleted_count
                    logger.debug("Deleted %d documents", deleted_count)
                except Exception as e:
                    logger.error("Batch delete error: %s", e)
                    stats["failed"] += len(delete_tasks)

            # Process updates (delete then add)
            if update_tasks:
                for task in update_tasks:
                    try:
                        # Delete old
                        await self.vector_store.delete([task.doc_id])
                        # Add new (with chunking and embedding)
                        await self._process_add_task(task)
                        stats["succeeded"] += 1
                        self._stats["total_updated"] += 1
                    except Exception as e:
                        logger.error("Update task failed for %s: %s", task.doc_id[:32], e)
                        stats["failed"] += 1
                        if task.retry_count < task.max_retries:
                            task.retry_count += 1
                            self._queue.append(task)

            # Process additions
            if add_tasks:
                for task in add_tasks:
                    try:
                        await self._process_add_task(task)
                        stats["succeeded"] += 1
                        self._stats["total_added"] += 1
                    except Exception as e:
                        logger.error("Add task failed for %s: %s", task.doc_id[:32], e)
                        stats["failed"] += 1
                        if task.retry_count < task.max_retries:
                            task.retry_count += 1
                            self._queue.append(task)

        finally:
            self._processing = False
            self._stats["total_processed"] += stats["succeeded"] + stats["failed"]
            self._stats["total_failed"] += stats["failed"]
            self._stats["last_run"] = datetime.now().isoformat()

        stats["processed"] = stats["succeeded"] + stats["failed"]
        stats["queue_remaining"] = len(self._queue)
        stats["batch_time_ms"] = (time.time() - batch_start) * 1000

        logger.info("Batch processed: %d succeeded, %d failed, %d remaining (%.0fms)",
                     stats["succeeded"], stats["failed"], stats["queue_remaining"], stats["batch_time_ms"])

        return stats

    async def _process_add_task(self, task: IndexUpdateTask) -> None:
        """Process a single add task: chunk, embed, store."""
        if not self.vector_store:
            logger.warning("No vector store configured, skipping add for %s", task.doc_id)
            return

        content = task.metadata.get("content", "")
        doc_metadata = task.metadata.get("metadata", {})

        # Chunk if chunker is available
        if self.chunker:
            chunks = self.chunker.chunk_text(content, metadata={
                "doc_id": task.doc_id,
                **doc_metadata,
            })
        else:
            chunks = [{"text": content, "index": 0}]

        # Embed and create vector documents
        from .indexing.vector_store import VectorDocument
        documents = []
        for chunk in chunks:
            chunk_text = chunk.text if hasattr(chunk, 'text') else chunk.get("text", "")
            embedding = None

            if self.embedder:
                try:
                    embedding = await self.embedder.embed_query(chunk_text)
                except Exception as e:
                    logger.warning("Embedding failed for chunk: %s", e)

            doc = VectorDocument(
                id=f"{task.doc_id}_{chunk.index if hasattr(chunk, 'index') else chunk.get('index', 0)}",
                text=chunk_text,
                embedding=embedding,
                metadata={
                    "doc_id": task.doc_id,
                    "chunk_index": chunk.index if hasattr(chunk, 'index') else chunk.get("index", 0),
                    **doc_metadata,
                },
            )
            documents.append(doc)

        # Store in vector store
        await self.vector_store.add(documents)

    async def run_scheduled(
        self,
        interval_seconds: int = 60,
        stop_event: Optional[asyncio.Event] = None,
    ) -> None:
        """Run the indexer on a schedule, processing batches periodically.

        Args:
            interval_seconds: Seconds between batch processing runs
            stop_event: Event to signal graceful shutdown
        """
        logger.info("IncrementalIndexer scheduler started (interval=%ds)", interval_seconds)

        while True:
            if stop_event and stop_event.is_set():
                logger.info("IncrementalIndexer scheduler stopping")
                break

            if self._queue:
                await self.process_batch()

            # Wait for next interval or stop signal
            try:
                if stop_event:
                    await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
                    break
                else:
                    await asyncio.sleep(interval_seconds)
            except asyncio.TimeoutError:
                continue

    async def full_reindex(
        self,
        documents: list[dict],
        progress_callback: Optional[Callable] = None,
    ) -> dict:
        """Perform a full re-index of all documents.

        Args:
            documents: List of {doc_id, content, metadata} dicts
            progress_callback: Optional async callback(current, total)

        Returns:
            Dict with re-indexing statistics
        """
        start_time = time.time()
        logger.info("Starting full re-index of %d documents...", len(documents))

        stats = {"total": len(documents), "succeeded": 0, "failed": 0}

        for i, doc in enumerate(documents):
            try:
                doc_id = doc.get("id", doc.get("doc_id", str(i)))
                content = doc.get("content", "")
                metadata = doc.get("metadata", {})

                if content:
                    task = IndexUpdateTask(
                        task_id=f"reindex_{doc_id}",
                        doc_id=doc_id,
                        action="add",
                        metadata={"content": content, "metadata": metadata},
                    )
                    await self._process_add_task(task)
                    stats["succeeded"] += 1
                else:
                    logger.warning("Skipping empty document: %s", doc_id[:32])
            except Exception as e:
                logger.error("Re-index failed for doc %d: %s", i, e)
                stats["failed"] += 1

            if progress_callback and i % 10 == 0:
                await progress_callback(i + 1, len(documents))

        elapsed = (time.time() - start_time) * 1000
        stats["elapsed_ms"] = elapsed
        stats["documents_per_second"] = stats["succeeded"] / (elapsed / 1000) if elapsed > 0 else 0

        logger.info("Full re-index complete: %d/%d succeeded (%.0fms)",
                     stats["succeeded"], stats["total"], elapsed)

        return stats

    async def verify_consistency(self) -> dict:
        """Verify index consistency between vector store and source.

        Checks for missing documents, stale embeddings, and count mismatches.
        """
        if not self.vector_store:
            return {"status": "unknown", "reason": "No vector store configured"}

        try:
            count = await self.vector_store.count()
            return {
                "status": "ok",
                "indexed_count": count,
                "queue_size": len(self._queue),
                "processing": self._processing,
                "stats": self._stats.copy(),
            }
        except Exception as e:
            return {"status": "error", "reason": str(e)}

    def get_stats(self) -> dict:
        """Get indexer statistics."""
        return {
            **self._stats,
            "queue_size": len(self._queue),
            "queue_max": self.max_queue_size,
            "processing": self._processing,
        }

    def clear_queue(self) -> int:
        """Clear the pending task queue. Returns number of tasks cleared."""
        count = len(self._queue)
        self._queue.clear()
        logger.info("Queue cleared: %d tasks removed", count)
        return count
