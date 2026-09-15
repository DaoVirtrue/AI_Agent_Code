"""
Agent System - Production-grade multi-agent orchestration framework.

Provides:
- ReAct, Plan-Execute, ReWOO, Reflection agent patterns via LangGraph
- Tool system with registry, sandboxed execution, and built-in tools
- Memory hierarchy (short-term, long-term, episodic) with consolidation
- Multi-agent orchestration (sequential, hierarchical, debate, swarm, etc.)
- LangGraph workflows (supervisor, conditional routing, human-in-the-loop)
- Inter-agent communication bus with heartbeat and deadlock detection
- Safety guardrails and content filtering
"""

__version__ = "1.0.0"

from src.core.tools import BaseTool, ToolDefinition, ToolResult, ToolStatus
from src.agents.tools.registry import ToolRegistry
from src.agents.tools.sandbox import ExecutionSandbox
from src.agents.tools.security import ToolSecurityManager
from src.agents.patterns.react import ReActAgent
from src.agents.patterns.plan_execute import PlanExecuteAgent
from src.agents.patterns.rewoo import ReWOOAgent
from src.agents.patterns.reflection import ReflectionAgent
from src.memory.short_term import ShortTermMemory
from src.memory.long_term import LongTermMemory
from src.memory.episodic import EpisodicMemory, Episode
from src.memory.manager import MemoryManager
from src.memory.consolidation import MemoryConsolidationEngine
from src.memory.forgetting_curve import ForgettingCurve
from src.memory.blackboard import SharedBlackboard
from src.agents.orchestration.sequential import SequentialOrchestrator
from src.agents.orchestration.hierarchical import HierarchicalOrchestrator
from src.agents.orchestration.debate import DebateOrchestrator
from src.agents.orchestration.escalation import EscalationOrchestrator
from src.agents.orchestration.blackboard import BlackboardOrchestrator
from src.agents.orchestration.auction import AuctionOrchestrator
from src.agents.orchestration.swarm import SwarmOrchestrator
from src.agents.langgraph_workflows.supervisor import SupervisorAgent
from src.agents.langgraph_workflows.conditional_router import ConditionalRouter
from src.agents.langgraph_workflows.human_in_loop import HumanInTheLoopAgent
from src.agents.communication.protocol import AgentMessage, CommunicationBus
from src.agents.communication.heartbeat import HeartbeatMonitor
from src.agents.communication.deadlock import DeadlockDetector
from src.agents.safety import SafetyGuard

__all__ = [
    "BaseTool", "ToolDefinition", "ToolResult", "ToolStatus",
    "ToolRegistry", "ExecutionSandbox", "ToolSecurityManager",
    "ReActAgent", "PlanExecuteAgent", "ReWOOAgent", "ReflectionAgent",
    "ShortTermMemory", "LongTermMemory", "EpisodicMemory", "Episode",
    "MemoryManager", "MemoryConsolidationEngine", "ForgettingCurve",
    "SharedBlackboard",
    "SequentialOrchestrator", "HierarchicalOrchestrator",
    "DebateOrchestrator", "EscalationOrchestrator",
    "BlackboardOrchestrator", "AuctionOrchestrator", "SwarmOrchestrator",
    "SupervisorAgent", "ConditionalRouter", "HumanInTheLoopAgent",
    "AgentMessage", "CommunicationBus", "HeartbeatMonitor", "DeadlockDetector",
    "SafetyGuard",
]
