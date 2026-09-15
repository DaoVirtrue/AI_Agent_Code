"""Herms 层 — 评估驱动的自进化闭环（核心生产级思考体系之一）。

> 核心思想：系统上线后如何**越用越好**、安全地迭代，而不是"发布即巅峰"。

**H-E-R-M-S 逐字母拆解**：

- **H** Human 人类监督 — 人工审批、高风险分人工复核、对抗评估兜底
- **E** Evaluation 评估 — 在线评估 + 六维评估 + RAGAS 分数
- **R** Rollout 灰度发布 — 流量染色 + 多版本并行
- **M** Monitoring 漂移监控 — 拒答率/引用率/负反馈率 + 行为基线 + 会话风险分
- **S** Self-improvement 自更新 — 失败轨迹回灌 + 自动调参 + 版本回滚

组件：
- ``traffic_tagger.py`` — 流量染色字段全链路透传
- ``grayscale.py``      — 灰度路由 + 多版本并行
- ``drift_monitor.py``  — 在线漂移监控
- ``risk_scorer.py``    — 会话风险分（防多轮渐进式越狱）
- ``self_improve.py``   — 自更新闭环（评估→诊断→调优→验证）
"""

from src.herms.traffic_tagger import TrafficTags, tag_request
from src.herms.grayscale import GrayscaleRouter, VersionTarget, RouteDecision
from src.herms.drift_monitor import DriftMonitor, DriftConfig, DriftAlert
from src.herms.risk_scorer import SessionRiskScorer, RiskScore
from src.herms.self_improve import SelfImprover, SelfImproveResult

__all__ = [
    "TrafficTags",
    "tag_request",
    "GrayscaleRouter",
    "VersionTarget",
    "RouteDecision",
    "DriftMonitor",
    "DriftConfig",
    "DriftAlert",
    "SessionRiskScorer",
    "RiskScore",
    "SelfImprover",
    "SelfImproveResult",
]
