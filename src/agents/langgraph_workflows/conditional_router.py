"""
Conditional router - Intent-based routing to worker agents.

Analyzes a user query, classifies the intent, and routes to the
appropriate specialized agent or pipeline.
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Route:
    """A routing rule with intent pattern and target agent."""
    name: str
    description: str
    keywords: list[str]  # Keywords that trigger this route
    agent: Any  # Target agent with run() method
    priority: int = 10  # Lower number = higher priority


class ConditionalRouter:
    """Routes tasks to agents based on intent classification.

    Uses keyword matching (with optional LLM classification) to determine
    which agent or pipeline should handle a given task.

    Args:
        router_llm: Optional LLM for intent classification.
        default_agent: Agent to use when no route matches.
        use_llm_classification: Whether to use LLM for intent analysis.
    """

    def __init__(
        self,
        router_llm=None,
        default_agent=None,
        use_llm_classification: bool = False,
    ):
        self.router_llm = router_llm
        self.default_agent = default_agent
        self.use_llm_classification = use_llm_classification
        self.routes: dict[str, Route] = {}

    def add_route(self, route: Route) -> None:
        """Add a routing rule.

        Args:
            route: The Route to add.
        """
        if route.name in self.routes:
            logger.warning("Overwriting existing route: %s", route.name)
        self.routes[route.name] = route

    def remove_route(self, name: str) -> None:
        """Remove a route by name."""
        self.routes.pop(name, None)

    async def route(self, task: str) -> tuple[str, Any, float]:
        """Determine which route matches the task.

        Args:
            task: The task/query to route.

        Returns:
            Tuple of (route_name, agent, confidence_score).
        """
        task_lower = task.lower()

        # Try keyword matching first
        matches: list[tuple[Route, float]] = []

        for route in self.routes.values():
            score = 0.0
            for keyword in route.keywords:
                kw_lower = keyword.lower()
                if kw_lower in task_lower:
                    # Exact match gives higher score
                    score += 1.0
                    # Longer keyword match = stronger signal
                    score += len(kw_lower) / 100.0

            if score > 0:
                matches.append((route, score))

        if matches:
            # Sort by priority (lower = higher priority) then by score
            matches.sort(key=lambda x: (x[0].priority, -x[1]))
            best = matches[0]
            return best[0].name, best[0].agent, min(best[1] / 5.0, 1.0)

        # Try LLM classification if enabled
        if self.use_llm_classification and self.router_llm:
            try:
                route_name = await self._llm_classify(task)
                if route_name and route_name in self.routes:
                    route = self.routes[route_name]
                    return route.name, route.agent, 0.7
            except Exception as e:
                logger.warning("LLM route classification failed: %s", e)

        # Fallback to default
        if self.default_agent:
            return "default", self.default_agent, 0.3

        # No match - try first route
        if self.routes:
            first = next(iter(self.routes.values()))
            return first.name, first.agent, 0.1

        raise RuntimeError("No routes or default agent configured.")

    async def _llm_classify(self, task: str) -> str | None:
        """Use LLM to classify the task's intent and suggest a route.

        Args:
            task: The task description.

        Returns:
            Route name or None.
        """
        routes_desc = "\n".join(
            f"- {route.name}: {route.description} (keywords: {', '.join(route.keywords)})"
            for route in self.routes.values()
        )

        prompt = (
            "You are a task router. Classify the following task into exactly "
            "one of the available routes. Respond with just the route name.\n\n"
            "Available routes:\n"
            f"{routes_desc}\n\n"
            f"Task: {task}\n\n"
            "Route name:"
        )

        try:
            response = await self.router_llm.ainvoke([{"role": "user", "content": prompt}])
            text = response.content if hasattr(response, "content") else str(response)
            return text.strip().split("\n")[0].strip()
        except Exception:
            return None

    async def run(self, task: str, **kwargs) -> dict:
        """Route and execute the task.

        Args:
            task: The task description.
            **kwargs: Additional context.

        Returns:
            Dict with route_name, agent_name, result, and metadata.
        """
        start = time.perf_counter()

        try:
            route_name, agent, confidence = await self.route(task)
            agent_name = getattr(agent, "__class__", type(agent)).__name__

            result = await agent.run(task)
            answer = result.answer if hasattr(result, "answer") else str(result)
            steps = result.steps if hasattr(result, "steps") else 1
        except Exception as e:
            route_name = "error"
            agent_name = "unknown"
            confidence = 0.0
            answer = f"Routing/execution error: {e}"
            steps = 0

        elapsed = (time.perf_counter() - start) * 1000

        return {
            "route": route_name,
            "agent": agent_name,
            "confidence": confidence,
            "answer": answer,
            "steps": steps,
            "execution_time_ms": elapsed,
            "run_id": str(uuid.uuid4())[:8],
            "success": not answer.startswith("Routing/execution error"),
        }

    def list_routes(self) -> list[dict]:
        """List all configured routes."""
        return [
            {
                "name": r.name,
                "description": r.description,
                "keywords": r.keywords,
                "priority": r.priority,
            }
            for r in sorted(self.routes.values(), key=lambda x: x.priority)
        ]

    def __repr__(self) -> str:
        return f"ConditionalRouter(routes={list(self.routes.keys())})"
