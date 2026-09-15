"""
Heartbeat monitor for agent liveliness detection.

Periodically checks agent health via heartbeat messages and
detects agents that have become unresponsive.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from src.agents.communication.protocol import AgentMessage, CommunicationBus, MessageType

logger = logging.getLogger(__name__)


@dataclass
class AgentHealth:
    """Health status of a monitored agent."""
    agent_name: str
    last_heartbeat: float = 0.0
    is_alive: bool = False
    missed_heartbeats: int = 0
    total_messages: int = 0
    avg_response_time_ms: float = 0.0
    status: str = "unknown"


class HeartbeatMonitor:
    """Monitors agent health through periodic heartbeats.

    Sends heartbeat pings to registered agents and tracks their responses.
    Agents that miss too many heartbeats are flagged as unresponsive.

    Args:
        communication_bus: The CommunicationBus for sending heartbeats.
        interval: Seconds between heartbeat checks (default 10).
        max_missed: Maximum missed heartbeats before declaring an agent dead (default 3).
        on_death: Optional callback(agent_name) called when an agent is declared dead.
        on_recovery: Optional callback(agent_name) called when an agent recovers.
    """

    def __init__(
        self,
        communication_bus: CommunicationBus | None = None,
        interval: float = 10.0,
        max_missed: int = 3,
        on_death: Callable | None = None,
        on_recovery: Callable | None = None,
    ):
        self.communication_bus = communication_bus or CommunicationBus()
        self.interval = interval
        self.max_missed = max_missed
        self.on_death = on_death
        self.on_recovery = on_recovery

        self._agents: dict[str, AgentHealth] = {}
        self._running = False
        self._task: asyncio.Task | None = None
        self._monitor_name = "heartbeat_monitor"

    # ------------------------------------------------------------------
    # Agent registration
    # ------------------------------------------------------------------

    def register_agent(self, agent_name: str) -> None:
        """Register an agent for heartbeat monitoring.

        Args:
            agent_name: Name of the agent to monitor.
        """
        if agent_name not in self._agents:
            self._agents[agent_name] = AgentHealth(agent_name=agent_name)
            logger.info("Registered agent for heartbeat: %s", agent_name)

    def unregister_agent(self, agent_name: str) -> None:
        """Stop monitoring an agent."""
        self._agents.pop(agent_name, None)
        logger.info("Unregistered agent from heartbeat: %s", agent_name)

    # ------------------------------------------------------------------
    # Monitoring lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the heartbeat monitor background task."""
        if self._running:
            logger.warning("Heartbeat monitor is already running.")
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Heartbeat monitor started (interval=%.1fs, max_missed=%d)", self.interval, self.max_missed)

    async def stop(self) -> None:
        """Stop the heartbeat monitor."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Heartbeat monitor stopped.")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                for agent_name in list(self._agents.keys()):
                    await self._check_agent(agent_name)

                await asyncio.sleep(self.interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Heartbeat monitor error: %s", e)
                await asyncio.sleep(self.interval)

    # ------------------------------------------------------------------
    # Agent checking
    # ------------------------------------------------------------------

    async def _check_agent(self, agent_name: str) -> None:
        """Send heartbeat to an agent and process the response."""
        health = self._agents.get(agent_name)
        if not health:
            return

        start = time.perf_counter()

        try:
            # Send heartbeat request
            response = await asyncio.wait_for(
                self.communication_bus.request(
                    sender=self._monitor_name,
                    receiver=agent_name,
                    payload={"type": "heartbeat", "timestamp": time.time()},
                    timeout=self.interval * 0.8,
                ),
                timeout=self.interval * 0.9,
            )

            elapsed = (time.perf_counter() - start) * 1000

            # Update health
            health.last_heartbeat = time.time()
            health.total_messages += 1
            health.avg_response_time_ms = (
                health.avg_response_time_ms * 0.7 + elapsed * 0.3
            )

            # Agent was dead, now alive
            if not health.is_alive:
                health.is_alive = True
                health.status = "recovered"
                logger.warning("Agent '%s' has recovered!", agent_name)
                if self.on_recovery:
                    try:
                        self.on_recovery(agent_name)
                    except Exception as e:
                        logger.warning("Recovery callback failed: %s", e)

            health.missed_heartbeats = 0
            health.status = "healthy"

        except (asyncio.TimeoutError, Exception):
            health.missed_heartbeats += 1
            health.status = "missed"

            if health.missed_heartbeats >= self.max_missed:
                if health.is_alive:
                    health.is_alive = False
                    health.status = "dead"
                    logger.warning(
                        "Agent '%s' is DEAD (missed %d heartbeats)",
                        agent_name, health.missed_heartbeats,
                    )
                    if self.on_death:
                        try:
                            self.on_death(agent_name)
                        except Exception as e:
                            logger.warning("Death callback failed: %s", e)

    # ------------------------------------------------------------------
    # Health queries
    # ------------------------------------------------------------------

    def get_health(self, agent_name: str) -> AgentHealth | None:
        """Get health status for a specific agent.

        Args:
            agent_name: The agent name.

        Returns:
            AgentHealth or None if not registered.
        """
        return self._agents.get(agent_name)

    def get_all_health(self) -> dict[str, AgentHealth]:
        """Get health status for all registered agents.

        Returns:
            Dict mapping agent_name -> AgentHealth.
        """
        return dict(self._agents)

    def get_alive_agents(self) -> list[str]:
        """Get list of currently alive agents."""
        return [
            name for name, health in self._agents.items()
            if health.is_alive
        ]

    def get_dead_agents(self) -> list[str]:
        """Get list of dead/unresponsive agents."""
        return [
            name for name, health in self._agents.items()
            if not health.is_alive
        ]

    @property
    def is_running(self) -> bool:
        """Whether the heartbeat monitor is running."""
        return self._running

    def __repr__(self) -> str:
        alive = len(self.get_alive_agents())
        total = len(self._agents)
        return f"HeartbeatMonitor(agents={alive}/{total} alive, interval={self.interval}s)"
