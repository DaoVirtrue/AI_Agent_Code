"""RAGAS 层 — RAG 质量评估（核心生产级思考体系之一）。

> 核心思想：用标准化指标量化 RAG 质量，而不是拍脑袋说"检索挺好"。

五指标：
- Faithfulness 忠实度 — 答案是否忠于检索到的上下文（防幻觉）
- Answer Relevancy 答案相关性 — 答案是否切题
- Context Precision 上下文精确率 — 检索到的文档是否相关
- Context Recall 上下文召回率 — 相关文档是否都被检索到
- Answer Correctness 答案正确性 — 答案是否事实正确（需 ground truth）

组件：
- ``metrics.py`` — 五指标统一入口（封装 RAGASWrapper）
- ``report.py``  — 评测历史存储 + 趋势
"""

from src.ragas.metrics import RAGASEvaluator, RAGASReport
from src.ragas.report import EvalRun, EvalRunStore

__all__ = [
    "RAGASEvaluator",
    "RAGASReport",
    "EvalRun",
    "EvalRunStore",
]
