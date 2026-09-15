## MCP 集成 (MCP Integration)

### 模块概述

MCP 集成模块实现 Model Context Protocol（MCP）的完整服务端和客户端能力。MCP 是 Anthropic 提出的标准化协议，用于 LLM 与外部工具/数据源之间的安全通信。本模块支持通过 JSON-RPC 2.0 协议暴露平台能力为 MCP 工具，同时也能作为客户端连接外部 MCP 服务器，将外部工具转换为 OpenAI Function Calling 格式供平台 Agent 使用，实现工具生态的双向互通。

### 关键文件

- `server/server.py` - `MCPServer`，完整的 MCP 服务端实现，支持 stdio 和 SSE 两种传输方式，处理 JSON-RPC 2.0 请求（tools/list、tools/call、resources/list、prompts/list）
- `client/client.py` - `MCPClient`，MCP 客户端，连接外部 MCP 服务器并管理会话生命周期
- `registry.py` - `MCPRegistry`，管理多个 MCP 服务器连接，支持健康检查和自动重连
- `server/` 子目录 - MCP 服务端的传输层、会话管理、资源/提示词注册等实现
- `client/` 子目录 - MCP 客户端的连接池、重连策略、工具格式转换（MCP <-> OpenAI）等

### 模块连接

MCP 服务端将平台的 RAG 搜索、Agent 工具、Prompt 模板等能力作为 MCP tools 暴露给外部 AI 应用（如 Claude Desktop）。MCP 客户端获取的外部工具注入 `agent_system.tools` 注册表供 Agent 调用。`api/mcp_routes` 提供 MCP 连接的管理 REST API。

### 关键技术

MCP 协议 (2024-11-05)、JSON-RPC 2.0、stdio 传输（子进程通信）、SSE（Server-Sent Events）传输、MCP <-> OpenAI Function Calling 格式互转、连接池管理。
