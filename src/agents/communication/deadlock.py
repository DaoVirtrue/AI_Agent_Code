"""
Deadlock detector for agent communication patterns.

Monitors message dependencies between agents and detects circular
wait conditions that indicate potential deadlocks.
"""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

from src.agents.communication.protocol import AgentMessage, CommunicationBus

logger = logging.getLogger(__name__)


@dataclass
class DependencyEdge:
    """A dependency edge between two agents."""
    from_agent: str
    to_agent: str
    started_at: float = field(default_factory=time.time)
    request_id: str = ""
    timeout: float = 30.0


class DeadlockDetector:
    """Detects circular wait conditions in agent message dependencies.

    Monitors pending requests between agents, building a dependency graph.
    A cycle in the dependency graph indicates a potential deadlock.

    Resolution strategies:
    - Notify: Alert via callback
    - Timeout: Let the oldest request in the cycle expire
    - Kill: Send a shutdown message to break the cycle

    Args:
        communication_bus: The CommunicationBus to monitor.
        check_interval: Seconds between deadlock checks (default 5).
        on_deadlock: Optional callback(cycle: list[str]) called on detection.
        auto_resolve: If True, automatically cancel the oldest request in the cycle.
    """

    def __init__(
        self,
        communication_bus: CommunicationBus | None = None,
        check_interval: float = 5.0,
        on_deadlock: Callable | None = None,
        auto_resolve: bool = False,
    ):
        self.communication_bus = communication_bus or CommunicationBus()
        self.check_interval = check_interval
        self.on_deadlock = on_deadlock
        self.auto_resolve = auto_resolve

        # Dependency tracking
        self._dependencies: dict[str, DependencyEdge] = {}
        self._agent_waiting_on: dict[str, set[str]] = defaultdict(set)

        self._running = False
        self._task: asyncio.Task | None = None
        self._deadlock_count = 0
        self._resolved_count = 0

    # ------------------------------------------------------------------
    # Dependency tracking
    # ------------------------------------------------------------------

    def track_request(self, message: AgentMessage) -> None:
        """Track a new outgoing request dependency.

        Args:
            message: The request message being sent.
        """
        if message.msg_type != "request":
            return

        self._dependencies[message.msg_id] = DependencyEdge(
            from_agent=message.sender,
            to_agent=message.receiver,
            request_id=message.msg_id,
            timeout=message.ttl,
        )
        self._agent_waiting_on[message.sender].add(message.receiver)

    def resolve_dependency(self, message: AgentMessage) -> None:
        """Resolve a dependency when a response is received.

        Args:
            message: The response (or error) message.
        """
        if message.correlation_id and message.correlation_id in self._dependencies:
            dep = self._dependencies.pop(message.correlation_id)
            self._agent_waiting_on[dep.from_agent].discard(dep.to_agent)
            if not self._agent_waiting_on[dep.from_agent]:
                del self._agent_waiting_on[dep.from_agent]

    # ------------------------------------------------------------------
    # Monitoring lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the deadlock detector background task."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._detect_loop())
        logger.info("Deadlock detector started (interval=%.1fs)", self.check_interval)

    async def stop(self) -> None:
        """Stop the deadlock detector."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Deadlock detector stopped.")

    async def _detect_loop(self) -> None:
        """Main detection loop."""
        while self._running:
            try:
                # Clean up expired dependencies
                self._clean_expired()

                # Check for cycles
                cycles = self._find_cycles()

                for cycle in cycles:
                    self._deadlock_count += 1
                    logger.warning("DEADLOCK DETECTED: cycle=%s", " -> ".join(cycle))

                    if self.on_deadlock:
                        try:
                            self.on_deadlock(cycle)
                        except Exception as e:
                            logger.warning("Deadlock callback failed: %s", e)

                    if self.auto_resolve:
                        await self._resolve_cycle(cycle)

                await asyncio.sleep(self.check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Deadlock detector error: %s", e)
                await asyncio.sleep(self.check_interval)

    # ------------------------------------------------------------------
    # Cycle detection
    # ------------------------------------------------------------------

    def _find_cycles(self) -> list[list[str]]:
        """Find all cycles in the current dependency graph.

        Uses DFS-based cycle detection.

        Returns:
            List of cycles, each cycle is a list of agent names.
        """
        cycles = []
        visited: set[str] = set()
        stack: set[str] = set()
        path: list[str] = []

        def dfs(agent: str) -> None:
            if agent in stack:
                # Found a cycle
                cycle_start = path.index(agent)
                cycles.append(path[cycle_start:] + [agent])
                return

            if agent in visited:
                return

            visited.add(agent)
            stack.add(agent)
            path.append(agent)

            for neighbor in self._agent_waiting_on.get(agent, set()):
                dfs(neighbor)

            path.pop()
            stack.discard(agent)

        for agent in list(self._agent_waiting_on.keys()):
            if agent not in visited:
                dfs(agent)

        return cycles

    def _clean_expired(self) -> None:
        """Remove expired dependency edges."""
        now = time.time()
        expired = []

        for req_id, dep in self._dependencies.items():
            if now - dep.started_at > dep.timeout:
                expired.append(req_id)

        for req_id in expired:
            dep = self._dependencies.pop(req_id, None)
            if dep:
                self._agent_waiting_on[dep.from_agent].discard(dep.to_agent)
                if not self._agent_waiting_on[dep.from_agent]:
                    del self._agent_waiting_on[dep.from_agent]
                logger.debug("Expired dependency: %s -> %s", dep.from_agent, dep.to_agent)

        if expired:
            logger.info("Cleaned up %d expired dependencies", len(expired))

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    async def _resolve_cycle(self, cycle: list[str]) -> None:
        """Automatically resolve a deadlock cycle.

        Strategy: find the oldest pending request in the cycle and
        send an error response to break the wait.

        Args:
            cycle: List of agent names in the cycle.
        """
        # Find dependences involved in the cycle
        cycle_deps = []
        for req_id, dep in self._dependencies.items():
            if dep.from_agent in cycle and dep.to_agent in cycle:
                cycle_deps.append((req_id, dep))

        if not cycle_deps:
            return

        # Resolve the oldest dependency
        cycle_deps.sort(key=lambda x: x[1].started_at)
        oldest_id, oldest_dep = cycle_deps[0]

        # Send an error response to break the wait
        if oldest_dep.from_agent in self._agent_waiting_on:
            self._agent_waiting_on[oldest_dep.from_agent].discard(oldest_dep.to_agent)
            if not self._agent_waiting_on[oldest_dep.from_agent]:
                del self._agent_waiting_on[oldest_dep.from_agent]

        self._dependencies.pop(oldest_id, None)
        self._resolved_count += 1

        logger.info(
            "Auto-resolved deadlock by canceling: %s -> %s",
            oldest_dep.from_agent, oldest_dep.to_agent,
        )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    @property
    def stats(self) -> dict:
        """Return deadlock detector statistics."""
        return {
            "active_dependencies": len(self._dependencies),
            "waiting_agents": len(self._agent_waiting_on),
            "deadlocks_detected": self._deadlock_count,
            "deadlocks_resolved": self._resolved_count,
            "is_running": self._running,
        }

    def get_dependency_graph(self) -> dict[str, list[str]]:
        """Return the current dependency graph.

        Returns:
            Dict mapping agent -> list of agents it's waiting on.
        """
        return {
            agent: sorted(waiting)
            for agent, waiting in self._agent_waiting_on.items()
        }

    def __repr__(self) -> str:
        return (
            f"DeadlockDetector(deps={len(self._dependencies)}, "
            f"detected={self._deadlock_count}, running={self._running})"
        )
