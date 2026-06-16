## 提示词工程 (Prompt Engineering)

### 模块概述

提示词工程模块提供生产级 LLM 提示词的全生命周期管理工具链。它包含基于 Jinja2 + Pydantic 的模板渲染引擎、Git 风格的提示词版本管理、多层注入防御、提示词级别成本优化、基于分布漂移的性能监控、A/B 测试实验框架、少样本（Few-Shot）示例选择管理，以及 DSPy 框架集成实现自动提示词优化。

### 关键文件

- `engine.py` - `PromptEngine`，Jinja2 + Pydantic 的提示词渲染引擎，支持模板继承、宏和变量校验
- `version_manager.py` - `PromptVersionManager`，Git-like 版本控制，支持 diff、rollback、发布审批
- `security.py` - `InjectionDefense`，多层级提示词注入防御（分隔符、正则、角色边界、LLM 检测）
- `cost_optimizer.py` - `PromptCostOptimizer`，分析提示词结构并优化以降低 Token 消耗
- `drift_detector.py` - `PromptDriftDetector`，监控提示词输出分布漂移
- `ab_testing/` - A/B 测试框架：流量拆分、实验分析、统计显著性检验
- `fewshot/` - 少样本选择器：MMR 选择、例句库管理
- `dspy_integration/` - DSPy 集成：自动编译和优化提示词
- `templates/` - 预置提示词模板库

### 模块连接

`engine` 被 `agent_system`（生成 agent 提示词）和 `rag_system`（RAG 问答提示词）使用。`version_manager` 通过 `api/prompt_routes` 暴露管理接口。`security` 在 `ai_gateway` 请求前进行注入检测。`drift_detector` 对接 `evaluation` 模块持续监测质量变化。

### 关键技术

Jinja2 模板引擎、Pydantic 变量校验、Git 版本控制模型、正则 + LLM 双层注入防御、DSPy 自动优化、统计显著性 A/B 测试、MMR 选择算法。
