"""Harness 层 — Agent 安全护栏（核心生产级思考体系之一）。

> 核心思想：**用工程确定性驾驭模型不确定性**。
> LLM 是不确定性的，Agent 循环若不套硬护栏，会无限循环、刷爆 Token 成本、
> 执行危险操作。Harness 让 Agent 能发挥智能，但每一步都受工程护栏约束。

组件：
- ``guard.py``        — 循环保护 / 成本上限 / 最大迭代 / 高危工具拦截
- ``verify.py``       — 独立校验器（**禁止 LLM 自判**）
- ``transaction.py``  — 业务事务 Prepare/Commit/Abort + 幂等 + 回滚栈
- ``checkpoint.py``   — 快照回放 + 断点恢复
"""

from src.harness.guard import Harness, HarnessConfig, HarnessViolation
from src.harness.verify import (
    Verifier,
    VerificationResult,
    SchemaVerifier,
    ContainsVerifier,
    CompositeVerifier,
)
from src.harness.transaction import (
    TransactionManager,
    TransactionResult,
    TransactionError,
    Operation,
)
from src.harness.checkpoint import CheckpointStore, Snapshot

__all__ = [
    "Harness",
    "HarnessConfig",
    "HarnessViolation",
    "Verifier",
    "VerificationResult",
    "SchemaVerifier",
    "ContainsVerifier",
    "CompositeVerifier",
    "TransactionManager",
    "TransactionResult",
    "TransactionError",
    "Operation",
    "CheckpointStore",
    "Snapshot",
]
