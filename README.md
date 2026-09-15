# LLM Platform — 企业级 LangGraph AI 应用平台

> **核心定位**：以 **LangGraph** 为中枢编排引擎，覆盖 Token 计算、上下文管理、AI 网关、高准确率 Prompt/RAG/Agent、MCP、监控告警的企业级大模型应用平台。

---

## 一键部署（Docker）

**面试官只需要装 Docker Desktop**，不需要 Python/Node.js/PostgreSQL/Redis 等任何环境。

```bash
cd llm-platform
cp .env.example .env          # 编辑填入 LLM API Keys
docker compose up -d           # 一键启动全部 6 个服务
```

| 服务 | 端口 | 说明 |
|------|------|------|
| **🖥️ 前端 UI** | http://localhost:3000 | React 管理后台 + 对话界面 |
| **API 应用** | http://localhost:8000 | FastAPI + Swagger 文档 |
| PostgreSQL | 5432 | 关系型数据库 |
| Redis | 6379 | 缓存 / 限流 |
| RabbitMQ | 5672 / 15672 | 消息队列 / 管理面板 |
| Celery Worker | — | 异步任务（RAG 摄入、评估） |

**国内优化**：Dockerfile 已配置阿里云 apt 源 + 清华 pip 源，构建速度极快。

---

## 技术栈

| 层级 | 技术 |
|------|------|
| **前端** | React 18 + Vite + TypeScript + Ant Design 5 + Tailwind CSS |
| **语言** | Python 3.12 (Docker 内) |
| **Web 框架** | FastAPI (async) |
| **编排引擎** | **LangGraph StateGraph**（复杂任务编排） |
| **LLM 框架** | LangChain 0.3+（组件生态） |
| **模型 Provider** | OpenAI / Anthropic / DeepSeek / Qwen / vLLM / llama.cpp |
| **数据库** | PostgreSQL 15 / Redis 7 / RabbitMQ 3.13 |
| **向量库** | ChromaDB / Milvus / FAISS |
| **Embedding** | BGE-M3 (1024d, 稠密+稀疏双向量) |
| **Prompt** | Jinja2 + DSPy (MIPROv2 贝叶斯优化) |
| **监控** | Prometheus + Grafana + OpenTelemetry |
| **部署** | Docker Compose 一键部署 |

---

## 核心架构

```
                    ┌──────────────────────────┐
                    │     LangGraph 编排层       │
                    │  StateGraph / Checkpoint  │
                    │  interrupt / time travel  │
                    └──────────┬───────────────┘
                               │
┌──────┐ ┌──────┐ ┌──────┐ ┌──┴───┐ ┌───────┐ ┌──────┐ ┌──────┐
│ AI   │ │Token │ │上下文│ │Prompt│ │ RAG   │ │Agent │ │ MCP  │
│ 网关 │ │管理  │ │管理  │ │工程  │ │ 系统  │ │系统  │ │集成  │
└──────┘ └──────┘ └──────┘ └──────┘ └───────┘ └──────┘ └──────┘
    │       │       │        │        │         │        │
    └───────┴───────┴────────┴────────┴─────────┴────────┘
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
   ┌──────────┐ ┌──────────┐ ┌──────────┐
   │ 五层记忆  │ │ 流式架构  │ │ 评估体系  │
   │+遗忘曲线 │ │ SSE/背压 │ │ 六维+4框架│
   └──────────┘ └──────────┘ └──────────┘
```

---

## 前端页面

| 页面 | 路由 | 功能 |
|------|------|------|
| **登录** | `/login` | tsparticles 粒子连线动画 + 毛玻璃登录卡片 |
| **Dashboard** | `/dashboard` | 统计卡片 + Token 趋势图 + 模型分布饼图 |
| **Chat** | `/chat` | 三栏可拖拽：对话列表 / SSE 流式对话 / RAG 来源 + Agent 步骤 |
| **RAG** | `/rag` | 文档拖拽上传 + 知识库管理 + 检索测试 |
| **Agent** | `/agent` | Agent 类型选择 + 执行日志逐步展开 (Thought→Action→Observation) |
| **Prompts** | `/prompts` | Monaco 代码编辑器 + 变量测试 + AB 统计结果 |
| **Gateway** | `/gateway` | Provider 健康卡片 + 熔断状态可视化 |
| **MCP** | `/mcp` | MCP Server 管理 + 工具目录 |
| **Admin** | `/admin` | 租户/审计日志/用量报告/API Key 管理 |

## 项目结构

