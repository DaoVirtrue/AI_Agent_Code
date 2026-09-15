"""Slot filling for multi-turn structured information gathering.

Manages required and optional slots with validation, cross-turn filling,
and intelligent prompting for missing required slots.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Slot:
    """A single information slot to fill during conversation.

    Attributes:
        name: Unique identifier for the slot.
        description: Human-readable description of what this slot captures.
        required: Whether this slot must be filled to complete.
        validator: Optional callable(value) -> bool.
        default: Default value if the slot is never filled.
        prompt: The prompt to ask the user when this slot is missing.
    """
    name: str
    description: str
    required: bool = True
    validator: Callable[[Any], bool] | None = None
    default: Any = None
    prompt: str = ""

    def __post_init__(self) -> None:
        if not self.prompt:
            self.prompt = f"Please provide {self.description}"


class SlotFiller:
    """Multi-turn slot filling manager.

    Tracks which slots have been filled, validates values, and
    generates prompts for the next missing required slot.
    Supports cross-turn filling (partial information provided
    across multiple user turns).

    Usage:
        slots = [
            Slot("name", "your full name", required=True),
            Slot("email", "your email address", validator=lambda v: "@" in v),
            Slot("department", "your department", required=False, default="General"),
        ]
        filler = SlotFiller(slots)
        filler.fill("name", "Zhang Wei")
        next_prompt = filler.get_next_prompt()  # -> "Please provide your email address"
    """

    def __init__(self, slots: list[Slot]) -> None:
        """Initialize with a list of slots to fill.

        Args:
            slots: List of Slot definitions.
        """
        self._slots: dict[str, Slot] = {}
        self._values: dict[str, Any] = {}
        self._fill_history: list[tuple[str, Any, bool]] = []  # (slot_name, value, success)

        for slot in slots:
            self._slots[slot.name] = slot
            if slot.default is not None:
                self._values[slot.name] = slot.default

    def fill(self, slot_name: str, value: Any) -> bool:
        """Attempt to fill a slot with a value.

        Args:
            slot_name: Name of the slot to fill.
            value: The value to assign.

        Returns:
            True if the value was accepted, False if validation failed
            or the slot does not exist.
        """
        if slot_name not in self._slots:
            self._fill_history.append((slot_name, value, False))
            return False

        slot = self._slots[slot_name]

        # Run validator if present
        if slot.validator is not None:
            try:
                if not slot.validator(value):
                    self._fill_history.append((slot_name, value, False))
                    return False
            except Exception:
                self._fill_history.append((slot_name, value, False))
                return False

        self._values[slot_name] = value
        self._fill_history.append((slot_name, value, True))
        return True

    def is_complete(self) -> bool:
        """Check if all required slots have been filled.

        Returns:
            True if every required slot has a value.
        """
        for slot in self._slots.values():
            if slot.required and slot.name not in self._values:
                return False
        return True

    def get_missing_slots(self) -> list[Slot]:
        """Get all required slots that are not yet filled.

        Returns:
            List of Slot objects for missing required slots.
        """
        return [
            slot for slot in self._slots.values()
            if slot.required and slot.name not in self._values
        ]

    def get_filled_values(self) -> dict[str, Any]:
        """Get all filled slot values (including defaults).

        Returns:
            Dictionary of slot_name -> value for all filled slots.
        """
        return dict(self._values)

    def get_next_prompt(self) -> str | None:
        """Get the prompt for the next missing required slot.

        Returns:
            The prompt string for the first missing required slot,
            or None if all required slots are filled.
        """
        missing = self.get_missing_slots()
        if missing:
            return missing[0].prompt
        return None

    def get_all_prompts(self) -> list[str]:
        """Get prompts for all missing required slots.

        Returns:
            List of prompt strings, one per missing required slot.
        """
        return [slot.prompt for slot in self.get_missing_slots()]

    def get_slot(self, slot_name: str) -> Slot | None:
        """Get a slot definition by name.

        Args:
            slot_name: The slot name.

        Returns:
            The Slot object, or None if not found.
        """
        return self._slots.get(slot_name)

    def get_value(self, slot_name: str) -> Any | None:
        """Get the current value of a slot.

        Args:
            slot_name: The slot name.

        Returns:
            The current value, or None if not filled.
        """
        return self._values.get(slot_name)

    def is_slot_filled(self, slot_name: str) -> bool:
        """Check if a specific slot has been filled.

        Args:
            slot_name: The slot name.

        Returns:
            True if the slot has a value.
        """
        return slot_name in self._values

    def get_progress(self) -> dict[str, Any]:
        """Get a progress summary of slot filling.

        Returns:
            Dictionary with total_required, filled_required,
            missing_required, optional_total, optional_filled,
            and completion_percentage.
        """
        required_slots = [s for s in self._slots.values() if s.required]
        optional_slots = [s for s in self._slots.values() if not s.required]

        filled_required = sum(1 for s in required_slots if s.name in self._values)
        filled_optional = sum(1 for s in optional_slots if s.name in self._values)

        return {
            "total_required": len(required_slots),
            "filled_required": filled_required,
            "missing_required": len(required_slots) - filled_required,
            "total_optional": len(optional_slots),
            "filled_optional": filled_optional,
            "completion_percentage": round(
                (filled_required / len(required_slots) * 100)
                if required_slots else 100.0, 1
            ),
            "missing_slot_names": [s.name for s in self.get_missing_slots()],
        }

    def fill_from_dict(self, data: dict[str, Any]) -> dict[str, bool]:
        """Bulk-fill slots from a dictionary.

        Args:
            data: Dictionary mapping slot_name -> value.

        Returns:
            Dictionary mapping slot_name -> success (bool).
        """
        results: dict[str, bool] = {}
        for name, value in data.items():
            results[name] = self.fill(name, value)
        return results

    def reset(self) -> None:
        """Reset all slots to unfilled state (re-applies defaults)."""
        self._values.clear()
        self._fill_history.clear()
        for slot in self._slots.values():
            if slot.default is not None:
                self._values[slot.name] = slot.default

    def __len__(self) -> int:
        return len(self._values)

    def __contains__(self, slot_name: str) -> bool:
        return slot_name in self._values

    def __repr__(self) -> str:
        progress = self.get_progress()
        return (
            f"SlotFiller(required={progress['filled_required']}/{progress['total_required']}, "
            f"optional={progress['filled_optional']}/{progress['total_optional']}, "
            f"complete={self.is_complete()})"
        )
