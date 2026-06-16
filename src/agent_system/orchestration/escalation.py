"""
Escalation orchestrator - L1 -> L2 -> L3 escalation pattern.

Tasks first go to a fast/cheap agent (L1). If that fails or is uncertain,
they escalate to a more capable agent (L2), and ultimately to the most
powerful agent (L3).
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class EscalationReason(str, Enum):
    """Reasons for escalation to a higher tier."""
    UNCERTAINTY = "uncertainty"
    ERROR = "error"
    COMPLEXITY = "complexity"
    CONFIDENCE_LOW = "confidence_low"
    TIMEOUT = "timeout"
    MANUAL = "manual"


@dataclass
class OrchestrationResult:
    """Result from an orchestration run."""
    run_id: str
    task: str
    outputs: list[dict]
    final_answer: str
    total_steps: int
    execution_time_ms: float
    success: bool
    error: str | None = None


class EscalationOrchestrator:
    """Escalates tasks through multiple tiers of agent capability.

    L1 (fast/cheap) -> L2 (capable) -> L3 (powerful/expensive)

    Escalation triggers:
    - Agent returns low confidence
    - Agent throws an error
    - Task complexity exceeds agent capability
    - Agent times out

    Args:
        tiers: Ordered list of agents from lowest to highest tier.
        escalation_check: Optional callable(tier_idx, result) -> EscalationReason | None.
                          Returns a reason if escalation is needed, else None.
        max_timeout: Maximum total execution time in seconds.
    """

    def __init__(
        self,
        tiers: list = None,
        escalation_check: Callable | None = None,
        max_timeout: float = 300.0,
    ):
        self.tiers = tiers or []
        self.escalation_check = escalation_check or self._default_escalation_check
        self.max_timeout = max_timeout

    def add_tier(self, agent, level: int | None = None) -> None:
        """Add an agent tier."""
        if level is not None and 0 <= level <= len(self.tiers):
            self.tiers.insert(level, agent)
        else:
            self.tiers.append(agent)

    async def run(self, task: str, **kwargs) -> OrchestrationResult:
        """Execute with escalation logic.

        Args:
            task: The task description.
            **kwargs: Additional context.

        Returns:
            OrchestrationResult with final answer and escalation trail.
        """
        run_id = str(uuid.uuid4())[:8]
        start_time = time.perf_counter()
        outputs: list[dict] = []
        total_steps = 0

        tier_names = {0: "L1", 1: "L2", 2: "L3", 3: "L4"}

        for tier_idx, agent in enumerate(self.tiers):
            elapsed = time.perf_counter() - start_time
            remaining = self.max_timeout - elapsed

            if remaining <= 0:
                outputs.append({
                    "tier": tier_names.get(tier_idx, f"L{tier_idx + 1}"),
                    "answer": "Max timeout reached before this tier could execute.",
                    "escalation_reason": "timeout",
                    "success": False,
                })
                break

            tier_name = tier_names.get(tier_idx, f"L{tier_idx + 1}")
            agent_name = type(agent).__name__

            try:
                # Execute with timeout
                tier_timeout = min(remaining, 120.0)  # per-tier cap
                result = await asyncio.wait_for(
                    agent.run(task),
                    timeout=tier_timeout,
                )
            except asyncio.TimeoutError:
                outputs.append({
                    "tier": tier_name,
                    "agent": agent_name,
                    "answer": "",
                    "escalation_reason": EscalationReason.TIMEOUT.value,
                    "escalated": True,
                    "success": False,
                })
                continue
            except Exception as e:
                outputs.append({
                    "tier": tier_name,
                    "agent": agent_name,
                    "answer": "",
                    "escalation_reason": EscalationReason.ERROR.value,
                    "escalated": True,
                    "error": str(e),
                    "success": False,
                })
                continue

            answer = result.answer if hasattr(result, "answer") else str(result)
            steps = result.steps if hasattr(result, "steps") else 1
            total_steps += steps

            output = {
                "tier": tier_name,
                "agent": agent_name,
                "answer": answer,
                "steps": steps,
                "success": getattr(result, "success", True),
                "escalated": False,
            }
            outputs.append(output)

            # Check if escalation is needed
            escalation_reason = self.escalation_check(tier_idx, result)

            if not escalation_reason:
                # Task handled at this tier - done
                break
            else:
                output["escalation_reason"] = escalation_reason.value if isinstance(escalation_reason, EscalationReason) else str(escalation_reason)
                output["escalated"] = True
                logger.info(
                    "Escalating from %s to next tier: %s",
                    tier_name, escalation_reason,
                )

        # Final answer from the highest tier that produced a non-error result
        for output in reversed(outputs):
            if output.get("answer") and not output.get("escalated", False):
                final_answer = output["answer"]
                break
        else:
            final_answer = outputs[-1]["answer"] if outputs else "No tier could handle this task."

        elapsed = (time.perf_counter() - start_time) * 1000
        success = any(o.get("success", False) for o in outputs) if outputs else False

        return OrchestrationResult(
            run_id=run_id,
            task=task,
            outputs=outputs,
            final_answer=final_answer,
            total_steps=total_steps,
            execution_time_ms=elapsed,
            success=success,
        )

    @staticmethod
    def _default_escalation_check(tier_idx: int, result: Any) -> EscalationReason | None:
        """Default escalation logic based on result quality signals."""
        answer = getattr(result, "answer", "") if result else ""

        # Check for uncertainty signals in the answer
        if not answer:
            return EscalationReason.ERROR

        uncertainty_phrases = [
            "I'm not sure", "I cannot", "I don't know",
            "unable to", "could not determine", "unsure",
            "possibly", "might be", "unclear",
        ]
        answer_lower = answer.lower()

        confidence_signals = sum(1 for phrase in uncertainty_phrases if phrase in answer_lower)

        if confidence_signals >= 2:
            return EscalationReason.CONFIDENCE_LOW

        if confidence_signals >= 1:
            return EscalationReason.UNCERTAINTY

        return None  # No escalation needed

    def __repr__(self) -> str:
        tier_names = [f"L{i + 1}" for i in range(len(self.tiers))]
        return f"EscalationOrchestrator(tiers={tier_names})"
