"""
Decorator for marking functions as SQS message listeners.

This module provides the @sqs_listener decorator that allows developers
to mark functions as message listeners with minimal boilerplate. The
decorator automatically registers the function with the ListenerRegistry
and extracts type hints for automatic deserialization.
"""

import inspect
from typing import Any, Callable, Dict, Optional, TypeVar, get_type_hints

from awskit.config import (
    AcknowledgementMode,
    FifoGroupStrategy,
    ListenerConfig,
)
from awskit.sqs.registry import ListenerRegistry

F = TypeVar("F", bound=Callable[..., Any])


def sqs_listener(
    queue: str,
    *,
    acknowledgement_mode: AcknowledgementMode = AcknowledgementMode.ON_SUCCESS,
    max_concurrent_messages: int = 10,
    max_messages_per_poll: int = 10,
    poll_timeout_seconds: int = 10,
    batch: bool = False,
    visibility_timeout: Optional[int] = None,
    message_group_strategy: Optional[FifoGroupStrategy] = None,
    error_handler: Optional[Callable[[Exception, Any, Dict[str, Any]], None]] = None,
) -> Callable[[F], F]:
    """
    Decorator to mark a function as an SQS message listener.

    This decorator registers the decorated function with the ListenerRegistry,
    making it available for automatic message processing by the
    MessageListenerContainer. The decorator extracts type hints from the
    function signature to enable automatic message deserialization.

    Args:
        queue: Queue name or URL to listen to
        acknowledgement_mode: When to acknowledge messages (default: ON_SUCCESS)
        max_concurrent_messages: Maximum messages to process concurrently (default: 10)
        max_messages_per_poll: Maximum messages to retrieve per poll (default: 10)
        poll_timeout_seconds: Wait time for long polling (default: 10)
        batch: Whether to receive messages in batches (default: False)
        visibility_timeout: Custom visibility timeout in seconds (default: None)
        message_group_strategy: Strategy for batching FIFO messages (default: None)
        error_handler: Optional custom error handler function (default: None)

    Returns:
        Decorator function that registers the listener

    Example:
        Basic listener:
        >>> @sqs_listener("my-queue")
        ... def process_message(message: dict):
        ...     print(f"Processing: {message}")

        Listener with custom configuration:
        >>> @sqs_listener(
        ...     "orders-queue",
        ...     acknowledgement_mode=AcknowledgementMode.MANUAL,
        ...     max_concurrent_messages=5
        ... )
        ... def process_order(message: Order, ack: Acknowledgement):
        ...     # Process the order
        ...     print(f"Processing order: {message.id}")
        ...     ack.acknowledge()

        Batch listener:
        >>> @sqs_listener("batch-queue", batch=True, max_messages_per_poll=10)
        ... def process_batch(messages: List[dict]):
        ...     print(f"Processing {len(messages)} messages")

        FIFO queue listener:
        >>> @sqs_listener(
        ...     "orders.fifo",
        ...     message_group_strategy=FifoGroupStrategy.PARALLEL_BATCHES_PER_GROUP
        ... )
        ... def process_fifo_message(message: Order):
        ...     print(f"Processing FIFO order: {message.id}")

        Listener with custom error handler:
        >>> def handle_error(exception: Exception, message: Any, context: dict):
        ...     print(f"Error processing message: {exception}")
        ...     # Send to dead letter queue, log to external service, etc.
        ...
        >>> @sqs_listener("my-queue", error_handler=handle_error)
        ... def process_message(message: dict):
        ...     # Process message
        ...     pass
    """

    def decorator(func: F) -> F:
        """
        Inner decorator that performs the actual registration.

        Args:
            func: The listener function to register

        Returns:
            The original function (unmodified)
        """
        # Create listener configuration
        listener_config = ListenerConfig(
            queue=queue,
            acknowledgement_mode=acknowledgement_mode,
            max_concurrent_messages=max_concurrent_messages,
            max_messages_per_poll=max_messages_per_poll,
            poll_timeout_seconds=poll_timeout_seconds,
            batch=batch,
            visibility_timeout=visibility_timeout,
            message_group_strategy=message_group_strategy,
            error_handler=error_handler,
        )

        # Extract type hints from function signature
        # This will be used by the container for automatic deserialization
        try:
            type_hints = get_type_hints(func)
            # Store type hints as metadata on the function for later use
            func.__sqs_type_hints__ = type_hints  # type: ignore[attr-defined]
        except Exception:
            # If type hints can't be extracted, store empty dict
            # The container will handle this gracefully
            func.__sqs_type_hints__ = {}  # type: ignore[attr-defined]

        # Extract function signature for validation
        sig = inspect.signature(func)
        func.__sqs_signature__ = sig  # type: ignore[attr-defined]

        # Register the listener with the registry
        ListenerRegistry.register(func, listener_config)

        # Return the original function unmodified
        return func

    return decorator
