"""Alerting module - Alert rules, notification channels, and alert manager integration."""

import os
import json
from typing import Optional

import yaml


class AlertConfig:
    """Loads and manages alert rule configurations."""

    def __init__(self, rules_path: Optional[str] = None):
        self.rules_path = rules_path or os.path.join(
            os.path.dirname(__file__), "rules.yaml"
        )
        self._rules: Optional[dict] = None

    @property
    def rules(self) -> dict:
        """Get the alert rules configuration."""
        if self._rules is None:
            self._rules = self._load_rules()
        return self._rules

    def _load_rules(self) -> dict:
        """Load alert rules from the YAML configuration file."""
        with open(self.rules_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def get_rule_by_name(self, name: str) -> Optional[dict]:
        """Get a specific alert rule by name."""
        for group in self.rules.get("groups", []):
            for rule in group.get("rules", []):
                if rule.get("alert") == name:
                    return rule
        return None

    def list_alerts(self) -> list[str]:
        """List all alert names."""
        alerts = []
        for group in self.rules.get("groups", []):
            for rule in group.get("rules", []):
                alerts.append(rule.get("alert", ""))
        return [a for a in alerts if a]


class AlertNotifier:
    """Sends alerts to notification channels (Slack, PagerDuty, email, webhook)."""

    SLACK_WEBHOOK_URL = os.getenv("SLACK_ALERT_WEBHOOK_URL", "")
    PAGERDUTY_ROUTING_KEY = os.getenv("PAGERDUTY_ROUTING_KEY", "")
    ALERT_EMAIL = os.getenv("ALERT_EMAIL", "")

    @classmethod
    async def send_slack_alert(
        cls,
        title: str,
        description: str,
        severity: str,
        details: Optional[dict] = None,
    ) -> bool:
        """Send an alert to Slack via webhook."""
        if not cls.SLACK_WEBHOOK_URL:
            return False

        color_map = {
            "P1": "#FF0000",  # Red - Critical
            "P2": "#FFA500",  # Orange - Warning
            "P3": "#FFFF00",  # Yellow - Info
        }

        payload = {
            "attachments": [
                {
                    "color": color_map.get(severity, "#FF0000"),
                    "title": title,
                    "text": description,
                    "fields": [
                        {"title": "Severity", "value": severity, "short": True},
                    ],
                    "footer": "LLM Platform Monitoring",
                    "ts": int(__import__("time").time()),
                }
            ]
        }

        if details:
            payload["attachments"][0]["fields"].append({
                "title": "Details",
                "value": f"```{json.dumps(details, indent=2)}```",
                "short": False,
            })

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    cls.SLACK_WEBHOOK_URL,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    return resp.status == 200
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("Failed to send Slack alert: %s", e)
            return False

    @classmethod
    async def send_pagerduty_alert(
        cls,
        title: str,
        description: str,
        severity: str,
        dedup_key: Optional[str] = None,
    ) -> bool:
        """Send an alert to PagerDuty via Events API v2."""
        if not cls.PAGERDUTY_ROUTING_KEY:
            return False

        payload = {
            "routing_key": cls.PAGERDUTY_ROUTING_KEY,
            "event_action": "trigger",
            "payload": {
                "summary": title,
                "source": "llm-platform",
                "severity": severity,
                "custom_details": {"description": description},
            },
        }

        if dedup_key:
            payload["dedup_key"] = dedup_key

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://events.pagerduty.com/v2/enqueue",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    return resp.status in (200, 202)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("Failed to send PagerDuty alert: %s", e)
            return False


__all__ = ["AlertConfig", "AlertNotifier"]
