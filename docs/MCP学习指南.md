# MCP (Model Context Protocol) 学习指南

## 一、什么是 MCP

**MCP (Model Context Protocol)** 是大模型与外部工具/数据源之间的**标准化通信协议**。

简单说：LLM 本身只能"说话"，不能操作文件、查数据库、搜网页。MCP 让 LLM 可以**安全地调用外部工具**。

```
用户 → LLM → MCP协议 → 外部工具(文件/数据库/API/搜索)
              ← 工具返回结果 ←
```

## 二、本项目中的 5 个 MCP 服务器

| 服务器 | 协议 | 工具数 | 用途 |
|--------|------|--------|------|
| **文件系统工具** | stdio | 4 | 读写本地文件、创建目录、搜索文件 |
| **网络搜索** | HTTP | 2 | 通过 API 搜索网页内容 |
| **数据库查询 (PostgreSQL)** | stdio | 3 | 执行 SQL 查询、查看表结构、导出数据 |
| **GitHub 代码仓库** | HTTP | 5 | 读取代码、创建 Issue、提交 PR |
| **REST API 网关** | HTTP | 4 | 调用任意 HTTP API，发送 GET/POST 请求 |

## 三、MCP 的核心概念

### 3.1 三种能力

| 能力 | 说明 | 示例 |
|------|------|------|
| **Tools (工具)** | LLM 可调用的函数 | `read_file`、`search_web`、`query_db` |
| **Resources (资源)** | LLM 可读取的数据 | 文件内容、数据库记录、API 响应 |
| **Prompts (提示词)** | 预定义的提示词模板 | "帮我分析这段代码"的模板 |

### 3.2 传输方式

| 方式 | 适用场景 | 特点 |
|------|----------|------|
| **stdio** | 本地进程通信 | 安全、低延迟，适合本地工具 |
| **HTTP/SSE** | 远程服务通信 | 支持跨机器访问，适合云服务 |

### 3.3 通信格式

MCP 使用 **JSON-RPC 2.0** 协议：

```json
// 请求：列出所有工具
{"jsonrpc": "2.0", "method": "tools/list", "id": 1}

// 请求：调用工具
{"jsonrpc": "2.0", "method": "tools/call", "params": {
  "name": "read_file",
  "arguments": {"path": "/docs/readme.md"}
}, "id": 2}

// 响应
{"jsonrpc": "2.0", "id": 2, "result": {
  "content": [{"type": "text", "text": "文件内容..."}]
}}
```

## 四、如何接入 MCP

### 4.1 在 Claude Desktop 中使用

编辑 `claude_desktop_config.json`：
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/docs"]
    }
  }
}
```

### 4.2 在本平台中添加 MCP 服务器

1. 进入 http://localhost:3000/mcp
2. 点击"添加 MCP 服务器"
3. 填写：
   - **服务器名称**：如 "我的数据库"
   - **传输方式**：stdio 或 HTTP
   - **命令/URL**：根据服务器类型填写
   - **参数**：服务器启动参数
4. 点击"连接"

### 4.3 常用 MCP 服务器推荐

| 服务器 | 安装命令 |
|--------|----------|
| Filesystem | `npx -y @modelcontextprotocol/server-filesystem /path` |
| GitHub | `npx -y @modelcontextprotocol/server-github` |
| PostgreSQL | `npx -y @modelcontextprotocol/server-postgres` |
| Brave Search | `npx -y @modelcontextprotocol/server-brave-search` |
| Puppeteer | `npx -y @modelcontextprotocol/server-puppeteer` |

## 五、MCP vs Function Calling

| 维度 | MCP | Function Calling |
|------|-----|-----------------|
| 标准化 | ✅ 统一协议，跨平台 | ❌ 每个平台自己定义 |
| 工具发现 | ✅ 自动发现服务器提供的所有工具 | ❌ 需手动定义每个工具 |
| 资源管理 | ✅ 支持文件和数据的标准化访问 | ❌ 仅支持函数调用 |
| 安全性 | ✅ 权限控制 + 沙箱 | ⚠️ 需自己实现 |
| 生态 | ✅ 社区活跃，官方提供多种服务器 | ❌ 各自为政 |

## 六、面试要点

如果面试官问 "你会用 MCP 吗"，可以这样回答：

> MCP 是 Anthropic 提出的 Model Context Protocol，用于标准化 LLM 与外部工具的交互。我理解它的三层架构（Tools、Resources、Prompts），两种传输方式（stdio 和 HTTP/SSE），以及基于 JSON-RPC 2.0 的通信格式。
>
> 在本项目中，我展示了5种典型的 MCP 服务器，包括文件系统、网络搜索、数据库查询、GitHub 和 REST API 网关，可以通过界面进行连接管理和工具调用。

## 七、参考资源

- [MCP 官方文档](https://modelcontextprotocol.io)
- [MCP GitHub](https://github.com/modelcontextprotocol)
- [MCP 服务器列表](https://github.com/modelcontextprotocol/servers)