```
llm-platform/
├── Dockerfile                  # Python 3.12 + 清华 pip 源 + 阿里云 apt 源
├── docker-compose.yml          # 6 服务一键编排
├── .env.example                # 环境变量模板
├── README.md
├── frontend/                   # 前端 React 应用
│   ├── Dockerfile              #   node:20 build → nginx:alpine
│   ├── nginx/nginx.conf        #   /api → app:8000 反向代理
│   └── src/                    #   React 页面 + 组件 + Zustand stores
│
├── src/                        # 十层架构 + 三大体系（见 docs/架构说明.md）
│   ├── core/                   # 最底层 — 异常体系 + 工具契约 + 共享类型
│   ├── api/                    # API 层 — FastAPI 路由 + 依赖注入
│   ├── agents/                 # Agent 层 — ReAct/PEV + 7编排 + 工具 + 通信
│   ├── mcp/                    # MCP 层 — Server/Client (stdio+SSE)
│   ├── memory/                 # 记忆层 — STM/LTM/Episodic + 遗忘曲线
│   ├── rag/                    # RAG 层 — chunk/embed/检索/生成 + 4级缓存
│   ├── repositories/           # 持久化层 — ORM + database
│   ├── infrastructure/         # 基础设施 — config/redis/broker/LLM适配器
│   ├── security/               # 安全层 — auth/RBAC/ABAC/PII/注入防御
│   ├── observability/          # 可观测 — metrics/tracing/health/audit
│   ├── resilience/             # 韧性层 — 分层超时/重试预算/断点恢复/资源TTL
│   ├── domain/                 # 领域层 — conversation/context/token/prompt
│   ├── harness/                # ★ Harness 体系 — Agent 安全护栏
│   ├── herms/                  # ★ Herms 体系 — 自进化闭环 H-E-R-M-S
│   ├── ragas/                  # ★ RAGAS 体系 — RAG 质量评估五指标
│   ├── ai_gateway/             # 模型网关层（自洽）— 熔断/限流/降级/负载均衡
│   ├── streaming/              # 流式层（自洽）— SSE/背压/安全扫描
│   └── evaluation/             # 评测层（自洽）— 六维评估/迭代闭环
│
├── tests/                      # 139+ 测试用例
├── config/                     # YAML 配置 + 模型注册表(14模型)
├── deploy/                     # K8s / Helm / Grafana 面板(40面板)
└── alembic/                    # 数据库迁移
```

---

## API 端点

| 端点 | 说明 |
|------|------|
| `GET /health` | 健康检查（DB/Redis/Provider 全量） |
| `GET /docs` | Swagger API 文档 |
| `POST /v1/gateway/chat/completions` | OpenAI 兼容对话（多模型路由） |
| `GET /v1/gateway/models` | 可用模型列表 |
| `POST /v1/rag/search` | RAG 混合检索 |
| `POST /v1/rag/chat` | RAG 对话 |
| `POST /v1/agent/run` | Agent 执行 |
| `POST /v1/prompts/render` | Prompt 渲染 |
| `POST /v1/prompts/experiments` | A/B 测试 |

---

## 5 大 AI 应用开发范式

| 范式 | 本项目的应用 |
|------|------------|
| **Prompt 工程** | Jinja2 模板 + 版本管理 + AB测试 + DSPy MIPROv2 + MMR Few-Shot |
| **RAG** | 全链路 RAG + CRAG/Self-RAG/Adaptive/Graph/Agentic + 4级缓存 |
| **Agent** | ReAct/Plan-Execute/ReWOO/Reflection + 7种多Agent编排 + MCP |
| **Vibe Coding** | Claude Code 辅助开发 |
| **Skills/Plugin** | MCP Server + Tool Registry 动态发现 |

---

## 验收标准

- [x] `docker compose up -d` 一键部署全部 6 服务，前端 `:3000` + 后端 `:8000` 双端口
- [x] 登录页 tsparticles 粒子连线动画 + JWT 认证
- [x] Chat 页 SSE 流式逐字显示 + Markdown 渲染 + RAG 来源标注
- [x] 5+ 厂商模型路由 + 熔断 + 降级 + 限流
- [x] Token 计数偏差 <2%（三编码器：tiktoken/sentencepiece/HF）
- [x] 五区结构上下文窗口 + 三厂商 Prompt Caching（Anthropic/OpenAI/DeepSeek）
- [x] A/B 测试 Welch's t-test + Cohen's d + Bonferroni
- [x] CRAG + Self-RAG + Adaptive RAG + Graph RAG + Agentic RAG
- [x] 4 种 Agent 模式 + 7 种多 Agent 编排
- [x] MCP Server/Client stdio + SSE 双传输
- [x] 五层记忆 + Ebbinghaus 遗忘曲线 + 记忆巩固引擎
- [x] 4 层纵深防御 + 5 层注入防御 + PII 检测

---

## 相关文档

- 📄 [企业级 LangGraph AI 应用平台 — 深度技术方案（30,000+ 字）](../企业级LangGraph_AI应用平台_深度技术方案.md)
- 📄 [学习提问记录（5 轮提问演进）](../学习提问记录.md)
