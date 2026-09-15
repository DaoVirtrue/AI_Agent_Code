"""Harness 层 — Agent 安全护栏（核心生产级思考体系之一）。

> 核心思想：**用工程确定性驾驭模型不确定性**。
> LLM 是不确定性的，Agent 循环若不套硬护栏，会无限循环、刷爆 Token 成本、
> 执行危险操作。Harness 让 Agent 能发挥智能，但每一步都受工程护栏约束。

计划实现（M3 落地）：

- ``guard.py``      — 循环保护 / 成本上限 / 最大迭代护栏
- ``verify.py``     — 独立校验器（**禁止 LLM 自判**，防"子 Agent 欺骗主编排器"）
- ``transaction.py`` — 业务事务 Prepare/Commit/Abort + 幂等锁 + 回滚栈
- ``checkpoint.py``  — 快照回放（每步状态落库，支持断点恢复 + 一致性校验）

与其它层的关系：
- 依赖 ``src/core``（工具契约、异常）、``src/agents``（编排器）
- 被 ``src/services`` 编排层调用
"""

__all__: list[str] = []
