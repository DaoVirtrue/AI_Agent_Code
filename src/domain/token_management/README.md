## 令牌管理 (Token Management)

### 模块概述

令牌管理模块负责 LLM 交互中的 Token 计量、成本核算、预算管控和用量统计分析。它提供多模型的精确 Token 计数、实时成本追踪、用户/租户级预算分配与超限告警，以及基于性价比的智能模型推荐优化，帮助团队在控制成本的同时最大化模型使用效率。

### 关键文件

- `counter.py` - `TokenCounter`，基于 tiktoken 的多模型精确 Token 计数
- `cost.py` - `CostTracker`，按模型定价实时累加输入/输出成本，`ModelPricing` 维护各模型单价
- `budget.py` - `TokenBudget`，支持日/周/月三级预算分配与超限拒绝
- `tracker.py` - `UsageAggregator`，聚合并导出按租户/应用/时间维度的用量报表
- `optimizer.py` - `CostOptimizer`，基于场景特征智能推荐性价比最优模型
- `encoders/` - 各模型专属的 Token 编码器适配

### 模块连接

`counter` 被 `ai_gateway` 在每次请求前后调用计算实际用量，`cost` 消费计数器结果累加成本。`budget` 通过 Redis 存储配额状态供 `api` 层中间件检查。`optimizer` 为 `prompt_engineering` 提供模型推荐。报表数据通过 `api/admin_routes` 暴露给前端仪表盘。

### 关键技术

tiktoken 精确计数、Lua 脚本原子化预算扣减、Redis 滑动窗口、模型定价表动态维护、Pydantic 配置管理、FastAPI 依赖注入。
