"""
Episodic memory for tracking task history and lessons learned.

Stores episodes (task + outcome + lessons) and enables similarity-based
retrieval to inform future task execution with past experiences.
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Episode:
    """A record of a completed task with its outcome and lessons."""
    task: str
    outcome: str  # SUCCESS, PARTIAL, FAILURE
    lessons: list[str]
    timestamp: float
    agent_type: str
    steps: int
    tools_used: list[str]
    execution_time_ms: float = 0.0
    error: str | None = None
    metadata: dict = field(default_factory=dict)
    episode_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "episode_id": self.episode_id,
            "task": self.task,
            "outcome": self.outcome,
            "lessons": self.lessons,
            "timestamp": self.timestamp,
            "agent_type": self.agent_type,
            "steps": self.steps,
            "tools_used": self.tools_used,
            "execution_time_ms": self.execution_time_ms,
            "error": self.error,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Episode":
        return cls(**{k: v for k, v in data.items() if k != "episode_id"})


class EpisodicMemory:
    """Stores task episodes for experience-based reasoning.

    Maintains a history of past task executions and enables retrieval
    of similar episodes to inform current task strategies.

    Args:
        max_episodes: Maximum number of episodes to retain (FIFO).
        embedding_model: Optional embedding model for semantic similarity.
    """

    def __init__(self, max_episodes: int = 1000, embedding_model=None):
        self.max_episodes = max_episodes
        self._embedding_model = embedding_model
        self._episodes: deque[Episode] = deque()
        self._embeddings: dict[str, list[float]] = {}
        self._episode_counter = 0

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def add(self, episode: Episode) -> str:
        """Add a new episode to memory.

        Args:
            episode: The Episode to store.

        Returns:
            The episode_id assigned to the episode.

        Raises:
            ValueError: If the episode is missing required fields.
        """
        if not episode.task:
            raise ValueError("Episode must have a 'task' description.")

        if not episode.outcome:
            episode.outcome = "UNKNOWN"

        if not episode.timestamp:
            episode.timestamp = time.time()

        self._episode_counter += 1
        episode.episode_id = f"ep_{self._episode_counter}"

        # Generate embedding for semantic search
        if self._embedding_model:
            try:
                embedding_text = f"{episode.task}\n{episode.outcome}\n{' '.join(episode.lessons)}"
                if hasattr(self._embedding_model, "embed_query"):
                    self._embeddings[episode.episode_id] = \
                        self._embedding_model.embed_query(embedding_text)
                elif callable(self._embedding_model):
                    self._embeddings[episode.episode_id] = \
                        self._embedding_model(embedding_text)
            except Exception as e:
                logger.debug("Failed to generate episode embedding: %s", e)

        self._episodes.append(episode)

        # Evict oldest if over capacity
        while len(self._episodes) > self.max_episodes:
            evicted = self._episodes.popleft()
            self._embeddings.pop(evicted.episode_id, None)
            logger.debug("Evicted episode %s (FIFO capacity)", evicted.episode_id)

        logger.debug(
            "Added episode %s: task='%s' outcome=%s steps=%d",
            episode.episode_id, episode.task[:50], episode.outcome, episode.steps,
        )
        return episode.episode_id

    async def find_similar(self, task: str, k: int = 3) -> list[Episode]:
        """Find episodes similar to the given task.

        Uses cosine similarity on embeddings if available, otherwise
        falls back to keyword overlap matching.

        Args:
            task: The task description to find similar episodes for.
            k: Number of episodes to return.

        Returns:
            List of Episode objects sorted by similarity.
        """
        if not self._episodes:
            return []

        if self._embedding_model and self._embeddings:
            try:
                return await self._similarity_search(task, k)
            except Exception as e:
                logger.warning("Similarity search failed, falling back to keyword: %s", e)

        return self._keyword_search(task, k)

    async def get_lessons(self, task: str, max_lessons: int = 5) -> list[str]:
        """Get relevant lessons learned from similar past episodes.

        Args:
            task: The task description to find lessons for.
            max_lessons: Maximum number of lessons to aggregate.

        Returns:
            List of lesson strings from similar episodes.
        """
        similar = await self.find_similar(task, k=3)
        lessons = []
        seen = set()

        for episode in similar:
            for lesson in episode.lessons:
                lesson_key = lesson.lower().strip()[:50]
                if lesson_key not in seen:
                    seen.add(lesson_key)
                    lessons.append(lesson)
                    if len(lessons) >= max_lessons:
                        return lessons

        return lessons

    async def get_by_outcome(self, outcome: str, limit: int = 10) -> list[Episode]:
        """Get recent episodes with a specific outcome.

        Args:
            outcome: Outcome to filter by (SUCCESS, FAILURE, PARTIAL).
            limit: Maximum number of episodes to return.

        Returns:
            List of Episode objects matching the outcome.
        """
        matching = []
        for episode in reversed(self._episodes):
            if episode.outcome.upper() == outcome.upper():
                matching.append(episode)
                if len(matching) >= limit:
                    break
        return matching

    async def get_recent(self, limit: int = 10) -> list[Episode]:
        """Get the most recent episodes.

        Args:
            limit: Maximum number of episodes to return.

        Returns:
            List of recent Episode objects.
        """
        return list(reversed(self._episodes))[:limit]

    def get_stats(self) -> dict:
        """Return statistics about stored episodes.

        Returns:
            Dict with count, outcome distribution, avg steps, etc.
        """
        if not self._episodes:
            return {"count": 0}

        outcomes = {"SUCCESS": 0, "FAILURE": 0, "PARTIAL": 0, "UNKNOWN": 0}
        agent_types: dict[str, int] = {}
        total_steps = 0
        total_time = 0.0

        for ep in self._episodes:
            outcome_key = ep.outcome.upper()
            outcomes[outcome_key] = outcomes.get(outcome_key, 0) + 1
            agent_types[ep.agent_type] = agent_types.get(ep.agent_type, 0) + 1
            total_steps += ep.steps
            total_time += ep.execution_time_ms

        count = len(self._episodes)
        return {
            "count": count,
            "outcomes": outcomes,
            "agent_types": agent_types,
            "avg_steps": total_steps / count,
            "avg_time_ms": total_time / count,
            "success_rate": outcomes.get("SUCCESS", 0) / count,
        }

    # ------------------------------------------------------------------
    # Search implementations
    # ------------------------------------------------------------------

    async def _similarity_search(self, task: str, k: int) -> list[Episode]:
        """Cosine similarity search using embeddings."""
        # Generate query embedding
        if hasattr(self._embedding_model, "embed_query"):
            query_embedding = self._embedding_model.embed_query(task)
        elif callable(self._embedding_model):
            query_embedding = self._embedding_model(task)
        else:
            return self._keyword_search(task, k)

        # Compute cosine similarities
        import math
        scored = []
        for episode in self._episodes:
            emb = self._embeddings.get(episode.episode_id)
            if emb is None:
                continue

            # Cosine similarity
            dot = sum(a * b for a, b in zip(query_embedding, emb))
            norm_q = math.sqrt(sum(a * a for a in query_embedding))
            norm_e = math.sqrt(sum(b * b for b in emb))

            if norm_q > 0 and norm_e > 0:
                similarity = dot / (norm_q * norm_e)
            else:
                similarity = 0.0

            scored.append((similarity, episode))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [ep for _, ep in scored[:k]]

    def _keyword_search(self, task: str, k: int) -> list[Episode]:
        """Keyword overlap-based search fallback."""
        task_lower = task.lower()
        task_terms = set(task_lower.split())

        scored = []
        for episode in self._episodes:
            episode_text = (
                f"{episode.task.lower()} "
                f"{' '.join(episode.lessons).lower()}"
            )
            episode_terms = set(episode_text.split())

            # Jaccard similarity
            intersection = task_terms & episode_terms
            union = task_terms | episode_terms
            jaccard = len(intersection) / max(len(union), 1)

            # Outcome bonus: prefer successful episodes
            bonus = 0.2 if episode.outcome.upper() == "SUCCESS" else 0

            scored.append((jaccard + bonus, episode))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [ep for _, ep in scored[:k]]

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Clear all episodes."""
        self._episodes.clear()
        self._embeddings.clear()
        self._episode_counter = 0

    def prune_old(self, max_age_days: int = 90) -> int:
        """Remove episodes older than max_age_days.

        Returns:
            Number of episodes pruned.
        """
        cutoff = time.time() - (max_age_days * 86400)
        pruned = 0

        new_episodes = deque()
        for episode in self._episodes:
            if episode.timestamp >= cutoff:
                new_episodes.append(episode)
            else:
                self._embeddings.pop(episode.episode_id, None)
                pruned += 1

        self._episodes = new_episodes
        logger.info("Pruned %d old episodes (older than %d days)", pruned, max_age_days)
        return pruned

    def __len__(self) -> int:
        return len(self._episodes)

    def __repr__(self) -> str:
        return f"EpisodicMemory(episodes={len(self._episodes)}/{self.max_episodes})"
