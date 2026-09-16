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
| **🖥️ 前端 UI** | http://localhost:3001 | React 管理后台 + 对话界面 |
| **API 应用** | http://localhost:8000 | FastAPI + Swagger 文档 |
| PostgreSQL | 5432 | 关系型数据库 |
| Redis | 6379 | 缓存 / 限流 |
| RabbitMQ | 5672 / 15672 | 消息队列 / 管理面板 |
| Celery Worker | — | 异步任务（RAG 摄入、评估） |

**国内优化**：Dockerfile 已配置阿里云 apt 源 + pip 源，构建速度极快。

**登录**：任意用户名密码即可登录（demo 模式，后端返回 `llm-demo-key`）。

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
| **登录** | `/login` | 粒子动画登录（真实后端 /v1/auth/login） |
| **Dashboard** | `/dashboard` | 统计卡片 + Token 趋势 + 模型分布（真实 admin 端点） |
| **AI 工作台** | `/chat` | 对话 + 专家/技能/RAG 选择 + 文件/图片上传解析 + 记忆压缩 + 长输出续写 + 复制/导出 |
| **RAG** | `/rag` | 文档上传 + 语义检索 + 知识库管理 |
| **Agent** | `/agent` | Agent 执行日志逐步展开（真实 /v1/agent/run） |
| **智能体专家** | `/experts` | 创建专属智能体（角色+提示词+技能+MCP+知识库）+ 审批 |
| **技能仓库** | `/skills` | 技能上传/列表/搜索/删除 + 权限管理（工具授权规则） |
| **质量评测** | `/eval` | RAGAS 五指标雷达图 + 历史趋势 |
| **Prompts** | `/prompts` | Prompt 模板 + 变量测试 |
| **Gateway** | `/gateway` | Provider 健康 + 熔断状态 |
| **MCP** | `/mcp` | MCP Server 管理 + 工具目录 |
| **Admin** | `/admin` | 租户/审计日志/用量报告/API Key |

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
├── src/                        # 十层架构 + 三大体系（见 docs/面试/架构说明.md）
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
├── tests/                      # 207 个测试（167 单元/集成/e2e + 40 API 冒烟）
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
| `POST /v1/auth/login` | 登录（demo 模式） |
| `POST /v1/gateway/chat/completions` | OpenAI 兼容对话（多模型路由） |
| `GET /v1/gateway/models` | 可用模型列表 |
| `POST /v1/rag/search` | RAG 混合检索 |
| `POST /v1/rag/evaluate` | RAGAS 评测 |
| `POST /v1/agent/run` | Agent 执行 |
| `POST /v1/experts` | 定义业务专家（角色+技能+MCP+知识库） |
| `POST /v1/experts/run` | 运行业务专家 |
| `POST /v1/documents/generate` | 文档生成下载（md/docx/xlsx/pptx） |
| `POST /v1/documents/ocr` | OCR 图片识别 |
| `POST /v1/chat/memory` | 带记忆对话（压缩不丢关键信息） |

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

- [x] `docker compose up -d` 一键部署全部 6 服务，前端 `:3001` + 后端 `:8000` 双端口
- [x] 登录（真实后端 /v1/auth/login）
- [x] Chat 页 SSE 流式逐字显示 + Markdown 渲染 + 记忆压缩可视化
- [x] 长输出续写机制（截断自动续写拼接，代码/文档完整输出）+ 代码复制/导出
- [x] 5+ 厂商模型路由 + 熔断 + 降级 + 限流
- [x] BGE-M3 语义检索（1024d，自动降级 bge-small-zh/hash）
- [x] 4 种 Agent 模式 + PEV + 7 种多 Agent 编排
- [x] 业务专家（角色+提示词+技能+MCP+专属知识库）
- [x] Skill 仓库（技能上传/拉取/安装）
- [x] 权限管理（工具授权规则配置）
- [x] MCP 工具化（CLI/文档/OCR）+ 每次授权机制
- [x] AI 工作台文件/图片上传解析 + RAG/技能选择
- [x] RAGAS 评测（五指标 + 历史趋势）
- [x] 文档生成下载（md/docx/xlsx/pptx）
- [x] 五层记忆 + Ebbinghaus 遗忘曲线 + 上下文压缩不丢关键信息
- [x] 分层超时/重试预算/断点恢复/资源 TTL（韧性专章）
- [x] 207 个测试全绿（167 单元/集成/e2e + 40 API 冒烟）

---

## 相关文档

- 📄 [企业级 LangGraph AI 应用平台 — 深度技术方案（30,000+ 字）](../企业级LangGraph_AI应用平台_深度技术方案.md)
- 📄 [学习提问记录（5 轮提问演进）](../学习提问记录.md)
