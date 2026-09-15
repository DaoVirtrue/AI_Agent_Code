"""RAGAS 层 — RAG 质量评估（核心生产级思考体系之一）。

> 核心思想：用标准化指标量化 RAG 质量，而不是拍脑袋说"检索挺好"。

五指标：

- Faithfulness 忠实度 — 答案是否忠于检索到的上下文（防幻觉）
- Answer Relevancy 答案相关性 — 答案是否切题
- Context Precision 上下文精确率 — 检索到的文档是否相关
- Context Recall 上下文召回率 — 相关文档是否都被检索到
- Answer Correctness 答案正确性 — 答案是否事实正确（需 ground truth）

计划实现（M5 落地）：

- ``metrics.py``         — 五指标计算（包现有 ``src/evaluation/ragas_wrapper.py``）
- ``golden_dataset.py``  — 黄金数据集管理（≥100 例、污染检查、分层抽样）
- ``drift.py``           — RAG 漂移监控
- ``report.py``          — 评测报告生成（雷达图 + 逐题明细 + 趋势）

配套：与 ``src/herms`` 的 Monitoring（漂移监控）协同，构成完整质量闭环。
"""

__all__: list[str] = []
