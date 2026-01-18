"""
Message listener container for polling and processing SQS messages.

This module provides the MessageListenerContainer class that manages polling
queues, invoking listeners, and coordinating message processing with
acknowledgement and backpressure management.
"""

import inspect
import structlog
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, get_type_hints

from awskit.sqs.acknowledgement import AcknowledgementProcessor
from awskit.sqs.backpressure import BackpressureManager
from awskit.config import AcknowledgementMode, ContainerConfig, ListenerConfig
from awskit.converter import MessageConverter
from awskit.exceptions import DeserializationError, ListenerError
from awskit.metrics import MetricsCollector, NoOpMetricsCollector
from awskit.sqs.models import Acknowledgement, Message
from awskit.sqs.registry import ListenerRegistry

logger = structlog.get_logger(__name__)


class MessageListenerContainer:
    """
    Container that polls queues and invokes registered listeners.

    The MessageListenerContainer is responsible for:
    - Loading registered listeners from the ListenerRegistry
    - Resolving queue URLs for all listeners
    - Polling queues for messages
    - Deserializing message payloads
    - Invoking listener functions
    - Managing acknowledgements based on configured strategies
    - Coordinating with BackpressureManager for throughput control

    Attributes:
        client: boto3 SQS client
        converter: MessageConverter for deserialization
        acknowledgement_processor: AcknowledgementProcessor for message deletion
        backpressure_manager: BackpressureManager for throughput control
        config: ContainerConfig with behavior settings
    """

    def __init__(
        self,
        client: Any,
        converter: MessageConverter,
        acknowledgement_processor: AcknowledgementProcessor,
        backpressure_manager: BackpressureManager,
        config: Optional[ContainerConfig] = None,
        metrics_collector: Optional[MetricsCollector] = None,
    ):
        """
        Initialize the MessageListenerContainer.

        Args:
            client: boto3 SQS client
            converter: MessageConverter for deserialization
            acknowledgement_processor: AcknowledgementProcessor for message deletion
            backpressure_manager: BackpressureManager for throughput control
            config: Optional ContainerConfig (uses defaults if not provided)
            metrics_collector: Optional MetricsCollector for tracking metrics (uses NoOp if not provided)
        """
        self.client = client
        self.converter = converter
        self.acknowledgement_processor = acknowledgement_processor
        self.backpressure_manager = backpressure_manager
        self.config = config or ContainerConfig()
        self.metrics_collector = metrics_collector or NoOpMetricsCollector()

        # Queue URL cache
        self._queue_url_cache: Dict[str, str] = {}

        # Listener storage: queue_url -> (listener_func, config)
        self._listeners: Dict[str, List[Tuple[Callable[..., Any], ListenerConfig]]] = {}

        # Thread pools for concurrent processing
        self._executor: Optional[ThreadPoolExecutor] = None

        # Polling threads
        self._polling_threads: List[threading.Thread] = []
        self._shutdown_event = threading.Event()

        # FIFO message group tracking
        # Maps queue_url -> set of message_group_ids currently being processed
        self._active_message_groups: Dict[str, set[str]] = {}
        self._message_group_locks: Dict[str, threading.Lock] = {}

        # Error tracking for backoff
        # Maps queue_url -> consecutive error count
        self._error_counts: Dict[str, int] = {}
        self._error_locks: Dict[str, threading.Lock] = {}

        # Load registered listeners
        self._load_listeners()

    def _load_listeners(self) -> None:
        """
        Load registered listeners from ListenerRegistry and resolve queue URLs.

        This method retrieves all registered listeners, resolves their queue
        names/URLs to actual queue URLs, and stores them for polling.
        """
        registered_listeners = ListenerRegistry.get_listeners()

        for listener_func, listener_config in registered_listeners:
            # Resolve queue URL
            queue_url = self._resolve_queue_url(listener_config.queue)

            # Store listener by queue URL
            if queue_url not in self._listeners:
                self._listeners[queue_url] = []

            self._listeners[queue_url].append((listener_func, listener_config))

            # Initialize backpressure manager for this queue
            self.backpressure_manager.initialize_queue(
                queue_url, listener_config.max_concurrent_messages
            )

            # Initialize FIFO tracking if this is a FIFO queue
            if self._is_fifo_queue(queue_url):
                if queue_url not in self._active_message_groups:
                    self._active_message_groups[queue_url] = set()
                    self._message_group_locks[queue_url] = threading.Lock()

            # Initialize error tracking for this queue
            if queue_url not in self._error_counts:
                self._error_counts[queue_url] = 0
                self._error_locks[queue_url] = threading.Lock()

    def _resolve_queue_url(self, queue: str) -> str:
        """
        Resolve queue name or URL to a queue URL.

        Args:
            queue: Queue name or URL

        Returns:
            Queue URL

        Raises:
            Exception: If queue doesn't exist
        """
        # If it looks like a URL, return it directly
        if queue.startswith("https://") or queue.startswith("http://"):
            return queue

        # Check cache
        if queue in self._queue_url_cache:
            return self._queue_url_cache[queue]

        # Get queue URL from SQS
        try:
            response = self.client.get_queue_url(QueueName=queue)
            queue_url: str = response["QueueUrl"]
            self._queue_url_cache[queue] = queue_url
            return queue_url
        except Exception as e:
            logger.error("Failed to resolve queue URL", queue_name=queue, error=str(e))
            raise

    def _is_fifo_queue(self, queue_url: str) -> bool:
        """
        Detect if a queue is a FIFO queue based on its URL.

        FIFO queues have URLs ending with .fifo

        Args:
            queue_url: The queue URL

        Returns:
            True if the queue is a FIFO queue, False otherwise
        """
        # Extract queue name from URL
        queue_name = queue_url.split("/")[-1]
        return queue_name.endswith(".fifo")

    def _get_message_group_id(self, raw_message: Dict[str, Any]) -> Optional[str]:
        """
        Extract message group ID from a message.

        Args:
            raw_message: The raw message dict from SQS

        Returns:
            Message group ID if present, None otherwise
        """
        attributes = raw_message.get("Attributes", {})
        group_id = attributes.get("MessageGroupId")
        return str(group_id) if group_id is not None else None

    def _extend_visibility_for_message_group(
        self,
        queue_url: str,
        message_group_id: str,
        messages: List[Dict[str, Any]],
        visibility_timeout: int,
    ) -> None:
        """
        Extend visibility timeout for all messages in a message group.

        This is required for FIFO queues to ensure that all messages in a group
        remain invisible while processing, preventing other consumers from
        receiving them out of order.

        Args:
            queue_url: The queue URL
            message_group_id: The message group ID
            messages: List of raw messages from the current poll
            visibility_timeout: The visibility timeout in seconds
        """
        # Find all messages in this message group from the current batch
        group_messages = [
            msg for msg in messages if self._get_message_group_id(msg) == message_group_id
        ]

        if not group_messages:
            return

        # Extend visibility for each message in the group
        for msg in group_messages:
            try:
                self.client.change_message_visibility(
                    QueueUrl=queue_url,
                    ReceiptHandle=msg["ReceiptHandle"],
                    VisibilityTimeout=visibility_timeout,
                )
            except Exception as e:
                logger.error(
                    "Failed to extend visibility for message in group",
                    message_id=msg.get("MessageId", "unknown"),
                    message_group_id=message_group_id,
                    error=str(e),
                )

    def start(self) -> None:
        """
        Start polling all registered queues.

        This method creates a thread pool for concurrent message processing
        and starts polling threads for each registered queue.
        """
        if self._executor is not None:
            logger.warning("Container is already started")
            return

        # Use a reasonable default pool size
        max_workers = sum(
            config.max_concurrent_messages
            for listeners in self._listeners.values()
            for _, config in listeners
        )

        # Ensure at least 1 worker (even if no listeners registered yet)
        max_workers = max(1, max_workers)

        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="SQS-Processor"
        )

        # Start polling thread for each queue
        for queue_url, listeners in self._listeners.items():
            # Use the first listener's config for polling parameters
            # (all listeners on the same queue should have compatible configs)
            _, listener_config = listeners[0]

            polling_thread = threading.Thread(
                target=self._poll_queue_loop,
                args=(queue_url, listener_config),
                daemon=True,
                name=f"SQS-Poller-{queue_url.split('/')[-1]}",
            )
            polling_thread.start()
            self._polling_threads.append(polling_thread)

    def stop(self, timeout_seconds: Optional[int] = None) -> None:
        """
        Stop polling and wait for in-flight messages to complete.

        This method performs a graceful shutdown:
        1. Signals all polling threads to stop
        2. Waits for in-flight messages to complete processing
        3. Flushes pending acknowledgements
        4. Shuts down the thread pool

        Args:
            timeout_seconds: Maximum time to wait for shutdown (uses config default if None)
        """
        if self._executor is None:
            logger.warning("Container is not started")
            return

        timeout = timeout_seconds or self.config.listener_shutdown_timeout_seconds

        self._shutdown_event.set()

        # Wait for polling threads to finish
        for thread in self._polling_threads:
            thread.join(timeout=timeout)
            if thread.is_alive():
                logger.warning(
                    "Polling thread did not stop within timeout", thread_name=thread.name
                )

        # Shutdown thread pool and wait for in-flight messages
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None

        # Flush pending acknowledgements
        self.acknowledgement_processor.flush()

    def _calculate_backoff_delay(self, queue_url: str) -> float:
        """
        Calculate backoff delay based on consecutive error count.

        Uses exponential backoff with the configured policy.

        Args:
            queue_url: The queue URL

        Returns:
            Backoff delay in seconds
        """
        with self._error_locks[queue_url]:
            error_count = self._error_counts[queue_url]

        policy = self.config.backoff_policy

        # Calculate exponential backoff
        delay = policy.initial_interval_seconds * (policy.multiplier**error_count)

        # Cap at max interval
        delay = min(delay, policy.max_interval_seconds)

        return delay

    def _reset_error_count(self, queue_url: str) -> None:
        """
        Reset error count for a queue after successful poll.

        Args:
            queue_url: The queue URL
        """
        with self._error_locks[queue_url]:
            if self._error_counts[queue_url] > 0:
                self._error_counts[queue_url] = 0

    def _increment_error_count(self, queue_url: str) -> int:
        """
        Increment error count for a queue after polling error.

        Args:
            queue_url: The queue URL

        Returns:
            New error count
        """
        with self._error_locks[queue_url]:
            self._error_counts[queue_url] += 1
            return self._error_counts[queue_url]

    def _poll_queue_loop(self, queue_url: str, config: ListenerConfig) -> None:
        """
        Continuous polling loop for a single queue.

        This method runs in a separate thread and continuously polls the queue
        for messages until shutdown is signaled. It implements error handling
        with exponential backoff for polling errors.

        Args:
            queue_url: The URL of the queue to poll
            config: The listener configuration for this queue
        """

        while not self._shutdown_event.is_set():
            try:
                # Check if we should poll based on backpressure
                if not self.backpressure_manager.should_poll(queue_url, config):
                    # No capacity available, wait a bit
                    self._shutdown_event.wait(0.1)
                    continue

                # Poll the queue
                self._poll_queue(queue_url, config)

                # Reset error count on successful poll
                self._reset_error_count(queue_url)

            except Exception as e:
                # Increment error count
                error_count = self._increment_error_count(queue_url)

                # Log error with full context
                logger.exception(
                    "Error polling queue",
                    queue_url=queue_url,
                    error_count=error_count,
                    error_type=type(e).__name__,
                )

                # Check if we've exceeded max retries
                max_retries = self.config.backoff_policy.max_retries
                if max_retries is not None and error_count >= max_retries:
                    logger.critical(
                        "Max retries exceeded for queue - stopping poll loop",
                        queue_url=queue_url,
                        max_retries=max_retries,
                        error_count=error_count,
                    )
                    break

                # Calculate and apply backoff delay
                backoff_delay = self._calculate_backoff_delay(queue_url)
                self._shutdown_event.wait(backoff_delay)

    def _poll_queue(self, queue_url: str, config: ListenerConfig) -> None:
        """
        Poll a single queue and process messages.

        This method performs a single poll operation on the queue, retrieves
        messages, and submits them for processing.

        Args:
            queue_url: The URL of the queue to poll
            config: The listener configuration for this queue
        """
        # Build receive parameters
        receive_params: Dict[str, Any] = {
            "QueueUrl": queue_url,
            "MaxNumberOfMessages": config.max_messages_per_poll,
            "WaitTimeSeconds": config.poll_timeout_seconds,
            "MessageAttributeNames": ["All"],
            "AttributeNames": ["All"],
        }

        if config.visibility_timeout is not None:
            receive_params["VisibilityTimeout"] = config.visibility_timeout

        # Receive messages
        response = self.client.receive_message(**receive_params)
        messages = response.get("Messages", [])

        if not messages:
            # Empty poll - update backpressure state
            self.backpressure_manager.on_empty_poll(queue_url)
            return

        # Messages received - update backpressure state
        message_count = len(messages)
        self.backpressure_manager.on_messages_received(queue_url, message_count)

        # Track received messages metric
        self.metrics_collector.increment_received(queue_url, message_count)

        # Try to acquire permits for processing these messages
        if not self.backpressure_manager.acquire_permit(queue_url, message_count):
            # Couldn't acquire permits - this shouldn't happen if should_poll worked correctly
            # But we'll handle it gracefully by not processing these messages
            # They'll become visible again after visibility timeout
            logger.warning(
                "Could not acquire permits for messages",
                message_count=message_count,
                queue_url=queue_url,
            )
            return

        # For FIFO queues, extend visibility timeout for message groups before processing
        if self._is_fifo_queue(queue_url):
            # Get visibility timeout (use config or default to 30 seconds)
            visibility_timeout = config.visibility_timeout or 30

            # Group messages by message group ID
            message_groups: Dict[str, List[Dict[str, Any]]] = {}
            for msg in messages:
                group_id = self._get_message_group_id(msg)
                if group_id:
                    if group_id not in message_groups:
                        message_groups[group_id] = []
                    message_groups[group_id].append(msg)

            # Extend visibility for each message group
            for group_id, group_messages in message_groups.items():
                self._extend_visibility_for_message_group(
                    queue_url, group_id, group_messages, visibility_timeout
                )

        # Process each message
        for msg in messages:
            # Submit message processing to thread pool
            if self._executor:
                self._executor.submit(self._process_message, queue_url, msg, config)

    def _process_message(
        self, queue_url: str, raw_message: Dict[str, Any], config: ListenerConfig
    ) -> None:
        """
        Process a single message by deserializing and invoking listeners.

        This method is called in a worker thread from the thread pool.
        For FIFO queues, it ensures messages within the same message group
        are processed serially while allowing parallel processing across groups.

        Args:
            queue_url: The URL of the queue the message came from
            raw_message: The raw message dict from SQS
            config: The listener configuration
        """
        message_group_id: Optional[str] = None
        is_fifo = self._is_fifo_queue(queue_url)

        # Bind context for this message
        log = logger.bind(
            message_id=raw_message.get("MessageId", "unknown"),
            queue_url=queue_url,
            receipt_handle=raw_message.get("ReceiptHandle", "unknown"),
        )

        try:
            # For FIFO queues, handle message group serialization
            if is_fifo:
                message_group_id = self._get_message_group_id(raw_message)
                if message_group_id:
                    # Wait until this message group is available for processing
                    self._acquire_message_group(queue_url, message_group_id)

            # Get listeners for this queue
            listeners = self._listeners.get(queue_url, [])
            if not listeners:
                log.error("No listeners found for queue")
                return

            # Process with each listener
            for listener_func, listener_config in listeners:
                try:
                    # Deserialize message
                    message = self._deserialize_message(raw_message, queue_url, listener_func)

                    # Invoke listener
                    self._invoke_listener(listener_func, message, listener_config)

                except Exception as e:
                    log.exception(
                        "Error processing message",
                        listener_name=listener_func.__name__,
                        error=str(e),
                    )

        finally:
            # Release message group lock for FIFO queues
            if is_fifo and message_group_id:
                self._release_message_group(queue_url, message_group_id)

            # Always release the permit
            self.backpressure_manager.release_permit(queue_url, 1)

    def _acquire_message_group(self, queue_url: str, message_group_id: str) -> None:
        """
        Acquire exclusive access to a message group for processing.

        This ensures that messages within the same message group are processed
        serially, while allowing parallel processing of different message groups.

        Args:
            queue_url: The queue URL
            message_group_id: The message group ID
        """
        lock = self._message_group_locks.get(queue_url)
        if not lock:
            return

        # Wait until this message group is not being processed
        while True:
            with lock:
                active_groups = self._active_message_groups.get(queue_url, set())
                if message_group_id not in active_groups:
                    # Mark this group as active
                    active_groups.add(message_group_id)
                    self._active_message_groups[queue_url] = active_groups
                    return

            # Group is busy, wait a bit before checking again
            self._shutdown_event.wait(0.01)

            # Check if we're shutting down
            if self._shutdown_event.is_set():
                return

    def _release_message_group(self, queue_url: str, message_group_id: str) -> None:
        """
        Release exclusive access to a message group after processing.

        Args:
            queue_url: The queue URL
            message_group_id: The message group ID
        """
        lock = self._message_group_locks.get(queue_url)
        if not lock:
            return

        with lock:
            active_groups = self._active_message_groups.get(queue_url, set())
            if message_group_id in active_groups:
                active_groups.discard(message_group_id)

    def _deserialize_message(
        self, raw_message: Dict[str, Any], queue_url: str, listener_func: Callable[..., Any]
    ) -> Message:
        """
        Deserialize a raw SQS message to a Message object.

        This method extracts type information from message attributes and uses
        the listener function's type hints to determine the target type for
        deserialization.

        Args:
            raw_message: The raw message dict from SQS
            queue_url: The URL of the queue
            listener_func: The listener function (for type hint extraction)

        Returns:
            Message object with deserialized body

        Raises:
            DeserializationError: If deserialization fails
        """
        # Extract type information from message attributes
        type_info = {}
        msg_attrs = raw_message.get("MessageAttributes", {})
        for key, value in msg_attrs.items():
            if key.startswith("__"):
                type_info[key] = value.get("StringValue", "")

        # Get target type from listener function's type hints
        target_type = self._get_listener_target_type(listener_func)

        # Deserialize body
        try:
            body = self.converter.deserialize(raw_message["Body"], type_info, target_type)
        except Exception as e:
            raise DeserializationError(
                f"Failed to deserialize message {raw_message.get('MessageId', 'unknown')}: {e}"
            ) from e

        # Create Message object
        return Message(
            message_id=raw_message["MessageId"],
            receipt_handle=raw_message["ReceiptHandle"],
            body=body,
            attributes=raw_message.get("Attributes", {}),
            message_attributes=msg_attrs,
            queue_url=queue_url,
        )

    def _get_listener_target_type(self, listener_func: Callable[..., Any]) -> Type[Any]:
        """
        Extract the target type for deserialization from listener function's type hints.

        This method looks at the first parameter of the listener function
        (excluding 'self' for methods) to determine what type to deserialize to.

        Args:
            listener_func: The listener function

        Returns:
            Target type for deserialization (defaults to dict if not found)
        """
        # Try to get type hints stored by decorator
        if hasattr(listener_func, "__sqs_type_hints__"):
            type_hints = listener_func.__sqs_type_hints__
        else:
            try:
                type_hints = get_type_hints(listener_func)
            except Exception:
                type_hints = {}

        # Get function signature
        sig = inspect.signature(listener_func)
        params = list(sig.parameters.values())

        # Find the first parameter (skip 'self' if present)
        for param in params:
            if param.name == "self":
                continue

            # Check if this parameter has a type hint
            if param.name in type_hints:
                target_type: Type[Any] = type_hints[param.name]
                return target_type

            # If no type hint, default to dict
            return dict

        # No parameters found, default to dict
        return dict

    def _invoke_listener(
        self,
        listener_func: Callable[..., Any],
        message: Message,
        config: ListenerConfig,
    ) -> None:
        """
        Invoke a listener function with a message.

        This method handles:
        - Single-message vs batch mode
        - Manual vs automatic acknowledgement
        - Exception handling
        - Custom error handler invocation
        - Acknowledgement based on configured strategy

        Args:
            listener_func: The listener function to invoke
            message: The deserialized message
            config: The listener configuration
        """
        # Get function signature to determine parameters
        sig = inspect.signature(listener_func)
        params = list(sig.parameters.keys())

        # Remove 'self' if present (for methods)
        if params and params[0] == "self":
            params = params[1:]

        # Prepare arguments
        args = []

        # First parameter is always the message body
        if params:
            args.append(message.body)

        # Check if listener expects an Acknowledgement handle
        needs_ack_handle = (
            len(params) > 1 and config.acknowledgement_mode == AcknowledgementMode.MANUAL
        )

        if needs_ack_handle:
            # Create acknowledgement handle
            ack_handle = Acknowledgement(
                queue_url=message.queue_url,
                receipt_handle=message.receipt_handle,
                processor=self.acknowledgement_processor,
            )
            args.append(ack_handle)

        # Invoke listener and handle exceptions
        success = False
        exception_to_raise: Optional[Exception] = None

        try:
            listener_func(*args)
            success = True

            # Track successful processing metric
            self.metrics_collector.increment_processed(message.queue_url, 1)

        except Exception as e:
            logger.exception(
                "Listener raised exception for message",
                listener_name=listener_func.__name__,
                message_id=message.message_id,
            )

            # Track failed processing metric
            self.metrics_collector.increment_failed(message.queue_url, 1)

            # Invoke custom error handler if configured
            if config.error_handler:
                try:
                    # Prepare context for error handler
                    context = {
                        "message_id": message.message_id,
                        "queue_url": message.queue_url,
                        "listener_name": listener_func.__name__,
                        "attributes": message.attributes,
                        "message_attributes": message.message_attributes,
                    }

                    # Invoke the error handler
                    config.error_handler(e, message.body, context)

                except Exception as handler_error:
                    logger.exception(
                        "Error handler raised exception for message",
                        message_id=message.message_id,
                    )

            # Wrap in ListenerError for clarity
            exception_to_raise = ListenerError(f"Listener {listener_func.__name__} failed: {e}")

        finally:
            # Handle acknowledgement based on strategy
            if config.acknowledgement_mode == AcknowledgementMode.ON_SUCCESS:
                if success:
                    self.acknowledgement_processor.acknowledge(
                        message.queue_url, message.receipt_handle
                    )
                    # Track acknowledged message metric
                    self.metrics_collector.increment_acknowledged(message.queue_url, 1)
            elif config.acknowledgement_mode == AcknowledgementMode.ALWAYS:
                self.acknowledgement_processor.acknowledge(
                    message.queue_url, message.receipt_handle
                )
                # Track acknowledged message metric
                self.metrics_collector.increment_acknowledged(message.queue_url, 1)
            # For MANUAL mode, the listener is responsible for acknowledgement

            # Re-raise exception if one occurred (after acknowledgement handling)
            if exception_to_raise:
                raise exception_to_raise
