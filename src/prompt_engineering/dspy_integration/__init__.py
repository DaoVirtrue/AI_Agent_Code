"""
DSPy Integration package for automatic prompt optimization.

Provides:
- DSPyPromptOptimizer: Wraps DSPy optimizers (MIPROv2, BootstrapFewShot)
- DSPyCompiler: Simplified RAG-focused compiler interface
"""

from .optimizer import DSPyPromptOptimizer
from .compiler import DSPyCompiler

__all__ = ["DSPyPromptOptimizer", "DSPyCompiler"]
