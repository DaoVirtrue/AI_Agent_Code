## AI 网关 (AI Gateway)

### 模块概述

AI 网关是整个平台所有 LLM API 调用的中央路由层，提供对多家 LLM 服务商（OpenAI、Anthropic、Azure 等）的统一抽象。它将请求路由、限流、负载均衡、熔断、降级、重试和缓存功能集成为一条可靠的请求处理链路，确保生产环境中 LLM 调用具备高可用性和弹性。

### 关键文件

- `gateway.py` - 网关核心路由器 `GatewayRouter`，编排完整的请求处理流程
- `provider_registry.py` - 服务商注册表，管理所有接入的 LLM 服务商及其模型配置
- `providers/` - 各 LLM 服务商的具体适配器实现（含 `base.py` 定义 `LLMRequest`/`LLMResponse`）
- `load_balancer.py` - 多实例负载均衡器，支持轮询、最少连接等策略
- `rate_limiter.py` - 基于令牌桶的本地 + Redis 分布式限流
- `circuit_breaker.py` - 熔断器，三态模型（关闭/打开/半开），自动恢复
- `fallback.py` - 降级链路管理器，按优先级依次尝试备选服务商
- `retry.py` - 指数退避重试策略，支持 jitter
- `cache.py` - LLM 响应缓存，支持语义缓存

### 模块连接

网关是平台所有 LLM 调用的唯一入口。`api` 模块的路由通过依赖注入获取 `GatewayRouter`，所有业务模块（agent_system、rag_system 等）的 LLM 调用均经过网关。网关与 `monitoring` 模块集成上报指标，与 `token_management` 协作统计用量，与 `security` 的注入防御联动进行内容检查。

### 关键技术

FastAPI 依赖注入、Redis 分布式限流、令牌桶算法、指数退避 + jitter 重试、熔断器三态模式（关闭/打开/半开）、语义缓存、惰性加载 Provider。
