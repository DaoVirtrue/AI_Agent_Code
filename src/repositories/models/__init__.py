"""
ORM models – import every model here so Alembic and ``Base.metadata`` can discover them.
"""

from .api_key import APIKey
from .base import Base
from .conversation import Conversation, Message
from .document import Document
from .model_registry import ModelRegistry
from .prompt_template import PromptTemplate, PromptTemplateVersion
from .request_log import RequestLog
from .tenant import Tenant
from .user import User

__all__ = [
    "Base",
    "Tenant",
    "User",
    "APIKey",
    "ModelRegistry",
    "PromptTemplate",
    "PromptTemplateVersion",
    "Document",
    "Conversation",
    "Message",
    "RequestLog",
]
