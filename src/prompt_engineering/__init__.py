"""
Prompt Engineering Package.

Provides a comprehensive toolkit for managing, optimizing, securing, and
monitoring LLM prompts in production. Sub-packages are imported lazily to
avoid circular dependencies and keep import times fast.

Sub-packages:
- engine: Jinja2 + Pydantic prompt rendering engine
- version_manager: Git-like version management for prompts
- security: Multi-layer prompt injection defense
- cost_optimizer: Prompt-level cost optimization strategies
- drift_detector: Distribution drift detection for prompt performance
- ab_testing: A/B experiment framework for prompts
- fewshot: Few-shot example selection and management
- dspy_integration: DSPy prompt optimization integration
"""

from src.prompt_engineering.engine import PromptEngine
from src.prompt_engineering.version_manager import PromptVersionManager
from src.prompt_engineering.security import InjectionDefense
from src.prompt_engineering.cost_optimizer import OptimizationResult, PromptCostOptimizer
from src.prompt_engineering.drift_detector import DriftResult, PromptDriftDetector

# Lazy imports for sub-packages that may have heavy dependencies
_LAZY_IMPORTS: dict[str, list[str]] = {
    "ab_testing": ["ABExperiment", "TrafficSplitter", "ABTestAnalyzer"],
    "fewshot": ["FewShotSelector", "MMRSelector", "FewShotRepository"],
    "dspy_integration": ["DSPyPromptOptimizer", "DSPyCompiler"],
}

__all__ = [
    # --- Core ---
    "PromptEngine",
    "PromptVersionManager",
    "PromptDriftDetector",
    "DriftResult",
    "InjectionDefense",
    "PromptCostOptimizer",
    "OptimizationResult",
    # --- A/B Testing ---
    "ABExperiment",
    "TrafficSplitter",
    "ABTestAnalyzer",
    # --- Few-Shot ---
    "FewShotSelector",
    "MMRSelector",
    "FewShotRepository",
    # --- DSPy ---
    "DSPyPromptOptimizer",
    "DSPyCompiler",
]


def __getattr__(name: str):
    """Lazy-load sub-package attributes on first access."""
    for module_name, attrs in _LAZY_IMPORTS.items():
        if name in attrs:
            import importlib

            mod = importlib.import_module(
                f"src.prompt_engineering.{module_name}"
            )
            attr = getattr(mod, name)
            # Cache in the module's globals so __getattr__ is not called again
            globals()[name] = attr
            return attr
    raise AttributeError(
        f"module 'src.prompt_engineering' has no attribute {name!r}"
    )
