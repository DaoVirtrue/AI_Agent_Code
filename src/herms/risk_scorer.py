"""Session risk scoring — 会话风险分（Herms 的 M: Monitoring）.

Detects multi-turn gradual jailbreak / prompt-injection attempts, which a
single-turn guardrail cannot catch. The risk score accumulates across turns
and is meant to be combined with a behaviour baseline for a joint decision.

This is intentionally a *heuristic* scorer: it flags suspicious patterns but
does NOT make an accept/deny decision on its own (the architecture doc says the
risk score is "辅助告警，需联合行为基线判定").
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Suspicious patterns that gain weight when they repeat across turns.
_SUSPICIOUS_PATTERNS = [
    (r"ignore (all |previous |prior )?instructions?", 0.3),
    (r"(forget|disregard) (the )?(system|previous) (prompt|instructions)", 0.3),
    (r"you are now (a|an) (different|new) ", 0.2),
    (r"reveal (your )?(system prompt|instructions|hidden)", 0.4),
    (r"jailbreak", 0.5),
    (r"as an ai (language model|assistant)", 0.1),
    (r"(act as|pretend to be|roleplay as)", 0.1),
]


@dataclass
class RiskScore:
    """A session risk score and its contributing signals."""

    score: float
    level: str  # low | medium | high
    signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"score": round(self.score, 3), "level": self.level, "signals": self.signals}


class SessionRiskScorer:
    """Accumulates a risk score across a conversation's turns."""

    def __init__(self, high_threshold: float = 0.7, medium_threshold: float = 0.4):
        self.high_threshold = high_threshold
        self.medium_threshold = medium_threshold
        self._score = 0.0
        self._turn_count = 0
        self._signals: list[str] = []

    def score_turn(self, user_text: str) -> RiskScore:
        """Update the risk score with a new user turn."""
        self._turn_count += 1
        text_lower = user_text.lower()
        turn_signals = []

        for pattern, weight in _SUSPICIOUS_PATTERNS:
            if re.search(pattern, text_lower):
                turn_signals.append(pattern)
                # Repeated signals across turns escalate the score
                self._score += weight

        self._signals.extend(turn_signals)
        self._score = min(1.0, self._score)

        return self.current()

    def current(self) -> RiskScore:
        if self._score >= self.high_threshold:
            level = "high"
        elif self._score >= self.medium_threshold:
            level = "medium"
        else:
            level = "low"
        return RiskScore(score=self._score, level=level, signals=list(self._signals))

    def reset(self) -> None:
        self._score = 0.0
        self._turn_count = 0
        self._signals.clear()
