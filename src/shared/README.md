## 共享基础设施 (Shared)

### 模块概述

共享基础设施模块是平台所有业务模块的公共基座，提供横切关注点（Cross-Cutting Concerns）的统一实现。它包含基于 YAML + 环境变量的分层配置管理、异步 SQLAlchemy 2.0 的数据库引擎和会话工厂、异步 Redis 客户端（含缓存助手和 Lua 令牌桶限流）、RabbitMQ + Celery 异步任务调度、层次化异常体系（精确映射 HTTP 4xx/5xx 状态码）、ULID 分布式 ID 生成、API 密钥哈希/验证/认证中间件、共享 TypedDict 类型定义，以及 Tenant/User/APIKey/PromptTemplate 等 ORM 模型。

### 关键文件

- `config.py` - `Settings`，Pydantic-settings 多层级配置（default.yaml <- {env}.yaml <- 环境变量），嵌套数据库/Redis/RabbitMQ/Milvus/网关/RAG/Agent/监控配置组
- `database.py` - 异步 SQLAlchemy 引擎、`async_sessionmaker` 工厂、`get_db` FastAPI 依赖
- `redis.py` - 异步 Redis 连接池、缓存 get/set/delete、Lua 令牌桶限流、Pub/Sub 发布订阅
- `broker.py` - Celery 应用工厂，定义 rag_ingestion/agent_execution/evaluation/notification 四个任务队列及死信队列
- `exceptions.py` - 层次化异常体系：`LLMPlatformError` -> Validation/Authentication/Authorization/RateLimit/Provider/CircuitBreaker/TokenBudget/ContextWindow/Tool/Agent/RAG 等子类
- `id_generator.py` - ULID（Crockford Base32）生成，支持 request_id、entity_id、short_id
- `security.py` - SHA-256 API 密钥哈希与验证、`get_current_tenant` FastAPI 认证依赖、基于 ContextVar 的请求级租户上下文、`require_scopes` 权限校验工厂
- `types.py` - 共享 TypedDict：`MessageDict`、`TokenUsage`、`RetrievalResult`、`StreamChunk`、`AgentStep`、`AgentRunResult`
- `models/` - SQLAlchemy ORM：Tenant、User、APIKey、Conversation、Document、ModelRegistry、PromptTemplate、RequestLog、Base 基类

### 模块连接

作为基座模块，`shared` 被几乎所有其他模块依赖。`config` 提供全平台统一配置，`database` 和 `redis` 提供数据存储基础设施，`exceptions` 提供统一错误语言，`security` 保护 API 层，`broker` 协调异步任务，`types` 定义跨模块契约。

### 关键技术

pydantic-settings 分层配置、SQLAlchemy 2.0 async/await、redis.asyncio 连接池、Celery + RabbitMQ 任务队列、Lua 原子令牌桶、Crockford Base32 ULID、SHA-256 + HMAC 密钥哈希、ContextVar 请求上下文。
