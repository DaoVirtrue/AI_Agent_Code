"""
Shared blackboard for multi-agent collaboration.

Provides a pub/sub namespace where agents can write data, read data,
and subscribe to changes in specific namespaces. Enables opportunistic
collaboration between agents.
"""

import asyncio
import hashlib
import logging
import time
import uuid
from asyncio import Event
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)


class SharedBlackboard:
    """Multi-agent shared namespace with publish/subscribe capabilities.

    Agents can write key-value pairs to namespaced sections, read from
    them, subscribe to change notifications, and list available keys.

    Supports:
    - Namespaced key-value storage
    - Pub/sub change notifications
    - TTL-based expiration
    - Version tracking for optimistic concurrency
    """

    def __init__(self):
        self._data: dict[str, dict[str, Any]] = defaultdict(dict)
        self._metadata: dict[str, dict[str, dict]] = defaultdict(
            lambda: defaultdict(dict)
        )
        self._subscribers: dict[str, dict[str, set[Callable]]] = defaultdict(
            lambda: defaultdict(set)
        )
        self._events: dict[str, dict[str, Event]] = defaultdict(dict)
        self._lock = asyncio.Lock()
        self._write_count = 0
        self._read_count = 0

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def write(
        self,
        namespace: str,
        key: str,
        value: Any,
        ttl: float | None = None,
        version: int | None = None,
    ) -> int:
        """Write a value to the blackboard.

        Args:
            namespace: The namespace to write to.
            key: The key within the namespace.
            value: The value to store.
            ttl: Optional TTL in seconds (None = no expiration).
            version: Expected version for optimistic concurrency (None = no check).

        Returns:
            The new version number.

        Raises:
            ValueError: If the version check fails.
        """
        async with self._lock:
            current_meta = self._metadata[namespace].get(key, {})

            # Version check for optimistic concurrency
            if version is not None:
                current_version = current_meta.get("version", 0)
                if current_version != version:
                    raise ValueError(
                        f"Version mismatch for {namespace}/{key}: "
                        f"expected {version}, got {current_version}"
                    )

            new_version = current_meta.get("version", 0) + 1
            self._metadata[namespace][key] = {
                "version": new_version,
                "created_at": current_meta.get("created_at", time.time()),
                "updated_at": time.time(),
                "ttl": ttl,
            }
            self._data[namespace][key] = value
            self._write_count += 1

        # Notify subscribers
        await self._notify(namespace, key, value)
        return new_version

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def read(self, namespace: str, key: str) -> Any:
        """Read a value from the blackboard.

        Args:
            namespace: The namespace.
            key: The key.

        Returns:
            The stored value, or None if not found or expired.

        Raises:
            KeyError: If the namespace/key doesn't exist.
        """
        async with self._lock:
            if namespace not in self._data or key not in self._data[namespace]:
                raise KeyError(f"Key not found: {namespace}/{key}")

            # Check TTL
            meta = self._metadata[namespace].get(key, {})
            ttl = meta.get("ttl")
            if ttl is not None:
                updated_at = meta.get("updated_at", 0)
                if time.time() - updated_at > ttl:
                    # Expired - clean up
                    del self._data[namespace][key]
                    del self._metadata[namespace][key]
                    raise KeyError(f"Key expired: {namespace}/{key}")

            self._read_count += 1
            return self._data[namespace][key]

    async def read_with_meta(self, namespace: str, key: str) -> tuple[Any, dict]:
        """Read a value with its metadata.

        Args:
            namespace: The namespace.
            key: The key.

        Returns:
            Tuple of (value, metadata_dict).

        Raises:
            KeyError: If not found or expired.
        """
        value = await self.read(namespace, key)
        meta = dict(self._metadata.get(namespace, {}).get(key, {}))
        return value, meta

    # ------------------------------------------------------------------
    # Subscribe
    # ------------------------------------------------------------------

    async def subscribe(
        self, namespace: str, callback: Callable,
        key: str | None = None,
    ) -> str:
        """Subscribe to changes in a namespace.

        The callback receives (namespace, key, value) when a value changes.

        Args:
            namespace: The namespace to watch.
            callback: Async callable taking (namespace, key, value).
            key: Optional specific key to watch (None = all keys in namespace).

        Returns:
            A subscription ID for unsubscribing.
        """
        subscription_id = str(uuid.uuid4())[:8]

        key_filter = key or "*"
        self._subscribers[namespace][key_filter].add((subscription_id, callback))

        logger.debug(
            "Subscription %s: namespace=%s key=%s",
            subscription_id, namespace, key_filter,
        )
        return subscription_id

    async def unsubscribe(self, subscription_id: str) -> bool:
        """Remove a subscription.

        Args:
            subscription_id: The ID returned by subscribe().

        Returns:
            True if the subscription was found and removed.
        """
        for namespace in list(self._subscribers.keys()):
            for key_filter in list(self._subscribers[namespace].keys()):
                subs = self._subscribers[namespace][key_filter]
                to_remove = [
                    (sid, cb) for sid, cb in subs if sid == subscription_id
                ]
                for item in to_remove:
                    subs.discard(item)
                    if not subs:
                        del self._subscribers[namespace][key_filter]
                    if not self._subscribers[namespace]:
                        del self._subscribers[namespace]
                    return True
        return False

    async def wait_for(
        self, namespace: str, key: str, timeout: float = 30.0,
    ) -> Any | None:
        """Block until a key is written or updated, then return its value.

        Args:
            namespace: The namespace to watch.
            key: The key to wait for.
            timeout: Maximum seconds to wait.

        Returns:
            The value when written, or None on timeout.
        """
        event = Event()

        async def callback(ns, k, value):
            if ns == namespace and k == key:
                event.set()

        sub_id = await self.subscribe(namespace, callback, key=key)

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return await self.read(namespace, key)
        except asyncio.TimeoutError:
            return None
        finally:
            await self.unsubscribe(sub_id)

    # ------------------------------------------------------------------
    # Namespace operations
    # ------------------------------------------------------------------

    async def list_namespace(self, namespace: str) -> list[str]:
        """List all keys in a namespace.

        Args:
            namespace: The namespace to list.

        Returns:
            List of key names.
        """
        async with self._lock:
            # Check and remove expired keys
            now = time.time()
            expired = []
            for key, meta in self._metadata.get(namespace, {}).items():
                ttl = meta.get("ttl")
                if ttl is not None:
                    if now - meta.get("updated_at", 0) > ttl:
                        expired.append(key)

            for key in expired:
                self._data[namespace].pop(key, None)
                self._metadata[namespace].pop(key, None)

            return sorted(self._data.get(namespace, {}).keys())

    async def list_all_namespaces(self) -> list[str]:
        """List all namespace names.

        Returns:
            Sorted list of namespace names.
        """
        return sorted(self._data.keys())

    async def delete(self, namespace: str, key: str) -> bool:
        """Delete a key from a namespace.

        Args:
            namespace: The namespace.
            key: The key to delete.

        Returns:
            True if the key was found and deleted.
        """
        async with self._lock:
            if namespace in self._data and key in self._data[namespace]:
                del self._data[namespace][key]
                del self._metadata[namespace][key]
                # Clean up empty namespace
                if not self._data[namespace]:
                    del self._data[namespace]
                    del self._metadata[namespace]
                return True
            return False

    async def clear_namespace(self, namespace: str) -> int:
        """Clear all keys in a namespace.

        Args:
            namespace: The namespace to clear.

        Returns:
            Number of keys removed.
        """
        async with self._lock:
            if namespace not in self._data:
                return 0
            count = len(self._data[namespace])
            del self._data[namespace]
            del self._metadata[namespace]
            return count

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _notify(self, namespace: str, key: str, value: Any) -> None:
        """Notify subscribers of a change."""
        subs = self._subscribers.get(namespace, {})
        callbacks_to_invoke = []

        # Match specific key subscriptions
        if key in subs:
            callbacks_to_invoke.extend(subs[key])

        # Match wildcard subscriptions
        if "*" in subs:
            callbacks_to_invoke.extend(subs["*"])

        # Also check global namespace watch
        global_subs = self._subscribers.get("*", {})
        if key in global_subs:
            callbacks_to_invoke.extend(global_subs[key])
        if "*" in global_subs:
            callbacks_to_invoke.extend(global_subs["*"])

        for sid, callback in callbacks_to_invoke:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(namespace, key, value)
                else:
                    callback(namespace, key, value)
            except Exception as e:
                logger.warning(
                    "Subscriber callback failed (sid=%s): %s", sid, e,
                )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    @property
    def stats(self) -> dict:
        """Return blackboard statistics."""
        total_keys = sum(len(keys) for keys in self._data.values())
        total_subs = sum(
            len(callbacks)
            for ns_subs in self._subscribers.values()
            for callbacks in ns_subs.values()
        )
        return {
            "namespaces": len(self._data),
            "total_keys": total_keys,
            "subscribers": total_subs,
            "writes": self._write_count,
            "reads": self._read_count,
        }

    def __len__(self) -> int:
        return sum(len(keys) for keys in self._data.values())

    def __repr__(self) -> str:
        return (
            f"SharedBlackboard(namespaces={len(self._data)}, "
            f"keys={sum(len(k) for k in self._data.values())})"
        )
