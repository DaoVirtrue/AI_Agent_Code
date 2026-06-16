"""Dialog state machine with 8 states and timeout detection.

Models conversation flow as a finite state machine with well-defined
transitions between dialog states. Includes timeout detection for
states that require user input within a time window.
"""

from __future__ import annotations

import time
from enum import Enum, auto
from typing import Callable


class DialogState(Enum):
    """Eight dialog states representing the conversation lifecycle."""
    IDLE = auto()             # Waiting for conversation to start
    GREETING = auto()         # Initial greeting exchange
    COLLECTING_INFO = auto()  # Gathering required information from user
    CONFIRMING = auto()       # Confirming collected information
    EXECUTING = auto()        # Performing the requested action
    WAITING_APPROVAL = auto() # Waiting for user approval to proceed
    HANDLING_ERROR = auto()   # Handling an error condition
    CLOSING = auto()          # Closing the conversation


class DialogFSM:
    """8-state dialog state machine with timeout detection.

    Models the conversation lifecycle with explicit state transitions.
    Each state has a defined set of valid transition events, and
    states that expect user input include a configurable timeout.

    Usage:
        fsm = DialogFSM(timeout_seconds=300)
        fsm.trigger("start")        # IDLE -> GREETING
        fsm.trigger("greeted")      # GREETING -> COLLECTING_INFO
        fsm.trigger("info_complete")# COLLECTING_INFO -> CONFIRMING
    """

    TRANSITIONS: dict[DialogState, list[str]] = {
        DialogState.IDLE: ["start"],
        DialogState.GREETING: ["greeted", "skip_greeting", "error"],
        DialogState.COLLECTING_INFO: ["info_complete", "timeout", "error", "cancel"],
        DialogState.CONFIRMING: ["confirmed", "rejected", "timeout", "cancel"],
        DialogState.EXECUTING: ["executed", "needs_approval", "error", "execution_failed"],
        DialogState.WAITING_APPROVAL: ["approved", "rejected", "timeout", "cancel"],
        DialogState.HANDLING_ERROR: ["recover", "retry", "fallback", "give_up"],
        DialogState.CLOSING: [],  # Terminal state
    }

    # Mapping from (current_state, event) -> next_state
    _TRANSITION_MAP: dict[tuple[DialogState, str], DialogState] = {
        (DialogState.IDLE, "start"): DialogState.GREETING,
        (DialogState.GREETING, "greeted"): DialogState.COLLECTING_INFO,
        (DialogState.GREETING, "skip_greeting"): DialogState.COLLECTING_INFO,
        (DialogState.GREETING, "error"): DialogState.HANDLING_ERROR,
        (DialogState.COLLECTING_INFO, "info_complete"): DialogState.CONFIRMING,
        (DialogState.COLLECTING_INFO, "timeout"): DialogState.CLOSING,
        (DialogState.COLLECTING_INFO, "error"): DialogState.HANDLING_ERROR,
        (DialogState.COLLECTING_INFO, "cancel"): DialogState.CLOSING,
        (DialogState.CONFIRMING, "confirmed"): DialogState.EXECUTING,
        (DialogState.CONFIRMING, "rejected"): DialogState.COLLECTING_INFO,
        (DialogState.CONFIRMING, "timeout"): DialogState.CLOSING,
        (DialogState.CONFIRMING, "cancel"): DialogState.CLOSING,
        (DialogState.EXECUTING, "executed"): DialogState.CLOSING,
        (DialogState.EXECUTING, "needs_approval"): DialogState.WAITING_APPROVAL,
        (DialogState.EXECUTING, "error"): DialogState.HANDLING_ERROR,
        (DialogState.EXECUTING, "execution_failed"): DialogState.HANDLING_ERROR,
        (DialogState.WAITING_APPROVAL, "approved"): DialogState.EXECUTING,
        (DialogState.WAITING_APPROVAL, "rejected"): DialogState.CLOSING,
        (DialogState.WAITING_APPROVAL, "timeout"): DialogState.CLOSING,
        (DialogState.WAITING_APPROVAL, "cancel"): DialogState.CLOSING,
        (DialogState.HANDLING_ERROR, "recover"): DialogState.COLLECTING_INFO,
        (DialogState.HANDLING_ERROR, "retry"): DialogState.EXECUTING,
        (DialogState.HANDLING_ERROR, "fallback"): DialogState.CLOSING,
        (DialogState.HANDLING_ERROR, "give_up"): DialogState.CLOSING,
    }

    def __init__(self, timeout_seconds: int = 300) -> None:
        """Initialize the dialog FSM.

        Args:
            timeout_seconds: Maximum seconds a state can remain active
                             before `check_timeout()` returns True.
                             Applicable to COLLECTING_INFO, CONFIRMING,
                             and WAITING_APPROVAL states.
        """
        self._state: DialogState = DialogState.IDLE
        self._state_entered_at: float = time.time()
        self._timeout_seconds = timeout_seconds
        self._transition_count: int = 0
        self._state_history: list[tuple[DialogState, float]] = [(DialogState.IDLE, self._state_entered_at)]
        self._on_transition_callbacks: dict[str, list[Callable[[DialogState, DialogState], None]]] = {}

    @property
    def state(self) -> DialogState:
        """Current dialog state."""
        return self._state

    def can_transition(self, event: str) -> bool:
        """Check whether a given event is valid in the current state.

        Args:
            event: The event name to check.

        Returns:
            True if the event can trigger a transition from the current state.
        """
        return event in self.TRANSITIONS.get(self._state, [])

    def trigger(self, event: str) -> bool:
        """Attempt to trigger a state transition with the given event.

        Args:
            event: The event name (must be valid for the current state).

        Returns:
            True if the transition was successful, False if the event
            is invalid for the current state.

        Raises:
            ValueError: If the event is valid per TRANSITIONS but has no
                        mapping in _TRANSITION_MAP (configuration error).
        """
        if not self.can_transition(event):
            return False

        key = (self._state, event)
        if key not in self._TRANSITION_MAP:
            raise ValueError(
                f"No transition mapping for state={self._state.name}, event={event}. "
                f"Update _TRANSITION_MAP."
            )

        old_state = self._state
        new_state = self._TRANSITION_MAP[key]
        now = time.time()

        self._state = new_state
        self._state_entered_at = now
        self._transition_count += 1
        self._state_history.append((new_state, now))

        # Fire callbacks
        self._fire_callbacks(event, old_state, new_state)

        return True

    def check_timeout(self) -> bool:
        """Check if the current state has exceeded its timeout.

        Only COLLECTING_INFO, CONFIRMING, and WAITING_APPROVAL are
        timeout-eligible states. IDLE, EXECUTING, and CLOSING never
        timeout via this method.

        Returns:
            True if the current state has timed out.
        """
        timeout_eligible = {
            DialogState.COLLECTING_INFO,
            DialogState.CONFIRMING,
            DialogState.WAITING_APPROVAL,
        }
        if self._state not in timeout_eligible:
            return False

        elapsed = time.time() - self._state_entered_at
        return elapsed > self._timeout_seconds

    def get_elapsed_time(self) -> float:
        """Get seconds elapsed since entering the current state."""
        return time.time() - self._state_entered_at

    def get_remaining_time(self) -> float:
        """Get seconds remaining before timeout in the current state."""
        return max(0.0, self._timeout_seconds - self.get_elapsed_time())

    def get_state_history(self) -> list[tuple[str, float]]:
        """Get the full state transition history with timestamps."""
        return [(s.name, ts) for s, ts in self._state_history]

    def get_available_events(self) -> list[str]:
        """Get all valid transition events for the current state."""
        return self.TRANSITIONS.get(self._state, [])

    def on_transition(self, event: str, callback: Callable[[DialogState, DialogState], None]) -> None:
        """Register a callback for a specific transition event.

        Args:
            event: The event name to listen for.
            callback: Called with (old_state, new_state) when the event fires.
        """
        if event not in self._on_transition_callbacks:
            self._on_transition_callbacks[event] = []
        self._on_transition_callbacks[event].append(callback)

    def _fire_callbacks(self, event: str, old_state: DialogState, new_state: DialogState) -> None:
        """Fire all registered callbacks for an event."""
        for cb in self._on_transition_callbacks.get(event, []):
            try:
                cb(old_state, new_state)
            except Exception:
                pass  # Callback errors should not break the FSM

    def reset(self) -> None:
        """Reset the FSM to IDLE state."""
        now = time.time()
        self._state = DialogState.IDLE
        self._state_entered_at = now
        self._transition_count = 0
        self._state_history = [(DialogState.IDLE, now)]

    def __repr__(self) -> str:
        return (
            f"DialogFSM(state={self._state.name}, "
            f"elapsed={self.get_elapsed_time():.1f}s, "
            f"transitions={self._transition_count})"
        )
