## API 层 (API)

### 模块概述

API 层是基于 FastAPI 构建的 Web 服务层，是平台所有功能的对外接口。它采用应用工厂模式创建 FastAPI 实例，支持弹性启动（非核心服务失败时降级而非崩溃），通过依赖注入系统管理数据库会话、Redis 客户端、Token 计数器、网关路由器、租户认证等共享资源。中间件栈负责 CORS、请求日志、异常捕获、租户上下文注入和限流。路由层按功能域组织，提供 RESTful API 供前端 SPA 消费。

### 关键文件

- `app.py` - `create_app()` 工厂函数，创建 FastAPI 实例，注册所有路由和中间件，配置生命周期事件（启动初始化/优雅关闭）
- `dependencies.py` - FastAPI 依赖注入集合：`get_db`（数据库会话）、`get_redis`、`get_gateway`、`get_token_counter`、`get_current_tenant`（租户认证）、`require_scope`（权限校验）
- `middleware_stack.py` - 中间件栈：请求 ID 注入、访问日志、异常统一处理、租户上下文
- `routes/` - 按功能域拆分的路由模块：
  - `gateway_routes.py` - 网关管理（服务商/模型配置、路由规则）
  - `rag_routes.py` - RAG 文档上传/搜索/问答
  - `agent_routes.py` - Agent 创建/执行/结果查询
  - `prompt_routes.py` - 提示词模板 CRUD、版本管理、A/B 测试
  - `mcp_routes.py` - MCP 服务器/客户端连接管理
  - `admin_routes.py` - 管理后台（租户/用户/审计/统计）
  - `health_routes.py` - 健康检查
- `schemas/` - Pydantic 请求/响应模型定义

### 模块连接

API 层是平台所有后端模块的入口和集成点。路由调用各业务模块（agent_system、rag_system、prompt_engineering 等），依赖注入整合 `shared` 层的基础设施。前端 SPA 通过 HTTP/SSE 与此层通信。

### 关键技术

FastAPI 应用工厂、Pydantic v2 模型校验、async/await 全异步、SSE 流式响应、弹性启动（Try-Continue 模式）、中间件洋葱模型。
