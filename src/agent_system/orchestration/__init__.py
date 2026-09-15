"""
Multi-agent orchestration patterns.
"""

from src.agent_system.orchestration.sequential import SequentialOrchestrator
from src.agent_system.orchestration.hierarchical import HierarchicalOrchestrator
from src.agent_system.orchestration.debate import DebateOrchestrator
from src.agent_system.orchestration.escalation import EscalationOrchestrator
from src.agent_system.orchestration.blackboard import BlackboardOrchestrator
from src.agent_system.orchestration.auction import AuctionOrchestrator
from src.agent_system.orchestration.swarm import SwarmOrchestrator

__all__ = [
    "SequentialOrchestrator",
    "HierarchicalOrchestrator",
    "DebateOrchestrator",
    "EscalationOrchestrator",
    "BlackboardOrchestrator",
    "AuctionOrchestrator",
    "SwarmOrchestrator",
]
