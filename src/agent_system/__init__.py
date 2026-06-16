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

from agent_system.tools.base import BaseTool, ToolDefinition, ToolResult, ToolStatus
from agent_system.tools.registry import ToolRegistry
from agent_system.tools.sandbox import ExecutionSandbox
from agent_system.tools.security import ToolSecurityManager
from agent_system.patterns.react import ReActAgent
from agent_system.patterns.plan_execute import PlanExecuteAgent
from agent_system.patterns.rewoo import ReWOOAgent
from agent_system.patterns.reflection import ReflectionAgent
from agent_system.memory.short_term import ShortTermMemory
from agent_system.memory.long_term import LongTermMemory
from agent_system.memory.episodic import EpisodicMemory, Episode
from agent_system.memory.manager import MemoryManager
from agent_system.memory.consolidation import MemoryConsolidationEngine
from agent_system.memory.forgetting_curve import ForgettingCurve
from agent_system.memory.blackboard import SharedBlackboard
from agent_system.orchestration.sequential import SequentialOrchestrator
from agent_system.orchestration.hierarchical import HierarchicalOrchestrator
from agent_system.orchestration.debate import DebateOrchestrator
from agent_system.orchestration.escalation import EscalationOrchestrator
from agent_system.orchestration.blackboard import BlackboardOrchestrator
from agent_system.orchestration.auction import AuctionOrchestrator
from agent_system.orchestration.swarm import SwarmOrchestrator
from agent_system.langgraph_workflows.supervisor import SupervisorAgent
from agent_system.langgraph_workflows.conditional_router import ConditionalRouter
from agent_system.langgraph_workflows.human_in_loop import HumanInTheLoopAgent
from agent_system.communication.protocol import AgentMessage, CommunicationBus
from agent_system.communication.heartbeat import HeartbeatMonitor
from agent_system.communication.deadlock import DeadlockDetector
from agent_system.safety import SafetyGuard

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
