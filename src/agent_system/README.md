## Agent 系统 (Agent System)

### 模块概述

Agent 系统是生产级的多智能体编排框架。它实现了 ReAct、Plan-Execute、ReWOO、Reflection 等经典 Agent 模式，提供完整的工具体系（注册表、沙箱执行、安全管控）、多层记忆架构（短时/长期/情景记忆 + 遗忘曲线与记忆巩固）、丰富的多 Agent 编排策略（顺序、层级、辩论、升级、黑板、拍卖、群体），以及基于 LangGraph 的 Supervisor、条件路由和人机协作工作流。通信模块支持 Agent 间消息传递、心跳监控和死锁检测，安全保障模块提供内容过滤和护栏。

### 关键文件

- `patterns/` - ReAct、PlanExecute、ReWOO、Reflection 四种 Agent 模式的 LangGraph 实现
- `tools/` - 工具注册表 (`ToolRegistry`)、Docker 沙箱 (`ExecutionSandbox`)、安全校验 (`ToolSecurityManager`)
- `memory/` - 记忆管理器 (`MemoryManager`)、短时/长期/情景记忆、遗忘曲线、记忆巩固引擎、共享黑板 (`SharedBlackboard`)
- `orchestration/` - Sequential、Hierarchical、Debate、Escalation、Blackboard、Auction、Swarm 七种编排器
- `langgraph_workflows/` - Supervisor Agent、条件路由、人机协作 (Human-in-the-Loop)
- `communication/` - Agent 消息协议、通信总线 (`CommunicationBus`)、心跳监控、死锁检测
- `safety.py` - `SafetyGuard`，Agent 执行的护栏和内容过滤

### 模块连接

Agent 系统通过 `api/agent_routes` 接收前端请求，调用 `ai_gateway` 进行 LLM 推理，使用 `prompt_engineering` 构建 Agent 提示词。`tools/` 通过 `mcp_integration` 桥接外部 MCP 工具。`monitoring` 监控 Agent 步数和死循环检测指标。

### 关键技术

LangGraph 状态图、ReAct/Plan-Execute/ReWOO 模式、Docker 沙箱隔离、Ebbinghaus 遗忘曲线、多 Agent 辩论/群体智能、黑板模式共享记忆、心跳+死锁检测、人机协作断点恢复。
