"""Resilience layer — 韧性专章（文档第 11 部分）.

承载「断点重试、超时中断与恢复」的独立韧性机制：

- ``timeout.py``        — 分层超时表（内层 < 外层，≥6 层）
- ``retry_budget.py``   — 重试预算 + 重试风暴检测 + 指数退避
- ``recovery.py``       — 断点恢复 + 一致性校验
- ``reclaimer.py``      — 资源 TTL 回收

设计说明：
本层是「横向韧性层」，独立于模型网关。``ai_gateway`` 内部的
circuit_breaker / retry / rate_limiter / fallback / load_balancer / cache
属于网关自带的韧性能力（与 providers 耦合），保持不动；本层承载的是
跨层的通用韧性机制。
"""

from src.resilience.timeout import TimeoutPolicy, DEFAULT_TIMEOUTS, LAYER_ORDER, build_default_policy
from src.resilience.retry_budget import (
    RetryBudget,
    RetryBudgetConfig,
    exponential_backoff,
)
from src.resilience.recovery import (
    RecoveryManager,
    RecoveryResult,
    ConsistencyReport,
    check_context_present,
    check_idempotency_complete,
    check_cost_not_negative,
)
from src.resilience.reclaimer import ResourceReclaimer, Resource

__all__ = [
    "TimeoutPolicy",
    "DEFAULT_TIMEOUTS",
    "LAYER_ORDER",
    "build_default_policy",
    "RetryBudget",
    "RetryBudgetConfig",
    "exponential_backoff",
    "RecoveryManager",
    "RecoveryResult",
    "ConsistencyReport",
    "check_context_present",
    "check_idempotency_complete",
    "check_cost_not_negative",
    "ResourceReclaimer",
    "Resource",
]
