"""Prompt management API schemas for templates, rendering, and experiments."""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class RenderRequest(BaseModel):
    """Request to render a prompt template with variables."""

    template_name: str = Field(..., description="Name of the template to render")
    variables: dict = Field(..., description="Variable values for template rendering")
    version: Optional[int] = Field(None, description="Specific template version (defaults to latest)")

    class Config:
        json_schema_extra = {
            "example": {
                "template_name": "customer_support",
                "variables": {"user_name": "Alice", "issue": "Login not working"},
                "version": 3,
            }
        }


class RenderResponse(BaseModel):
    """Response for a rendered prompt template."""

    rendered: str = Field(..., description="Rendered prompt text")
    token_count: int = Field(..., description="Estimated token count of the rendered prompt", ge=0)
    template_name: str = Field(..., description="Template name used")
    version: int = Field(..., description="Template version used")
    variable_count: int = Field(..., description="Number of variables in the template")

    class Config:
        json_schema_extra = {
            "example": {
                "rendered": "You are a support agent. User Alice says: Login not working. Help them.",
                "token_count": 18,
                "template_name": "customer_support",
                "version": 3,
                "variable_count": 2,
            }
        }


class TemplateCreate(BaseModel):
    """Request to create a new prompt template."""

    name: str = Field(..., description="Template name (unique identifier)", min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    content: str = Field(..., description="Template content with {{variable}} placeholders")
    description: Optional[str] = Field(None, description="Human-readable description")
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")
    variables: list[str] = Field(default_factory=list, description="Required variable names")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "customer_support",
                "content": "You are a support agent. User {{user_name}} says: {{issue}}. Help them.",
                "description": "Customer support prompt template",
                "tags": ["support", "customer"],
                "variables": ["user_name", "issue"],
            }
        }


class TemplateResponse(BaseModel):
    """Template metadata and content."""

    name: str = Field(..., description="Template name")
    content: str = Field(..., description="Current template content")
    description: Optional[str] = Field(None, description="Template description")
    version: int = Field(..., description="Current version number")
    tags: list[str] = Field(default_factory=list, description="Tags")
    variables: list[str] = Field(default_factory=list, description="Required variables")
    created_at: Optional[str] = Field(None, description="ISO timestamp of creation")
    updated_at: Optional[str] = Field(None, description="ISO timestamp of last update")
    created_by: Optional[str] = Field(None, description="Creator identifier")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "customer_support",
                "content": "You are a support agent. User {{user_name}} says: {{issue}}.",
                "description": "Customer support prompt template",
                "version": 3,
                "tags": ["support"],
                "variables": ["user_name", "issue"],
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-06-01T14:30:00Z",
            }
        }


class ExperimentRequest(BaseModel):
    """Request to create a prompt evaluation experiment."""

    name: str = Field(..., description="Experiment name")
    template_names: list[str] = Field(..., description="Templates to compare")
    test_inputs: list[dict] = Field(..., description="Test variable sets")
    evaluator: str = Field(
        default="six_dimension",
        description="Evaluator to use",
        examples=["six_dimension", "llm_judge", "ragas"],
    )
    model: str = Field(default="gpt-4o", description="Model to use for generation")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "support_prompt_ab_test",
                "template_names": ["customer_support_v1", "customer_support_v2"],
                "test_inputs": [
                    {"user_name": "Bob", "issue": "Password reset"},
                    {"user_name": "Carol", "issue": "Billing question"},
                ],
                "evaluator": "six_dimension",
                "model": "gpt-4o",
            }
        }
