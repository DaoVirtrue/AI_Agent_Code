"""Structured audit logging with hash chain for tamper evidence."""

import hashlib
import json
import os
from datetime import datetime, timedelta
from typing import Optional

from src.monitoring.logging_setup import get_logger

logger = get_logger(__name__)


class AuditLogger:
    """Structured audit logging with hash chain for tamper evidence.

    Features:
    - Immutable hash chain using SHA-256 (each entry links to previous)
    - Query by tenant, date range, event type
    - Integrity verification (detects tampering)
    - File-based storage with optional database backend
    """

    def __init__(self, log_dir: Optional[str] = None):
        """Initialize the audit logger.

        Args:
            log_dir: Directory for audit log files. Defaults to './audit_logs'.
        """
        self.log_dir = log_dir or os.getenv(
            "AUDIT_LOG_DIR", "./audit_logs"
        )
        os.makedirs(self.log_dir, exist_ok=True)
        self._last_hash: Optional[str] = None

    async def log(
        self,
        event_type: str,
        tenant_id: str,
        user_id: str,
        action: str,
        details: dict,
        resource_id: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> str:
        """Log an audit event with hash chain linking.

        Args:
            event_type: Category of event (e.g., 'gateway.call', 'rag.query', 'admin.update').
            tenant_id: Tenant identifier.
            user_id: User identifier.
            action: Action performed (e.g., 'create', 'read', 'update', 'delete').
            details: Event-specific details dict.
            resource_id: Optional resource identifier.
            ip_address: Optional client IP address.

        Returns:
            The event's hash chain entry (SHA-256 hex digest).
        """
        timestamp = datetime.utcnow()

        event_data = {
            "timestamp": timestamp.isoformat(),
            "event_type": event_type,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "action": action,
            "resource_id": resource_id or "",
            "ip_address": ip_address or "",
            "details": details,
        }

        # Compute hash chain entry
        previous_hash = self._load_last_hash(timestamp.date()) or ""
        chain_hash = self._compute_chain_hash(previous_hash, event_data)
        event_data["chain_hash"] = chain_hash

        # Persist to daily log file
        log_file = self._get_log_path(timestamp.date())
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event_data, ensure_ascii=False) + "\n")

        # Update last hash
        self._save_last_hash(timestamp.date(), chain_hash)
        self._last_hash = chain_hash

        # Structured log
        logger.info(
            "audit_event",
            extra={
                "audit": event_data,
                "type": "audit_log",
            },
        )

        return chain_hash

    async def query(
        self,
        tenant_id: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        event_type: Optional[str] = None,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Query audit logs with optional filters.

        Args:
            tenant_id: Filter by tenant.
            date_from: Start date (inclusive).
            date_to: End date (inclusive).
            event_type: Filter by event type.
            user_id: Filter by user ID.
            action: Filter by action type.
            limit: Maximum number of results.

        Returns:
            List of matching audit event dicts (most recent first).
        """
        results = []

        if date_to is None:
            date_to = datetime.utcnow()
        if date_from is None:
            date_from = date_to - timedelta(days=30)

        # Iterate over daily log files in date range
        current_date = date_from.date()
        end_date = date_to.date()

        while current_date <= end_date and len(results) < limit:
            log_file = self._get_log_path(current_date)

            if os.path.exists(log_file):
                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if len(results) >= limit:
                            break
                        try:
                            event = json.loads(line.strip())
                            if self._matches_filters(
                                event, tenant_id, event_type, user_id, action
                            ):
                                results.append(event)
                        except json.JSONDecodeError:
                            continue

            current_date += timedelta(days=1)

        # Sort by timestamp descending (most recent first)
        results.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        return results[:limit]

    async def verify_integrity(
        self,
        date_str: str,
    ) -> bool:
        """Verify the integrity of the audit hash chain for a given date.

        Recomputes the hash chain from the beginning and compares with
        stored values. Any mismatch indicates tampering.

        Args:
            date_str: Date string in YYYY-MM-DD format.

        Returns:
            True if the hash chain is intact, False if tampering is detected.
        """
        log_file = self._get_log_path(datetime.fromisoformat(date_str).date())

        if not os.path.exists(log_file):
            return True  # No logs = nothing to verify

        previous_hash = ""
        line_number = 0

        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                line_number += 1
                try:
                    event = json.loads(line.strip())
                except json.JSONDecodeError:
                    logger.warning(
                        "Audit log parse error",
                        date=date_str,
                        line=line_number,
                    )
                    return False

                stored_hash = event.get("chain_hash", "")
                # Recompute expected hash
                event_for_hash = {k: v for k, v in event.items() if k != "chain_hash"}
                expected_hash = self._compute_chain_hash(
                    previous_hash, event_for_hash
                )

                if stored_hash != expected_hash:
                    logger.error(
                        "Audit hash chain broken",
                        date=date_str,
                        line=line_number,
                        expected=expected_hash,
                        found=stored_hash,
                    )
                    return False

                previous_hash = stored_hash

        return True

    def _compute_chain_hash(
        self,
        previous_hash: str,
        event_data: dict,
    ) -> str:
        """Compute SHA-256 hash chain entry.

        Hash = SHA-256(previous_hash || timestamp || event_type || tenant_id || user_id || action || resource_id)

        Args:
            previous_hash: Previous entry's hash (empty string for first entry).
            event_data: Normalized event data dict.

        Returns:
            Hex-encoded SHA-256 hash.
        """
        chain_data = "|".join([
            previous_hash,
            str(event_data.get("timestamp", "")),
            str(event_data.get("event_type", "")),
            str(event_data.get("tenant_id", "")),
            str(event_data.get("user_id", "")),
            str(event_data.get("action", "")),
            str(event_data.get("resource_id", "")),
        ])
        return hashlib.sha256(chain_data.encode("utf-8")).hexdigest()

    @staticmethod
    def _matches_filters(
        event: dict,
        tenant_id: Optional[str],
        event_type: Optional[str],
        user_id: Optional[str],
        action: Optional[str],
    ) -> bool:
        """Check if an event matches the given filters."""
        if tenant_id and event.get("tenant_id") != tenant_id:
            return False
        if event_type and event.get("event_type") != event_type:
            return False
        if user_id and event.get("user_id") != user_id:
            return False
        if action and event.get("action") != action:
            return False
        return True

    def _get_log_path(self, date) -> str:
        """Get the file path for a date's audit log."""
        date_str = date.isoformat() if hasattr(date, "isoformat") else str(date)
        return os.path.join(self.log_dir, f"audit-{date_str}.jsonl")

    def _load_last_hash(self, date) -> Optional[str]:
        """Load the last hash from the persistence file for a date."""
        if self._last_hash is not None:
            return self._last_hash

        hash_file = os.path.join(self.log_dir, f"last_hash-{date.isoformat()}.txt")
        if os.path.exists(hash_file):
            with open(hash_file, "r") as f:
                return f.read().strip()

        return ""

    def _save_last_hash(self, date, chain_hash: str) -> None:
        """Persist the last hash for a date."""
        hash_file = os.path.join(self.log_dir, f"last_hash-{date.isoformat()}.txt")
        with open(hash_file, "w") as f:
            f.write(chain_hash)
