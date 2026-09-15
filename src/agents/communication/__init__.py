"""
Inter-agent communication system.
"""

from src.agents.communication.protocol import AgentMessage, CommunicationBus
from src.agents.communication.heartbeat import HeartbeatMonitor
from src.agents.communication.deadlock import DeadlockDetector

__all__ = [
    "AgentMessage",
    "CommunicationBus",
    "HeartbeatMonitor",
    "DeadlockDetector",
]
