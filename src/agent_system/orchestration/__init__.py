"""
Multi-agent orchestration patterns.
"""

from agent_system.orchestration.sequential import SequentialOrchestrator
from agent_system.orchestration.hierarchical import HierarchicalOrchestrator
from agent_system.orchestration.debate import DebateOrchestrator
from agent_system.orchestration.escalation import EscalationOrchestrator
from agent_system.orchestration.blackboard import BlackboardOrchestrator
from agent_system.orchestration.auction import AuctionOrchestrator
from agent_system.orchestration.swarm import SwarmOrchestrator

__all__ = [
    "SequentialOrchestrator",
    "HierarchicalOrchestrator",
    "DebateOrchestrator",
    "EscalationOrchestrator",
    "BlackboardOrchestrator",
    "AuctionOrchestrator",
    "SwarmOrchestrator",
]
