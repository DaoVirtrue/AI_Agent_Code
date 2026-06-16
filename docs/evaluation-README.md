## 评估系统 (Evaluation)

### 模块概述

评估系统为 LLM 应用提供多维度的质量评测和持续优化能力。它包含自研的六维评估体系（准确性、相关性、完整性、一致性、安全性、流畅性）、RAGAS 框架集成评估 RAG 质量、黄金数据集构建（支持人工标注和自动生成）、基于输出分布的漂移检测（及早发现模型/提示词质量退化），以及由评估驱动的迭代优化闭环（评估->分析->优化->再评估），形成正向质量飞轮。

### 关键文件

- `six_dimension.py` - `SixDimensionEvaluator`，LLM-as-Judge 模式的六维质量评估器，支持自定义评判准则和权重
- `ragas_wrapper.py` - `RAGASWrapper`，封装 RAGAS 框架，输出 Faithfulness、Answer Relevancy、Context Precision/Recall 等标准指标
- `golden_dataset.py` - `GoldenDatasetBuilder`，管理标注数据集，支持人工标注、LLM 辅助生成和版本演进
- `drift_detector.py` - `DriftDetector`，对比当前输出与基线分布的差异，检测模型/提示词退化
- `iteration_loop.py` - `IterationClosedLoop`，自动化评估->分析根因->触发优化（提示词/模型选择）->再评估的闭环

### 模块连接

`evaluation` 消费 `rag_system` 的检索和生成结果并产出评估报告，评分配对 `prompt_engineering.drift_detector` 反馈提示词质量变化。`iteration_loop` 可根据评估结果自动调用 `prompt_engineering` 进行提示词调优或建议模型切换。`api/admin_routes` 暴露评估结果数据给前端仪表盘。

### 关键技术

LLM-as-Judge 评分模式、RAGAS 评估框架（Faithfulness/Context Precision/Recall）、黄金数据集版本管理、KL 散度/JS 散度分布漂移检测、自动化评估闭环。
