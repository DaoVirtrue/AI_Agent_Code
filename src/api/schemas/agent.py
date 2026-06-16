"""Agent API schemas for running and orchestrating agents."""

from typing import Optional
from pydantic import BaseModel, Field


class AgentStep(BaseModel):
    """A single step in an agent execution trace."""

    step_number: int = Field(..., description="Step number in the execution", ge=0)
    action: str = Field(..., description="Action taken by the agent")
    thought: Optional[str] = Field(None, description="Agent's reasoning/thought process")
    observation: Optional[str] = Field(None, description="Observation from the environment")
    tool_name: Optional[str] = Field(None, description="Tool used in this step")
    tool_input: Optional[dict] = Field(None, description="Input to the tool")
    tool_output: Optional[str] = Field(None, description="Output from the tool")
    elapsed_ms: float = Field(0, description="Time taken for this step", ge=0)
    tokens_used: int = Field(0, description="Tokens used in this step", ge=0)

    class Config:
        json_schema_extra = {
            "example": {
                "step_number": 1,
                "action": "search",
                "thought": "I need to search for the answer to the user's question",
                "observation": "Found 5 relevant results",
                "tool_name": "web_search",
                "tool_input": {"query": "capital of France"},
                "tool_output": "Paris is the capital of France.",
                "elapsed_ms": 250.5,
                "tokens_used": 150,
            }
        }


class AgentRunRequest(BaseModel):
    """Request to run an agent with a given task."""

    task: str = Field(..., description="Task for the agent to perform", min_length=1, max_length=50000)
    agent_type: str = Field(
        default="react",
        description="Agent architecture type",
        examples=["react", "plan_execute", "reflection", "tool_use"],
    )
    tools: Optional[list[str]] = Field(
        None,
        description="List of tool names available to the agent",
        examples=[["web_search", "calculator", "code_interpreter"]],
    )
    max_steps: int = Field(
        default=15,
        description="Maximum execution steps before stopping",
        ge=1,
        le=100,
    )
    model: str = Field(
        default="gpt-4o",
        description="Model to use for the agent",
    )
    temperature: float = Field(
        default=0.0,
        description="Temperature for agent reasoning (lower = more deterministic)",
        ge=0.0,
        le=2.0,
    )
    system_prompt: Optional[str] = Field(
        None,
        description="Custom system prompt for the agent",
    )
    verbose: bool = Field(
        default=False,
        description="Include detailed step information in response",
    )
    require_approval: bool = Field(
        default=False,
        description="Require human approval for tool executions",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "task": "Research the latest AI trends and create a summary report",
                "agent_type": "react",
                "tools": ["web_search", "summarize", "write_file"],
                "max_steps": 10,
                "model": "gpt-4o",
                "temperature": 0.0,
            }
        }


class AgentRunResponse(BaseModel):
    """Response from an agent execution."""

    run_id: str = Field(..., description="Unique run identifier")
    result: str = Field(..., description="Final agent output")
    status: str = Field(
        ...,
        description="Execution status",
        examples=["completed", "max_steps_reached", "cancelled", "error"],
    )
    steps: list[AgentStep] = Field(..., description="Execution trace of agent steps")
    total_steps: int = Field(..., description="Total steps taken", ge=0)
    token_usage: dict = Field(..., description="Aggregate token usage")
    elapsed_ms: float = Field(..., description="Total execution time in milliseconds", ge=0)
    cost_usd: float = Field(..., description="Estimated cost in USD", ge=0)
    loop_detected: bool = Field(False, description="Whether a loop was detected")

    class Config:
        json_schema_extra = {
            "example": {
                "run_id": "run-xyz789",
                "result": "Based on research, the top AI trends include...",
                "status": "completed",
                "steps": [],
                "total_steps": 5,
                "token_usage": {"prompt_tokens": 1200, "completion_tokens": 800, "total_tokens": 2000},
                "elapsed_ms": 3500.0,
                "cost_usd": 0.008,
                "loop_detected": False,
            }
        }


class OrchestrateRequest(BaseModel):
    """Request to orchestrate multiple agents for a complex task."""

    task: str = Field(..., description="Complex task requiring multiple agents", min_length=1)
    agents: list[dict] = Field(
        ...,
        description="Agent configurations",
        examples=[[
            {"name": "researcher", "agent_type": "react", "tools": ["web_search"]},
            {"name": "writer", "agent_type": "tool_use", "tools": ["write_file"]},
        ]],
    )
    workflow: str = Field(
        default="sequential",
        description="Orchestration workflow type",
        examples=["sequential", "parallel", "debate", "hierarchical"],
    )
    max_steps_total: int = Field(default=50, ge=1, le=200)
    model: str = Field(default="gpt-4o")

    class Config:
        json_schema_extra = {
            "example": {
                "task": "Research and write a report on quantum computing",
                "agents": [
                    {"name": "researcher", "agent_type": "react", "tools": ["web_search", "summarize"]},
                    {"name": "writer", "agent_type": "tool_use", "tools": ["write_file"]},
                ],
                "workflow": "sequential",
                "model": "gpt-4o",
            }
        }


class ApprovalDecision(BaseModel):
    """Human approval decision for an agent tool call."""

    approved: bool = Field(..., description="Whether the action is approved")
    comment: Optional[str] = Field(None, description="Optional comment for the decision")
    modified_input: Optional[dict] = Field(None, description="Modified tool input if adjusted")
