import structlog
import logging


def setup_logging():
    """Configure structured JSON logging via structlog."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )

    # Also configure standard logging to use structlog
    logging.basicConfig(
        format="%(message)s",
        level=logging.INFO,
    )
