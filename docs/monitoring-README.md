## 监控与可观测性 (Monitoring)

### 模块概述

监控模块为 LLM 平台提供全面的可观测性基础设施。它基于 Prometheus 暴露关键业务指标（网关请求量、延迟、RAG 缓存命中率、Agent 步数、Token 用量、成本、熔断器状态、注入攻击次数、PII 检测数等），通过 OpenTelemetry 实现分布式链路追踪以可视化跨服务请求流，提供结构化 JSON 日志和分级日志管理，以及健康检查端点和完整的审计日志记录，满足生产环境运维和安全合规需求。

### 关键文件

- `metrics.py` - 定义并导出所有 Prometheus 指标（Counter、Histogram、Gauge），覆盖网关、RAG、Agent、Token、安全等维度
- `tracing.py` - OpenTelemetry 链路追踪：`setup_tracing` 初始化 TracerProvider，`trace_llm_call` 装饰器自动记录 LLM 调用 Span
- `logging_setup.py` - 基于 `structlog` 的 JSON 格式日志系统，支持分级输出和 Sentry 集成
- `health.py` - `HealthChecker`，检查数据库、Redis、Milvus、各服务商 API 的连通性
- `audit.py` - `AuditLogger`，记录所有敏感操作（API 调用、配置变更、权限操作）的全链路审计日志
- `alerts/` - 告警规则定义和通知通道

### 模块连接

`metrics` 被 `ai_gateway`、`rag_system`、`agent_system`、`security` 等业务模块在关键节点调用更新指标。`tracing` 在 `api` 中间件层和各模块异步任务中织入链路追踪。`health` 通过 `api/health_routes` 暴露 `/health` 端点供负载均衡器和 Kubernetes 探针使用。`audit` 记录 `api` 层和 Admin 路由的所有操作。

### 关键技术

Prometheus Python Client、OpenTelemetry OTLP Exporter、structlog 结构化日志、Sentry 错误追踪、健康检查端点模式、Redis Pub/Sub 告警分发。
