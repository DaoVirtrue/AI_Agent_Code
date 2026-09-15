"""Structured logging configuration using structlog."""

import os
import sys
import logging
from typing import Optional

import structlog


def setup_logging(
    level: str = "INFO",
    json_format: bool = True,
    log_file: Optional[str] = None,
) -> None:
    """Configure structured logging for the application.

    Sets up structlog with the following processors:
    - Timestamper: Adds ISO 8601 timestamps
    - JSON renderer: Produces JSON-formatted logs (production)
    - Console renderer: Produces colored console output (development)

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_format: If True, output JSON; if False, output colored console logs.
        log_file: Optional file path for persistent logging.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Shared processors applied to all log events
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if json_format:
        # JSON output for production (machine-parseable)
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(serializer=_json_serializer),
        ]
    else:
        # Colored console output for development (human-readable)
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    # Configure structlog
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging to route through structlog
    _configure_stdlib_logging(log_level, json_format, log_file)

    # Set root log level
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Suppress noisy library loggers
    _suppress_noisy_loggers()


def _json_serializer(data, **kwargs):
    """Custom JSON serializer that handles non-serializable objects."""
    import json

    def default(obj):
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="replace")
        if isinstance(obj, set):
            return list(obj)
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        return str(obj)

    return json.dumps(data, default=default, **kwargs)


def _configure_stdlib_logging(
    level: int,
    json_format: bool,
    log_file: Optional[str],
) -> None:
    """Configure Python standard library logging to use structlog."""

    class StructlogHandler(logging.Handler):
        """Redirects stdlib logging records to structlog."""

        def emit(self, record):
            log_entry = self.format(record)
            logger = structlog.get_logger(record.name)
            if record.levelno >= logging.ERROR:
                logger.error(log_entry)
            elif record.levelno >= logging.WARNING:
                logger.warning(log_entry)
            elif record.levelno >= logging.INFO:
                logger.info(log_entry)
            else:
                logger.debug(log_entry)

    handler = StructlogHandler()
    handler.setLevel(level)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        logging.getLogger().addHandler(file_handler)

    logging.getLogger().handlers = [handler]


def _suppress_noisy_loggers():
    """Suppress verbose loggers from third-party libraries."""
    noisy_loggers = [
        "httpx",
        "httpcore",
        "urllib3",
        "botocore",
        "aiosqlite",
        "asyncio",
        "boto3",
        "s3transfer",
    ]
    for name in noisy_loggers:
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger instance.

    Args:
        name: Logger name, typically __name__ of the calling module.

    Returns:
        A structlog BoundLogger configured with the application settings.

    Usage:
        logger = get_logger(__name__)
        logger.info("Processing request", request_id="abc123", tenant_id="org-1")
        logger.error("Failed to connect", error=str(e), provider="openai")
    """
    return structlog.get_logger(name)


def bind_context(**kwargs) -> None:
    """Bind contextual key-value pairs to all subsequent log calls in this context.

    Useful for adding request-scoped data like request_id and tenant_id.

    Usage:
        bind_context(request_id="abc123", tenant_id="org-1")
        logger.info("Starting operation")  # Automatically includes the bound context
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def unbind_context(*keys: str) -> None:
    """Unbind specific context variables.

    Usage:
        unbind_context("request_id", "tenant_id")
    """
    structlog.contextvars.unbind_contextvars(*keys)


class LogContext:
    """Context manager for temporarily binding log context."""

    def __init__(self, **kwargs):
        self.context = kwargs

    def __enter__(self):
        bind_context(**self.context)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        unbind_context(*self.context.keys())
        return False
