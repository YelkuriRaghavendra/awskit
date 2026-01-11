"""
Structured logging configuration using structlog.

This module provides centralized configuration for structlog, including
processor setup, output formatting, and pytest compatibility.
"""

import logging
import structlog


def configure_structlog() -> None:
    """
    Configure structlog with default settings for the SQS integration library.

    This function sets up the processor pipeline, logger factory, and output
    formatting. It should be called once at module import time.

    The processor pipeline includes:
    - Context variables merging
    - Log level addition
    - Logger name addition
    - ISO 8601 timestamp
    - Stack info rendering
    - Exception formatting
    - ProcessorFormatter for pytest compatibility (adds context as log record attributes)
    - JSON rendering

    The configuration uses structlog.stdlib.BoundLogger as the wrapper class
    for compatibility with pytest's caplog fixture.
    """
    # Configure structlog
    structlog.configure(
        processors=[
            # Merge context variables
            structlog.contextvars.merge_contextvars,
            # Add log level to the event dict
            structlog.stdlib.add_log_level,
            # Add logger name to the event dict
            structlog.stdlib.add_logger_name,
            # Add ISO 8601 timestamp
            structlog.processors.TimeStamper(fmt="iso"),
            # Render stack info if present
            structlog.processors.StackInfoRenderer(),
            # Format exception information
            structlog.processors.format_exc_info,
            # ProcessorFormatter for pytest compatibility - adds context as log record attributes
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        # Use BoundLogger for pytest compatibility
        wrapper_class=structlog.stdlib.BoundLogger,
        # Use dict for context storage
        context_class=dict,
        # Use standard library logger factory
        logger_factory=structlog.stdlib.LoggerFactory(),
        # Cache logger instances for performance
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging to use structlog's ProcessorFormatter
    # This ensures context fields are added as log record attributes for pytest
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
