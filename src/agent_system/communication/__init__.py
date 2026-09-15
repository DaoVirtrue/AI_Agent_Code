"""
Inter-agent communication system.
"""

from src.agent_system.communication.protocol import AgentMessage, CommunicationBus
from src.agent_system.communication.heartbeat import HeartbeatMonitor
from src.agent_system.communication.deadlock import DeadlockDetector

__all__ = [
    "AgentMessage",
    "CommunicationBus",
    "HeartbeatMonitor",
    "DeadlockDetector",
]
