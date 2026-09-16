"""业务专家模块 — 可配置的角色化 Agent.

A business expert is a configured agent = 角色(role) + 提示词(system prompt)
+ 技能(skills/tools) + MCP(可用的工具集). The user defines an expert, and the
expert executes tasks by calling its bound tools (skills + MCP tools)
automatically via function calling.

The expert loop (function-calling) is:
    1. Build messages = [system: role+prompt] + [user: task]
    2. Call the LLM with bound tools
    3. If the LLM requests a tool call -> run the tool (with approval gate) -> append result -> repeat
    4. If the LLM returns a final answer -> done
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.core.tools import BaseTool, ToolDefinition, ToolResult, ToolStatus

logger = logging.getLogger(__name__)


@dataclass
class ExpertConfig:
    """Configuration for a business expert.

    Attributes:
        name: Expert name (e.g. "法务专家", "数据分析师").
        role: Role description injected into the system prompt.
        system_prompt: Custom system prompt (prepended to the role).
        skills: List of tool names this expert may call (from the registry).
        description: Short description for the expert catalog.
    """

    name: str
    role: str = ""
    system_prompt: str = ""
    skills: list[str] = field(default_factory=list)
    description: str = ""

    def build_system_prompt(self) -> str:
        parts = []
        if self.system_prompt:
            parts.append(self.system_prompt)
        if self.role:
            parts.append(f"你的角色：{self.role}")
        parts.append("你可以使用提供的工具来完成用户的任务。")
        return "\n".join(parts)


@dataclass
class ExpertResult:
    """Result of an expert run."""

    output: str
    tool_calls: list[dict] = field(default_factory=list)
    status: str = "completed"  # completed | error
    error: str | None = None


class BusinessExpert:
    """A configured business expert that executes tasks with bound tools.

    Args:
        config: ExpertConfig.
        llm: LLM object with an OpenAI-compatible tool-calling interface.
             It must expose ``chat(messages, tools) -> {content, tool_calls}``
             or a LangChain ``ainvoke`` with bound tools.
        tools: Dict of tool_name -> BaseTool available to this expert.
        approval_gate: Optional ApprovalGate for requiring user approval.
    """

    def __init__(
        self,
        config: ExpertConfig,
        llm: Any = None,
        tools: Optional[dict[str, BaseTool]] = None,
        approval_gate: Any = None,
    ):
        self.config = config
        self.llm = llm
        self.tools = {name: tools[name] for name in (tools or {}) if name in config.skills} if config.skills else (tools or {})
        self.approval_gate = approval_gate
        self._max_steps = 15

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------

    async def run(self, task: str) -> ExpertResult:
        """Execute a task as this expert."""
        if self.llm is None:
            return ExpertResult(output="专家未配置 LLM", status="error", error="no llm")

        messages = [
            {"role": "system", "content": self.config.build_system_prompt()},
            {"role": "user", "content": task},
        ]

        tool_calls_trace: list[dict] = []
        tool_schemas = self._build_tool_schemas()

        for _ in range(self._max_steps):
            try:
                response = await self._call_llm(messages, tool_schemas)
            except Exception as exc:  # noqa: BLE001
                return ExpertResult(output=f"专家执行失败: {exc}", status="error", error=str(exc), tool_calls=tool_calls_trace)

            # Extract tool calls
            requested = self._extract_tool_calls(response)
            if not requested:
                # Final answer
                return ExpertResult(
                    output=self._extract_content(response),
                    tool_calls=tool_calls_trace,
                    status="completed",
                )

            # Append the assistant message (with tool calls) to history
            messages.append(self._response_to_message(response))

            for tool_call in requested:
                name = tool_call["name"]
                args = tool_call.get("arguments", {})
                result = await self._run_tool(name, args)
                tool_calls_trace.append({"name": name, "arguments": args, "result": result})

                # Append tool result
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })

        return ExpertResult(
            output="达到最大步数限制",
            status="error",
            error="max steps",
            tool_calls=tool_calls_trace,
        )

    # ------------------------------------------------------------------
    # Tool execution (with approval gate)
    # ------------------------------------------------------------------

    async def _run_tool(self, name: str, args: dict) -> dict:
        """Run a bound tool, gating on approval if required."""
        tool = self.tools.get(name)
        if tool is None:
            return {"error": f"未知工具: {name}"}

        # Approval gate
        if tool.definition.requires_approval and self.approval_gate is not None:
            req = self.approval_gate.request(name, args)
            approved = await self.approval_gate.wait_for_decision(req.request_id)
            if not approved:
                return {"error": f"用户拒绝了工具 '{name}' 的执行", "approved": False}

        try:
            result: ToolResult = await tool.execute(**args)
            return {
                "status": result.status.value,
                "data": result.data,
                "error": result.error,
                "approved": True,
            }
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc), "approved": False}

    # ------------------------------------------------------------------
    # LLM interface helpers
    # ------------------------------------------------------------------

    async def _call_llm(self, messages: list[dict], tools: list[dict]):
        """Call the LLM with tools, supporting two interfaces."""
        # Interface 1: OpenAI-compatible chat() returning {content, tool_calls}
        if hasattr(self.llm, "chat"):
            return await self.llm.chat(messages, tools=tools)

        # Interface 2: DeepSeekLLM (ainvoke with messages)
        if hasattr(self.llm, "ainvoke"):
            # Build an OpenAI-style prompt with tool descriptions
            response = await self.llm.ainvoke(messages)
            return {"content": getattr(response, "content", str(response)), "tool_calls": []}

        raise RuntimeError("LLM must expose chat() or ainvoke()")

    def _extract_tool_calls(self, response) -> list[dict]:
        """Extract tool calls from an LLM response."""
        if not isinstance(response, dict):
            return []
        tool_calls = response.get("tool_calls") or []
        result = []
        for tc in tool_calls:
            if isinstance(tc, dict):
                fn = tc.get("function", tc)
                args = fn.get("arguments", "{}")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                result.append({"id": tc.get("id", ""), "name": fn.get("name", ""), "arguments": args})
        return result

    def _extract_content(self, response) -> str:
        if isinstance(response, dict):
            return response.get("content", "") or ""
        return getattr(response, "content", str(response))

    def _response_to_message(self, response) -> dict:
        """Convert an LLM response to a message dict (with tool calls)."""
        if isinstance(response, dict):
            content = response.get("content") or ""
            tool_calls = response.get("tool_calls") or []
            msg = {"role": "assistant", "content": content}
            if tool_calls:
                msg["tool_calls"] = tool_calls
            return msg
        return {"role": "assistant", "content": getattr(response, "content", str(response))}

    def _build_tool_schemas(self) -> list[dict]:
        """Build OpenAI-compatible tool schemas for the bound tools."""
        schemas = []
        for name, tool in self.tools.items():
            d = tool.definition
            schemas.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": d.description,
                    "parameters": {
                        "type": "object",
                        "properties": d.parameters.get("properties", {}),
                        "required": d.parameters.get("required", []),
                    },
                },
            })
        return schemas

    def __repr__(self) -> str:
        return f"BusinessExpert(name={self.config.name!r}, tools={list(self.tools.keys())})"
