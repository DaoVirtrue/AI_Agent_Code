"""Agentic RAG: Multi-tool agent for complex information retrieval.

Uses an agent with multiple tools (search, retrieve, calculate, etc.)
to answer complex queries that require multi-step reasoning.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Callable

logger = logging.getLogger(__name__)


@dataclass
class Tool:
    """A tool for the agentic RAG agent."""
    name: str
    description: str
    function: Callable
    parameters: dict = field(default_factory=dict)


class AgenticRAGProcessor:
    """Agent-based RAG with tool usage.

    An autonomous agent that can:
    - Search a vector database
    - Query external APIs
    - Perform calculations
    - Verify facts
    - Synthesize information from multiple tools

    The agent iteratively calls tools until it has enough information
    to answer the query, then synthesizes a final response.
    """

    SYSTEM_PROMPT = """You are a research agent with access to tools. To answer a question:
1. Think about what information you need
2. Call appropriate tools to gather information
3. Synthesize the results into a comprehensive answer

Always cite your sources. If you cannot find information, be honest about it.

Available tools:
{tool_descriptions}

Respond in JSON format:
{{"thought": "...", "action": "tool_name", "action_input": {{...}}}} or
{{"thought": "...", "final_answer": "..."}}"""

    def __init__(
        self,
        llm_client=None,
        max_steps: int = 10,
        tools: Optional[list[Tool]] = None,
    ):
        """Initialize agentic RAG processor.

        Args:
            llm_client: LLM for agent reasoning
            max_steps: Maximum agent steps
            tools: List of Tool objects
        """
        self.llm_client = llm_client
        self.max_steps = max_steps
        self.tools: dict[str, Tool] = {}

        if tools:
            for tool in tools:
                self.register_tool(tool)

        logger.info("AgenticRAGProcessor: max_steps=%d, tools=%d", max_steps, len(self.tools))

    def register_tool(self, tool: Tool) -> None:
        """Register a tool for the agent."""
        self.tools[tool.name] = tool
        logger.debug("Registered tool: %s", tool.name)

    def unregister_tool(self, tool_name: str) -> bool:
        """Remove a tool."""
        if tool_name in self.tools:
            del self.tools[tool_name]
            return True
        return False

    async def process(
        self,
        query: str,
        context: Optional[dict] = None,
    ) -> dict:
        """Process a query using agentic RAG.

        Args:
            query: User query
            context: Optional initial context

        Returns:
            Dict with {answer, steps, tool_calls, sources}
        """
        if not self.tools:
            return {
                "answer": f"No tools available to answer: {query}",
                "steps": [],
                "tool_calls": [],
                "sources": [],
            }

        steps = []
        tool_calls = []
        sources = []

        # Build tool descriptions
        tool_descriptions = "\n".join([
            f"- {name}: {tool.description}"
            for name, tool in self.tools.items()
        ])

        messages = [
            {
                "role": "system",
                "content": self.SYSTEM_PROMPT.format(tool_descriptions=tool_descriptions),
            },
            {"role": "user", "content": query},
        ]

        for step in range(self.max_steps):
            # Get agent's next action
            response = await self._get_agent_response(messages)

            if response is None:
                break

            if "final_answer" in response:
                steps.append({
                    "step": step + 1,
                    "type": "final_answer",
                    "content": response["final_answer"],
                })
                return {
                    "answer": response["final_answer"],
                    "steps": steps,
                    "tool_calls": tool_calls,
                    "sources": sources,
                }

            if "action" in response:
                tool_name = response.get("action", "")
                action_input = response.get("action_input", {})

                if tool_name not in self.tools:
                    logger.warning("Unknown tool: %s", tool_name)
                    continue

                # Execute tool
                try:
                    tool = self.tools[tool_name]
                    observation = await self._execute_tool(tool, action_input)
                    tool_call = {
                        "step": step + 1,
                        "tool": tool_name,
                        "input": action_input,
                        "observation": observation[:500],
                    }
                    tool_calls.append(tool_call)
                    steps.append({
                        "step": step + 1,
                        "type": "tool_call",
                        "tool": tool_name,
                        "thought": response.get("thought", ""),
                    })

                    # Add observation to messages
                    messages.append({
                        "role": "assistant",
                        "content": json.dumps(response, ensure_ascii=False),
                    })
                    messages.append({
                        "role": "user",
                        "content": f"Observation: {observation}",
                    })

                    # Collect sources
                    if "source" in str(action_input) or "document" in str(observation):
                        sources.append(tool_call)

                except Exception as e:
                    logger.error("Tool execution error (%s): %s", tool_name, e)
                    messages.append({
                        "role": "user",
                        "content": f"Error executing {tool_name}: {str(e)}",
                    })

        # Max steps reached
        return {
            "answer": "I was unable to find a complete answer within the step limit.",
            "steps": steps,
            "tool_calls": tool_calls,
            "sources": sources,
            "max_steps_reached": True,
        }

    async def _get_agent_response(self, messages: list[dict]) -> Optional[dict]:
        """Get the agent's next action from LLM."""
        if not self.llm_client:
            return {"final_answer": "Agent LLM not available"}

        # Combine messages into a prompt
        conversation = "\n".join([
            f"{m['role'].upper()}: {m['content'][:2000]}"
            for m in messages[-10:]
        ])

        try:
            if hasattr(self.llm_client, 'chat'):
                response = await self.llm_client.chat(
                    messages=[
                        {"role": m["role"], "content": m["content"]}
                        for m in messages
                    ]
                )
                response_text = str(response)
            elif hasattr(self.llm_client, 'generate'):
                response = await self.llm_client.generate(conversation)
                response_text = str(response)
            else:
                response_text = str(self.llm_client(conversation))

            # Parse JSON response
            return self._parse_json_response(response_text)
        except Exception as e:
            logger.error("Agent response error: %s", e)
            return None

    def _parse_json_response(self, text: str) -> Optional[dict]:
        """Parse JSON from LLM response."""
        # Try direct JSON parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from markdown code blocks
        import re
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find any JSON object in the text
        brace_match = re.search(r'\{.*\}', text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    async def _execute_tool(self, tool: Tool, params: dict) -> str:
        """Execute a tool with given parameters."""
        import asyncio

        if callable(tool.function):
            if asyncio.iscoroutinefunction(tool.function):
                result = await tool.function(**params)
            else:
                result = tool.function(**params)
        else:
            result = "Tool execution not available"

        return str(result)
