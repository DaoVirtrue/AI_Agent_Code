"""
Celery application factory with RabbitMQ broker.

Defines task queues for the major async workloads:
- rag_ingestion    – document parsing, chunking, embedding, indexing
- agent_execution  – autonomous agent runs
- evaluation       – offline eval / benchmarking jobs
- notification     – webhooks, email, push notifications
"""

from __future__ import annotations

from celery import Celery
from kombu import Exchange, Queue

from .config import Settings, get_settings

# ---------------------------------------------------------------------------
# Queue definitions
# ---------------------------------------------------------------------------

# Dead-letter exchange used by all queues for failed messages
DEAD_LETTER_EXCHANGE = Exchange("dlx", type="direct")

RAG_INGESTION_QUEUE = Queue(
    "rag_ingestion",
    Exchange("rag_ingestion", type="direct"),
    routing_key="rag_ingestion",
    queue_arguments={
        "x-dead-letter-exchange": "dlx",
        "x-dead-letter-routing-key": "rag_ingestion.dlq",
    },
)

AGENT_EXECUTION_QUEUE = Queue(
    "agent_execution",
    Exchange("agent_execution", type="direct"),
    routing_key="agent_execution",
    queue_arguments={
        "x-dead-letter-exchange": "dlx",
        "x-dead-letter-routing-key": "agent_execution.dlq",
    },
)

EVALUATION_QUEUE = Queue(
    "evaluation",
    Exchange("evaluation", type="direct"),
    routing_key="evaluation",
    queue_arguments={
        "x-dead-letter-exchange": "dlx",
        "x-dead-letter-routing-key": "evaluation.dlq",
    },
)

NOTIFICATION_QUEUE = Queue(
    "notification",
    Exchange("notification", type="direct"),
    routing_key="notification",
    queue_arguments={
        "x-dead-letter-exchange": "dlx",
        "x-dead-letter-routing-key": "notification.dlq",
    },
)

# Dead-letter queues (for manual inspection / replay)
RAG_INGESTION_DLQ = Queue("rag_ingestion.dlq", DEAD_LETTER_EXCHANGE, routing_key="rag_ingestion.dlq")
AGENT_EXECUTION_DLQ = Queue("agent_execution.dlq", DEAD_LETTER_EXCHANGE, routing_key="agent_execution.dlq")
EVALUATION_DLQ = Queue("evaluation.dlq", DEAD_LETTER_EXCHANGE, routing_key="evaluation.dlq")
NOTIFICATION_DLQ = Queue("notification.dlq", DEAD_LETTER_EXCHANGE, routing_key="notification.dlq")

# ---------------------------------------------------------------------------
# Celery app factory
# ---------------------------------------------------------------------------

_celery_app: Celery | None = None


def create_celery_app(settings: Settings | None = None) -> Celery:
    """Build (or return cached) Celery application instance."""
    global _celery_app

    if _celery_app is not None:
        return _celery_app

    if settings is None:
        settings = get_settings()

    app = Celery(
        "llm_platform",
        broker=settings.rabbitmq.url,
        backend="rpc://",  # RPC result backend – no persistence needed for task results
    )

    # ------------------------------------------------------------------
    # Broker connection settings
    # ------------------------------------------------------------------
    app.conf.broker_heartbeat = settings.rabbitmq.heartbeat
    app.conf.broker_connection_retry_on_startup = True
    app.conf.broker_connection_max_retries = settings.rabbitmq.connection_attempts

    # ------------------------------------------------------------------
    # Task queues
    # ------------------------------------------------------------------
    app.conf.task_queues = (
        RAG_INGESTION_QUEUE,
        AGENT_EXECUTION_QUEUE,
        EVALUATION_QUEUE,
        NOTIFICATION_QUEUE,
        RAG_INGESTION_DLQ,
        AGENT_EXECUTION_DLQ,
        EVALUATION_DLQ,
        NOTIFICATION_DLQ,
    )

    app.conf.task_default_queue = "rag_ingestion"
    app.conf.task_default_exchange = "rag_ingestion"
    app.conf.task_default_routing_key = "rag_ingestion"

    # Route tasks to queues by name prefix
    app.conf.task_routes = {
        "rag.tasks.*": {
            "queue": "rag_ingestion",
            "routing_key": "rag_ingestion",
        },
        "agent.tasks.*": {
            "queue": "agent_execution",
            "routing_key": "agent_execution",
        },
        "evaluation.tasks.*": {
            "queue": "evaluation",
            "routing_key": "evaluation",
        },
        "notification.tasks.*": {
            "queue": "notification",
            "routing_key": "notification",
        },
    }

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    app.conf.task_serializer = "json"
    app.conf.result_serializer = "json"
    app.conf.accept_content = ["json"]

    # ------------------------------------------------------------------
    # Task execution
    # ------------------------------------------------------------------
    app.conf.task_acks_late = True  # Re-deliver if worker crashes mid-task
    app.conf.task_reject_on_worker_lost = True
    app.conf.task_track_started = True
    app.conf.task_soft_time_limit = 600  # SoftLimitExceeded after 10 min
    app.conf.task_time_limit = 900       # SIGKILL after 15 min

    # ------------------------------------------------------------------
    # Retry / error handling
    # ------------------------------------------------------------------
    app.conf.task_default_retry_delay = 5       # seconds
    app.conf.task_max_retries = 3
    app.conf.task_autoretry_for = (Exception,)   # Autoretry on any exception
    app.conf.task_acks_on_failure_or_timeout = True
    app.conf.task_store_errors_even_if_ignored = True

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------
    app.conf.worker_prefetch_multiplier = 1   # Fair dispatch (disable prefetch)
    app.conf.worker_max_tasks_per_child = 1000  # Restart worker after 1k tasks (leak protection)
    app.conf.worker_send_task_events = True

    # ------------------------------------------------------------------
    # Result backend
    # ------------------------------------------------------------------
    app.conf.result_expires = 3600  # 1 hour
    app.conf.result_extended = True
    app.conf.result_backend_transport_options = {
        "master_name": "celery",
        "visibility_timeout": 3600,
    }

    _celery_app = app
    return app


def get_celery_app() -> Celery:
    """Return the cached Celery app. Raises RuntimeError if not created yet."""
    if _celery_app is None:
        raise RuntimeError("Celery app not created. Call create_celery_app() first.")
    return _celery_app


# ── Module-level Celery app for celery -A auto-discovery ──────
# The `celery -A src.infrastructure.broker:celery_app` command needs a module-level instance.
# Prefer the RABBITMQ_URL env var (set by docker-compose) so the worker connects
# to the compose network's RabbitMQ rather than localhost.
import os as _os

_broker_url = _os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost//")

try:
    celery_app = create_celery_app()
except Exception:
    # Fallback: create a minimal app reading RABBITMQ_URL directly.
    celery_app = Celery("llm_platform")
    celery_app.config_from_object({
        "broker_url": _broker_url,
        "task_serializer": "json",
        "result_serializer": "json",
        "accept_content": ["json"],
    })
