"""Structured logging setup with bounded, privacy-safe fields."""

import logging

import structlog


def configure_logging(level: str) -> None:
    """Configure JSON logs; request middleware is responsible for safe correlation fields."""
    logging.basicConfig(format="%(message)s", stream=None, level=level, force=True)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level)),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
