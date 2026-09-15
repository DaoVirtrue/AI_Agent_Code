"""Resilience layer — 韧性专章（对应文档第 11 部分）。

承载「断点重试、超时中断与恢复」的独立韧性机制：

- 分层超时表（≥6 层：MCP / 工具 / LLM / 子 Agent / 主 Agent / 任务）
- 重试预算 + 重试风暴检测
- 断点恢复 + 一致性校验
- Cancel / Pause 语义
- 资源 TTL 兜底

设计说明：
本层是「横向韧性层」，独立于模型网关。``ai_gateway`` 内部的
circuit_breaker / retry / rate_limiter / fallback / load_balancer / cache
属于网关自带的韧性能力（与 providers 耦合），保持不动；本层承载的是
跨层的通用韧性机制，在 M4 阶段落地实现。
"""
