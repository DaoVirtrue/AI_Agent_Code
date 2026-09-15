"""Conversation Management Module.

Provides coreference resolution, context stitching, entity tracking,
dialog state machines, slot filling, clarification, persona management,
and tone adaptation for multi-turn conversational AI.
"""

from .coreference import CoreferenceResolver, ResolvedQuery
from .context_stitcher import ContextStitcher, ConversationHistory, ConversationTurn
from .entity_tracker import EntityTracker
from .fsm import DialogFSM, DialogState
from .slot_filling import SlotFiller, Slot
from .clarification import ClarificationEngine
from .persona import PersonaManager, Persona
from .tone_adapter import ToneAdapter

__all__ = [
    # Coreference
    "CoreferenceResolver",
    "ResolvedQuery",
    # Context Stitching
    "ContextStitcher",
    "ConversationHistory",
    "ConversationTurn",
    # Entity Tracking
    "EntityTracker",
    # FSM
    "DialogFSM",
    "DialogState",
    # Slot Filling
    "SlotFiller",
    "Slot",
    # Clarification
    "ClarificationEngine",
    # Persona
    "PersonaManager",
    "Persona",
    # Tone Adapter
    "ToneAdapter",
]
