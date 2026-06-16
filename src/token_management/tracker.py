"""Usage aggregation, reporting, and budget alerting.

Tracks per-tenant token consumption, costs, and generates usage reports
with configurable alert thresholds.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """Budget alert severity levels."""

    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class DailyUsage:
    """Token usage and cost for a single day."""

    date: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    total_cost: float = 0.0
    request_count: int = 0


@dataclass
class ModelUsage:
    """Per-model usage breakdown."""

    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    total_cost: float = 0.0
    request_count: int = 0


@dataclass
class UsageReport:
    """Aggregated usage report for a tenant and date range."""

    tenant_id: str
    date_from: str
    date_to: str
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cached_tokens: int = 0
    total_cost: float = 0.0
    total_requests: int = 0
    daily_breakdown: list[DailyUsage] = field(default_factory=list)
    model_breakdown: list[ModelUsage] = field(default_factory=list)
    alert_level: AlertLevel = AlertLevel.NORMAL
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def total_tokens(self) -> int:
        """Sum of all token types."""
        return self.total_input_tokens + self.total_output_tokens + self.total_cached_tokens

    @property
    def cached_hit_rate(self) -> float:
        """Percentage of input tokens served from cache."""
        total_input = self.total_input_tokens + self.total_cached_tokens
        if total_input == 0:
            return 0.0
        return self.total_cached_tokens / total_input


@dataclass
class UsageRecord:
    """Single usage record."""

    tenant_id: str
    model: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    cost_usd: float
    timestamp: datetime = field(default_factory=datetime.utcnow)


class UsageAggregator:
    """Tracks, aggregates, and reports on token usage and costs.

    In-memory storage; for production, replace with database-backed
    persistence (PostgreSQL / TimescaleDB).

    Usage::

        agg = UsageAggregator()
        agg.record("tenant-a", "gpt-4o", 1000, 200, 0, 0.0045)
        report = agg.get_tenant_usage("tenant-a", date_from, date_to)
        alert = agg.check_budget_alert("tenant-a")
    """

    # Default alert thresholds
    DEFAULT_DAILY_BUDGET: float = 50.0   # USD per day
    DEFAULT_MONTHLY_BUDGET: float = 1000.0  # USD per month
    WARNING_RATIO: float = 0.80   # 80% of budget → warning
    CRITICAL_RATIO: float = 0.95  # 95% of budget → critical

    def __init__(
        self,
        daily_budget: float | None = None,
        monthly_budget: float | None = None,
    ) -> None:
        self._records: list[UsageRecord] = []
        self._tenant_budgets: dict[str, dict[str, float]] = {}
        self.daily_budget = daily_budget or self.DEFAULT_DAILY_BUDGET
        self.monthly_budget = monthly_budget or self.DEFAULT_MONTHLY_BUDGET

    def record(
        self,
        tenant_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int,
        cost_usd: float,
        timestamp: datetime | None = None,
    ) -> None:
        """Record a single usage event.

        Args:
            tenant_id: Tenant identifier.
            model: Model used.
            input_tokens: Input tokens consumed.
            output_tokens: Output tokens generated.
            cached_tokens: Cached input tokens.
            cost_usd: Cost in USD.
            timestamp: Event timestamp (default: now).
        """
        record = UsageRecord(
            tenant_id=tenant_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            cost_usd=cost_usd,
            timestamp=timestamp if timestamp is not None else datetime.utcnow(),
        )
        self._records.append(record)

    def set_tenant_budget(
        self,
        tenant_id: str,
        daily: float | None = None,
        monthly: float | None = None,
    ) -> None:
        """Set custom budget thresholds for a tenant.

        Args:
            tenant_id: Tenant identifier.
            daily: Daily budget in USD.
            monthly: Monthly budget in USD.
        """
        if tenant_id not in self._tenant_budgets:
            self._tenant_budgets[tenant_id] = {}
        if daily is not None:
            self._tenant_budgets[tenant_id]["daily"] = daily
        if monthly is not None:
            self._tenant_budgets[tenant_id]["monthly"] = monthly

    def get_tenant_budget(self, tenant_id: str, period: str) -> float:
        """Get budget threshold for a tenant.

        Args:
            tenant_id: Tenant identifier.
            period: 'daily' or 'monthly'.

        Returns:
            Budget in USD.
        """
        return self._tenant_budgets.get(tenant_id, {}).get(
            period, getattr(self, f"{period}_budget")
        )

    def get_tenant_usage(
        self,
        tenant_id: str,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> UsageReport:
        """Generate a usage report for a tenant.

        Args:
            tenant_id: Tenant identifier.
            date_from: Start of period (default: 30 days ago).
            date_to: End of period (default: now).

        Returns:
            UsageReport with full breakdowns.
        """
        if date_to is None:
            date_to = datetime.utcnow()
        if date_from is None:
            date_from = date_to - timedelta(days=30)

        # Filter records
        filtered = [
            r
            for r in self._records
            if r.tenant_id == tenant_id and date_from <= r.timestamp <= date_to
        ]

        # Aggregate totals
        total_input = sum(r.input_tokens for r in filtered)
        total_output = sum(r.output_tokens for r in filtered)
        total_cached = sum(r.cached_tokens for r in filtered)
        total_cost = sum(r.cost_usd for r in filtered)

        # Daily breakdown
        daily_grouped: dict[str, DailyUsage] = defaultdict(DailyUsage)
        for r in filtered:
            day_key = r.timestamp.strftime("%Y-%m-%d")
            daily = daily_grouped[day_key]
            daily.date = day_key
            daily.input_tokens += r.input_tokens
            daily.output_tokens += r.output_tokens
            daily.cached_tokens += r.cached_tokens
            daily.total_cost += r.cost_usd
            daily.request_count += 1

        daily_list = sorted(daily_grouped.values(), key=lambda d: d.date)

        # Model breakdown
        model_grouped: dict[str, ModelUsage] = defaultdict(ModelUsage)
        for r in filtered:
            mu = model_grouped[r.model]
            mu.model_id = r.model
            mu.input_tokens += r.input_tokens
            mu.output_tokens += r.output_tokens
            mu.cached_tokens += r.cached_tokens
            mu.total_cost += r.cost_usd
            mu.request_count += 1

        model_list = sorted(model_grouped.values(), key=lambda m: m.total_cost, reverse=True)

        return UsageReport(
            tenant_id=tenant_id,
            date_from=date_from.strftime("%Y-%m-%d"),
            date_to=date_to.strftime("%Y-%m-%d"),
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_cached_tokens=total_cached,
            total_cost=round(total_cost, 6),
            total_requests=len(filtered),
            daily_breakdown=daily_list,
            model_breakdown=model_list,
            alert_level=self._compute_alert_level(tenant_id, filtered),
        )

    def get_model_breakdown(self, tenant_id: str) -> list[ModelUsage]:
        """Get per-model usage breakdown for a tenant.

        Args:
            tenant_id: Tenant identifier.

        Returns:
            List of ModelUsage sorted by cost descending.
        """
        model_grouped: dict[str, ModelUsage] = defaultdict(ModelUsage)
        for r in self._records:
            if r.tenant_id != tenant_id:
                continue
            mu = model_grouped[r.model]
            mu.model_id = r.model
            mu.input_tokens += r.input_tokens
            mu.output_tokens += r.output_tokens
            mu.cached_tokens += r.cached_tokens
            mu.total_cost += r.cost_usd
            mu.request_count += 1

        return sorted(model_grouped.values(), key=lambda m: m.total_cost, reverse=True)

    def get_daily_trend(self, tenant_id: str, days: int = 30) -> list[DailyUsage]:
        """Get daily usage trend for a tenant.

        Args:
            tenant_id: Tenant identifier.
            days: Number of days to look back.

        Returns:
            List of DailyUsage for each day.
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        daily_grouped: dict[str, DailyUsage] = defaultdict(DailyUsage)
        for r in self._records:
            if r.tenant_id != tenant_id or r.timestamp < cutoff:
                continue
            day_key = r.timestamp.strftime("%Y-%m-%d")
            daily = daily_grouped[day_key]
            daily.date = day_key
            daily.input_tokens += r.input_tokens
            daily.output_tokens += r.output_tokens
            daily.cached_tokens += r.cached_tokens
            daily.total_cost += r.cost_usd
            daily.request_count += 1

        # Fill in missing days with zero entries
        result = []
        for i in range(days):
            day = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
            if day in daily_grouped:
                result.append(daily_grouped[day])
            else:
                result.append(DailyUsage(date=day))

        return sorted(result, key=lambda d: d.date)

    def check_budget_alert(self, tenant_id: str) -> AlertLevel:
        """Check budget alert status for a tenant.

        Compares today's spending against daily budget and this month's
        spending against monthly budget.

        Args:
            tenant_id: Tenant identifier.

        Returns:
            AlertLevel enum (NORMAL, WARNING, or CRITICAL).
        """
        now = datetime.utcnow()

        # Daily
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_records = [
            r
            for r in self._records
            if r.tenant_id == tenant_id and r.timestamp >= today_start
        ]
        today_cost = sum(r.cost_usd for r in today_records)

        daily_budget = self.get_tenant_budget(tenant_id, "daily")
        if daily_budget > 0:
            today_ratio = today_cost / daily_budget
            if today_ratio >= self.CRITICAL_RATIO:
                return AlertLevel.CRITICAL
            if today_ratio >= self.WARNING_RATIO:
                return AlertLevel.WARNING

        # Monthly
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_records = [
            r
            for r in self._records
            if r.tenant_id == tenant_id and r.timestamp >= month_start
        ]
        month_cost = sum(r.cost_usd for r in month_records)

        monthly_budget = self.get_tenant_budget(tenant_id, "monthly")
        if monthly_budget > 0:
            month_ratio = month_cost / monthly_budget
            if month_ratio >= self.CRITICAL_RATIO:
                return AlertLevel.CRITICAL
            if month_ratio >= self.WARNING_RATIO:
                return AlertLevel.WARNING

        return AlertLevel.NORMAL

    def get_total_cost(self, tenant_id: str) -> float:
        """Get total cost for a tenant across all time.

        Args:
            tenant_id: Tenant identifier.

        Returns:
            Total USD cost.
        """
        return round(
            sum(r.cost_usd for r in self._records if r.tenant_id == tenant_id),
            6,
        )

    def get_top_tenants(
        self,
        limit: int = 10,
        date_from: datetime | None = None,
    ) -> list[tuple[str, float]]:
        """Get top tenants by cost.

        Args:
            limit: Number of top tenants to return.
            date_from: Optional start date filter.

        Returns:
            List of (tenant_id, total_cost) tuples.
        """
        tenant_costs: dict[str, float] = defaultdict(float)
        for r in self._records:
            if date_from is not None and r.timestamp < date_from:
                continue
            tenant_costs[r.tenant_id] += r.cost_usd

        sorted_tenants = sorted(tenant_costs.items(), key=lambda x: x[1], reverse=True)
        return [(tid, round(cost, 6)) for tid, cost in sorted_tenants[:limit]]

    def _compute_alert_level(
        self,
        tenant_id: str,
        records: list[UsageRecord],
    ) -> AlertLevel:
        """Internal helper to compute alert level for a set of records."""
        return self.check_budget_alert(tenant_id)

    def clear_tenant(self, tenant_id: str) -> int:
        """Remove all records for a tenant.

        Args:
            tenant_id: Tenant identifier.

        Returns:
            Number of records removed.
        """
        before = len(self._records)
        self._records = [r for r in self._records if r.tenant_id != tenant_id]
        return before - len(self._records)

    def __len__(self) -> int:
        return len(self._records)
