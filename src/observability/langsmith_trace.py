"""LangSmith tracing integration — 安全接入，缺 key 时零开销透传。

LangSmith (https://smith.langchain.com) 是 LangChain 官方的 LLM 调用追踪 /
评测平台：记录每次 LLM 调用的输入/输出/延迟/token，用于调试、回归测试、
数据集评测。

设计原则（保证「容器没 key 也能直接打开」）：
- **有 key 才追踪**：``LANGSMITH_API_KEY`` 为空时，装饰器原样返回原函数，
  完全 no-op，零开销、不报错、不打印骚扰日志。
- **未安装 langsmith 包时透传**：``import langsmith`` 失败（依赖未装）时同样
  透传，不因可观测性组件缺失而破坏核心调用路径。
- **弹性启动**：由 ``src.api.app`` 的 lifespan 通过 ``_try_init`` 调用，初始化
  失败只降级不影响服务启动。
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def _langsmith_available() -> bool:
    """Return True if the langsmith package is importable."""
    try:
        import langsmith  # noqa: F401
        return True
    except ImportError:
        return False


def _tracing_enabled() -> bool:
    """Return True only when an API key is present (tracing is opt-in)."""
    return bool(os.environ.get("LANGSMITH_API_KEY", "").strip())


def traceable_llm(func: Callable) -> Callable:
    """Decorate an LLM-calling async/sync function with LangSmith tracing.

    If LangSmith is unavailable OR no API key is configured, return ``func``
    unchanged (no tracing, zero overhead). Otherwise wrap with ``traceable``
    using ``run_type="llm"`` so runs appear as LLM traces in LangSmith.
    """
    if not _langsmith_available():
        logger.debug("langsmith not installed; LLM tracing disabled")
        return func
    if not _tracing_enabled():
        logger.debug("LANGSMITH_API_KEY not set; LLM tracing disabled (untraced)")
        return func

    try:
        from langsmith import traceable

        wrapped = traceable(run_type="llm", name=getattr(func, "__qualname__", func.__name__))(func)
        logger.info("LangSmith tracing enabled for %s", getattr(func, "__qualname__", func.__name__))
        return wrapped
    except Exception as exc:  # noqa: BLE001 - observability must never break the call path
        logger.warning("Failed to enable LangSmith tracing for %s: %s", func.__name__, exc)
        return func


def setup_langsmith() -> dict:
    """Report and (if key present) configure LangSmith tracing.

    Returns a dict describing the tracing status (for logs / diagnostics).
    """
    available = _langsmith_available()
    enabled = _tracing_enabled()

    if not available:
        status = "unavailable"
        logger.info("LangSmith tracing unavailable (langsmith package not installed)")
    elif not enabled:
        status = "disabled"
        logger.info("LangSmith tracing disabled (LANGSMITH_API_KEY not set; runs are untraced)")
    else:
        # Opt-in to tracing whenever a key is present, unless explicitly turned off.
        os.environ.setdefault("LANGSMITH_TRACING", "true")
        os.environ.setdefault("LANGSMITH_PROJECT", "llm-platform")
        status = "enabled"
        logger.info(
            "LangSmith tracing enabled (project=%s, endpoint=%s)",
            os.environ.get("LANGSMITH_PROJECT", "llm-platform"),
            os.environ.get("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"),
        )

    return {
        "langsmith_available": available,
        "langsmith_enabled": enabled,
        "status": status,
    }


def get_langsmith_client() -> Optional[Any]:
    """Return a LangSmith client when configured, else None.

    Used by evaluation / dataset workflows that need an explicit client.
    """
    if not _tracing_enabled() or not _langsmith_available():
        return None
    try:
        from langsmith import Client

        return Client()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to create LangSmith client: %s", exc)
        return None
