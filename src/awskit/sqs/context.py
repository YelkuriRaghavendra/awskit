"""
Application context for automatic container lifecycle management.

This module provides Spring-like automatic container startup and management,
allowing users to simply define listeners and start processing with minimal
boilerplate.
"""

import atexit
from typing import Any, Optional

import structlog

from awskit.config import (
    SqsConfig,
)
from awskit.converter import JsonMessageConverter, MessageConverter
from awskit.metrics import MetricsCollector, NoOpMetricsCollector
from awskit.sqs.acknowledgement import AcknowledgementProcessor
from awskit.sqs.backpressure import BackpressureManager
from awskit.sqs.container import MessageListenerContainer

logger = structlog.get_logger(__name__)


class SqsListenerContext:
    """
    Application context that manages the listener container lifecycle.

    This class provides automatic initialization and startup of the
    MessageListenerContainer, similar to Spring's ApplicationContext.
    Users can define listeners with @sqs_listener and then call
    start_listeners() to begin processing.

    Example:
        >>> import boto3
        >>> from awskit.sqs import sqs_listener, start_listeners
        >>>
        >>> @sqs_listener("my-queue")
        ... def process_message(message: dict):
        ...     print(f"Processing: {message}")
        >>>
        >>> # Automatic container creation and startup
        >>> client = boto3.client('sqs', region_name='us-east-1')
        >>> start_listeners(client)
    """

    _instance: Optional["SqsListenerContext"] = None
    _container: Optional[MessageListenerContainer] = None

    def __init__(
        self,
        client: Any,
        converter: Optional[MessageConverter] = None,
        config: Optional[SqsConfig] = None,
        metrics_collector: Optional[MetricsCollector] = None,
    ):
        """
        Initialize the SQS listener context.

        Args:
            client: boto3 SQS client
            converter: Optional MessageConverter (defaults to JsonMessageConverter)
            config: Optional SqsConfig (uses defaults if not provided)
            metrics_collector: Optional MetricsCollector (uses NoOp if not provided)
        """
        self.client = client
        self.converter = converter or JsonMessageConverter()
        self.config = config or SqsConfig()
        self.metrics_collector = metrics_collector or NoOpMetricsCollector()

        # Create components
        self.acknowledgement_processor = AcknowledgementProcessor(
            client=self.client,
            config=self.config.acknowledgement,
        )

        self.backpressure_manager = BackpressureManager(
            mode=self.config.container.backpressure_mode,
        )

        # Create container
        self._container = MessageListenerContainer(
            client=self.client,
            converter=self.converter,
            acknowledgement_processor=self.acknowledgement_processor,
            backpressure_manager=self.backpressure_manager,
            config=self.config.container,
            metrics_collector=self.metrics_collector,
        )

        # Register shutdown hook
        atexit.register(self.stop)

    def start(self) -> None:
        """
        Start the listener container to begin processing messages.

        This method starts all polling threads and begins processing
        messages from registered queues.
        """
        if self._container:
            self._container.start()
        else:
            logger.warning("No container available to start")

    def stop(self, timeout_seconds: Optional[int] = None) -> None:
        """
        Stop the listener container gracefully.

        This method stops all polling threads, waits for in-flight
        messages to complete, and flushes pending acknowledgements.

        Args:
            timeout_seconds: Maximum time to wait for shutdown
        """
        if self._container:
            self._container.stop(timeout_seconds=timeout_seconds)

    def is_running(self) -> bool:
        """
        Check if the container is currently running.

        Returns:
            True if the container is running, False otherwise
        """
        return self._container is not None and self._container._executor is not None

    @classmethod
    def get_instance(cls) -> Optional["SqsListenerContext"]:
        """
        Get the singleton context instance.

        Returns:
            The singleton SqsListenerContext instance, or None if not initialized
        """
        return cls._instance

    @classmethod
    def set_instance(cls, instance: "SqsListenerContext") -> None:
        """
        Set the singleton context instance.

        Args:
            instance: The SqsListenerContext instance to set as singleton
        """
        cls._instance = instance


# Global convenience functions


def start_listeners(
    client: Any,
    converter: Optional[MessageConverter] = None,
    config: Optional[SqsConfig] = None,
    metrics_collector: Optional[MetricsCollector] = None,
    auto_start: bool = True,
) -> SqsListenerContext:
    """
    Initialize and start the listener container with minimal boilerplate.

    This is the main entry point for automatic container management.
    Call this function after defining your @sqs_listener decorated functions
    to automatically create and start the container.

    Args:
        client: boto3 SQS client
        converter: Optional MessageConverter (defaults to JsonMessageConverter)
        config: Optional SqsConfig (uses defaults if not provided)
        metrics_collector: Optional MetricsCollector (uses NoOp if not provided)
        auto_start: Whether to automatically start the container (default: True)

    Returns:
        SqsListenerContext instance for manual control if needed

    Example:
        Basic usage:
        >>> import boto3
        >>> from awskit.sqs import sqs_listener, start_listeners
        >>>
        >>> @sqs_listener("orders-queue")
        ... def process_order(message: dict):
        ...     print(f"Processing order: {message}")
        >>>
        >>> client = boto3.client('sqs', region_name='us-east-1')
        >>> start_listeners(client)
        >>> # Container is now running and processing messages

        With custom configuration:
        >>> from awskit.sqs import SqsConfig, ContainerConfig, BackpressureMode
        >>>
        >>> config = SqsConfig(
        ...     container=ContainerConfig(
        ...         backpressure_mode=BackpressureMode.ALWAYS_POLL_MAX
        ...     )
        ... )
        >>> start_listeners(client, config=config)

        Manual control:
        >>> context = start_listeners(client, auto_start=False)
        >>> # Do some setup...
        >>> context.start()  # Start when ready
        >>> # Later...
        >>> context.stop()
    """
    # Create context
    context = SqsListenerContext(
        client=client,
        converter=converter,
        config=config,
        metrics_collector=metrics_collector,
    )

    # Set as singleton
    SqsListenerContext.set_instance(context)

    # Auto-start if requested
    if auto_start:
        context.start()

    return context


def stop_listeners(timeout_seconds: Optional[int] = None) -> None:
    """
    Stop the global listener container.

    This is a convenience function to stop the singleton container
    instance created by start_listeners().

    Args:
        timeout_seconds: Maximum time to wait for shutdown

    Example:
        >>> from awskit.sqs import start_listeners, stop_listeners
        >>>
        >>> # Start processing
        >>> start_listeners(client)
        >>>
        >>> # Later, stop gracefully
        >>> stop_listeners(timeout_seconds=30)
    """
    context = SqsListenerContext.get_instance()
    if context:
        context.stop(timeout_seconds=timeout_seconds)


def get_listener_context() -> Optional[SqsListenerContext]:
    """
    Get the global listener context instance.

    Returns:
        The singleton SqsListenerContext instance, or None if not initialized

    Example:
        >>> from awskit.sqs import start_listeners, get_listener_context
        >>>
        >>> start_listeners(client)
        >>> context = get_listener_context()
        >>> if context.is_running():
        ...     print("Container is running")
    """
    return SqsListenerContext.get_instance()
