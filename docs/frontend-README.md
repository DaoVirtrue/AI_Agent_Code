## 前端应用 (Frontend)

### 模块概述

前端是基于 React 18 + TypeScript 构建的单页应用（SPA），为 LLM 平台提供直观的管理界面和交互体验。它使用 Vite 作为构建工具，Ant Design 作为 UI 组件库，Tailwind CSS 实现原子化样式，Zustand 进行轻量级状态管理，React Router 实现路由和权限守卫。前端集成了 Monaco 编辑器用于提示词编写和 JSON 编辑，Recharts 用于数据可视化图表，tsparticles 提供粒子背景动效，React Markdown 渲染 AI 回复的富文本内容。应用支持代码分割和懒加载优化性能。

### 关键目录和文件

- `src/App.tsx` - 应用根组件，React Router 路由定义（含路由守卫 `RouteGuard` 和错误边界 `ErrorBoundary`）
- `src/pages/` - 各功能页面：登录页 `LoginPage`、仪表盘 `DashboardPage`、对话 `chat/ChatPage`、RAG 管理 `RAGPage`、Agent 管理 `AgentPage`、提示词 `PromptsPage`、网关 `GatewayPage`、MCP 管理 `MCPPage`、管理后台 `AdminPage` 及其子页面
- `src/components/` - 可复用组件：布局（`AppLayout`）、通用组件（`ErrorBoundary`、`RouteGuard`）、图表面板
- `src/store/` - Zustand 状态管理：`authStore`、`chatStore`、`ragStore`、`agentStore`、`gatewayStore`、`promptsStore`、`mcpStore`、`adminStore`、`dashboardStore`、`appStore`
- `src/api/` - Axios HTTP 客户端封装 + 各领域的 API 调用函数
- `src/hooks/` - 自定义 Hooks：`useAuth`、`usePagination`、`useSSE`（流式事件订阅）
- `src/types/` - TypeScript 类型定义
- `src/utils/` - 工具函数：格式化、Token 显示、常量配置
- `nginx/` - 生产环境 Nginx 反向代理配置
- `Dockerfile` - Docker 多阶段构建（Nginx 静态文件服务）

### 模块连接

前端通过 `src/api/` 中的 Axios 客户端与后端 `api` 层通信，SSE 流式对话通过 `useSSE` Hook 接收实时 Token 流。Zustand 各 Store 管理前端状态并与后端同步。路由守卫 `RouteGuard` 依赖后端认证接口校验权限。

### 关键技术

React 18、TypeScript 5.6、Vite 6、Ant Design 5.2、Tailwind CSS 3.4、Zustand 5（状态管理）、React Router 7、Axios、Monaco Editor、Recharts 2、React Markdown（remark-gfm + rehype-highlight）、tsparticles、Vitest 测试。
