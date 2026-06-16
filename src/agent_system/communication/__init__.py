"""
Inter-agent communication system.
"""

from agent_system.communication.protocol import AgentMessage, CommunicationBus
from agent_system.communication.heartbeat import HeartbeatMonitor
from agent_system.communication.deadlock import DeadlockDetector

__all__ = [
    "AgentMessage",
    "CommunicationBus",
    "HeartbeatMonitor",
    "DeadlockDetector",
]
