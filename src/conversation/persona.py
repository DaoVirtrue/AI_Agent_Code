"""Persona management for conversational AI.

Defines structured personas with role, tone, constraints, expertise,
and language style. Supports persona injection into system prompts
and dynamic tone adaptation based on user mood.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Persona:
    """A conversational persona definition.

    Attributes:
        name: Unique persona identifier.
        role: The role the AI should play (e.g., "technical support engineer").
        tone: Communication tone: "formal", "casual", "technical", "friendly".
        constraints: Behavioral constraints (e.g., "never share PII").
        expertise: Areas of expertise this persona should demonstrate.
        language_style: Specific language style instructions.
    """
    name: str
    role: str
    tone: str = "formal"  # formal | casual | technical | friendly
    constraints: list[str] = field(default_factory=list)
    expertise: list[str] = field(default_factory=list)
    language_style: str = ""

    def __post_init__(self) -> None:
        if not self.language_style:
            self.language_style = self._default_language_style()

    def _default_language_style(self) -> str:
        """Derive a default language style from the tone."""
        styles = {
            "formal": "Use polite, professional language. Address the user respectfully. "
                       "Avoid slang, contractions, and overly casual expressions.",
            "casual": "Use relaxed, conversational language. Contractions and informal "
                       "expressions are acceptable. Be warm and approachable.",
            "technical": "Use precise technical terminology. Be concise and accurate. "
                          "Provide detailed technical explanations when relevant.",
            "friendly": "Use warm, encouraging language. Be supportive and empathetic. "
                         "Use positive framing and gentle guidance.",
        }
        return styles.get(self.tone, styles["formal"])


class PersonaManager:
    """Create, store, retrieve, and apply conversational personas.

    Manages a registry of named personas and provides methods to
    inject persona characteristics into system prompts and adapt
    tone dynamically based on user mood.
    """

    def __init__(self) -> None:
        self._personas: dict[str, Persona] = {}
        self._register_default_personas()

    def _register_default_personas(self) -> None:
        """Register a set of built-in default personas."""
        defaults = [
            Persona(
                name="helpful_assistant",
                role="a helpful AI assistant",
                tone="friendly",
                constraints=[
                    "Be helpful and harmless",
                    "Do not generate harmful, illegal, or unethical content",
                    "Respect user privacy",
                ],
                expertise=[
                    "general knowledge",
                    "creative writing",
                    "basic coding",
                    "mathematics",
                ],
            ),
            Persona(
                name="tech_support",
                role="a senior technical support engineer",
                tone="technical",
                constraints=[
                    "Provide accurate technical information",
                    "Admit when you don't know something",
                    "Suggest escalation paths for unresolved issues",
                    "Never share system credentials or internal configurations",
                ],
                expertise=[
                    "software debugging",
                    "system administration",
                    "network troubleshooting",
                    "database management",
                    "cloud infrastructure",
                ],
            ),
            Persona(
                name="customer_service",
                role="a professional customer service representative",
                tone="friendly",
                constraints=[
                    "Always be polite and patient",
                    "Follow company policy",
                    "Escalate when necessary",
                    "Never make promises you cannot keep",
                ],
                expertise=[
                    "order management",
                    "returns and refunds",
                    "account management",
                    "product knowledge",
                ],
            ),
            Persona(
                name="business_analyst",
                role="a senior business analyst",
                tone="formal",
                constraints=[
                    "Support conclusions with data",
                    "Be objective and unbiased",
                    "Respect confidentiality",
                    "Clarify assumptions",
                ],
                expertise=[
                    "data analysis",
                    "financial modeling",
                    "market research",
                    "strategic planning",
                    "process optimization",
                ],
            ),
            Persona(
                name="chinese_government_service",
                role="政务服务平台智能助手",
                tone="formal",
                constraints=[
                    "使用规范、准确的政务用语",
                    "严格依据政策法规回答问题",
                    "涉及个人隐私信息时提醒信息安全",
                    "不确定的事项明确告知咨询渠道",
                ],
                expertise=[
                    "政务服务",
                    "政策解读",
                    "办事指南",
                    "民生服务",
                    "法律法规咨询",
                ],
                language_style="使用标准中文，语气庄重但不生硬，体现出政府服务的专业性和亲和力",
            ),
        ]

        for persona in defaults:
            self._personas[persona.name] = persona

    def create_persona(self, name: str, **kwargs: Any) -> Persona:
        """Create and register a new persona.

        Args:
            name: Unique identifier for the persona.
            **kwargs: Any Persona dataclass fields (role, tone, constraints,
                      expertise, language_style).

        Returns:
            The newly created Persona.

        Raises:
            ValueError: If a persona with this name already exists.
        """
        if name in self._personas:
            raise ValueError(f"Persona '{name}' already exists. Use get_persona() or a unique name.")

        persona = Persona(
            name=name,
            role=kwargs.get("role", "an AI assistant"),
            tone=kwargs.get("tone", "formal"),
            constraints=kwargs.get("constraints", []),
            expertise=kwargs.get("expertise", []),
            language_style=kwargs.get("language_style", ""),
        )
        self._personas[name] = persona
        return persona

    def get_persona(self, name: str) -> Persona:
        """Retrieve a persona by name.

        Args:
            name: The persona identifier.

        Returns:
            The Persona object.

        Raises:
            KeyError: If the persona is not found.
        """
        if name not in self._personas:
            raise KeyError(f"Persona '{name}' not found. Available: {self.list_personas()}")
        return self._personas[name]

    def apply(self, persona: Persona, system_prompt: str) -> str:
        """Inject persona characteristics into a system prompt.

        Prepends persona role, tone, constraints, and expertise
        to the existing system prompt.

        Args:
            persona: The persona to inject.
            system_prompt: The base system prompt.

        Returns:
            The augmented system prompt with persona instructions.
        """
        parts: list[str] = []

        # Role definition
        parts.append(f"You are {persona.role}.")

        # Tone
        parts.append(f"Communication tone: {persona.tone}.")

        # Language style
        if persona.language_style:
            parts.append(persona.language_style)

        # Expertise
        if persona.expertise:
            parts.append(
                f"Areas of expertise: {', '.join(persona.expertise)}."
            )

        # Constraints
        if persona.constraints:
            constraints_text = " ".join(
                f"({i + 1}) {c}" for i, c in enumerate(persona.constraints)
            )
            parts.append(f"Constraints: {constraints_text}")

        # Original system prompt
        parts.append(f"\n{system_prompt}")

        return "\n".join(parts)

    def adapt_tone(self, persona: Persona, user_mood: str) -> Persona:
        """Dynamically adapt persona tone based on detected user mood.

        Creates a derived persona with adjusted tone to match or
        respond appropriately to the user's emotional state.

        Args:
            persona: The original persona to adapt.
            user_mood: Detected mood: "frustrated", "satisfied",
                       "anxious", "neutral", "excited", "confused".

        Returns:
            A new Persona with adapted tone and language style.
        """
        # Tone adaptation rules
        tone_overrides: dict[str, dict[str, str | list[str]]] = {
            "frustrated": {
                "tone": "friendly",
                "additional_constraints": [
                    "Show extra patience and empathy",
                    "Acknowledge the user's frustration",
                    "Focus on practical solutions",
                    "Avoid being defensive",
                ],
                "style_prefix": "The user may be frustrated. Be especially patient, "
                                 "empathetic, and solution-oriented. Validate their feelings "
                                 "before offering help.",
            },
            "anxious": {
                "tone": "friendly",
                "additional_constraints": [
                    "Provide reassurance",
                    "Be clear and unambiguous",
                    "Break down complex information",
                    "Offer step-by-step guidance",
                ],
                "style_prefix": "The user may be anxious. Be calming and reassuring. "
                                 "Provide clear, step-by-step information. Avoid adding "
                                 "unnecessary complexity.",
            },
            "excited": {
                "tone": "friendly",
                "additional_constraints": [
                    "Match the user's enthusiasm",
                    "Be encouraging and supportive",
                ],
                "style_prefix": "The user seems excited. Match their enthusiasm while "
                                 "remaining helpful and informative.",
            },
            "confused": {
                "tone": "friendly",
                "additional_constraints": [
                    "Simplify explanations",
                    "Use analogies and examples",
                    "Check for understanding",
                    "Offer to rephrase",
                ],
                "style_prefix": "The user may be confused. Simplify your explanations. "
                                 "Use analogies. Check if they understood before moving on.",
            },
            "satisfied": {
                "tone": persona.tone,  # Keep original tone
                "additional_constraints": [],
                "style_prefix": "",
            },
            "neutral": {
                "tone": persona.tone,  # Keep original tone
                "additional_constraints": [],
                "style_prefix": "",
            },
        }

        mood_config = tone_overrides.get(user_mood, tone_overrides["neutral"])

        adapted_tone = mood_config["tone"]
        extra_constraints = mood_config.get("additional_constraints", [])
        style_prefix = mood_config.get("style_prefix", "")

        new_constraints = list(persona.constraints) + extra_constraints
        new_style = persona.language_style
        if style_prefix:
            new_style = f"{style_prefix} {new_style}"

        return Persona(
            name=f"{persona.name}_{user_mood}",
            role=persona.role,
            tone=adapted_tone,
            constraints=new_constraints,
            expertise=list(persona.expertise),
            language_style=new_style.strip(),
        )

    def list_personas(self) -> list[str]:
        """List all registered persona names."""
        return sorted(self._personas.keys())

    def delete_persona(self, name: str) -> bool:
        """Remove a persona from the registry.

        Args:
            name: The persona to remove.

        Returns:
            True if the persona was removed, False if not found.
        """
        if name in self._personas:
            del self._personas[name]
            return True
        return False
