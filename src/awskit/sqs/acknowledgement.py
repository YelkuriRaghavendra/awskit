"""
Acknowledgement processor for batching message deletions.

This module provides the AcknowledgementProcessor class which handles
message acknowledgement (deletion) with support for batching to reduce
API calls to SQS.
"""

import structlog
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from queue import Queue
from typing import Any, Deque, Dict, List, Optional

from awskit.config import AcknowledgementConfig, AcknowledgementOrdering

logger = structlog.get_logger(__name__)


@dataclass
class _AckRequest:
    """Internal representation of an acknowledgement request."""

    queue_url: str
    receipt_handle: str
    timestamp: float


class AcknowledgementProcessor:
    """
    Processes message acknowledgements with batching support.

    This processor queues acknowledgement requests and batches them together
    to reduce the number of API calls to SQS. It supports both immediate
    acknowledgement (when interval=0 and threshold=0) and batched acknowledgement
    with configurable interval and threshold.

    For FIFO queues with ordered acknowledgement, messages are acknowledged
    in the order they were received to maintain message group ordering.

    Attributes:
        client: boto3 SQS client for making delete_message_batch calls
        config: Configuration for acknowledgement behavior
    """

    def __init__(self, client: Any, config: AcknowledgementConfig):
        """
        Initialize the acknowledgement processor.

        Args:
            client: boto3 SQS client
            config: Acknowledgement configuration
        """
        self.client = client
        self.config = config
        self._ack_queue: Queue[_AckRequest] = Queue()
        self._worker_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        self._lock = threading.Lock()

        # For ordered acknowledgement (FIFO queues)
        self._ordered_queues: Dict[str, Deque[str]] = defaultdict(deque)

        # Start background worker if batching is enabled
        if self.config.interval_seconds > 0 or self.config.threshold > 0:
            self._start_worker()

    def _start_worker(self) -> None:
        """Start the background worker thread for batch processing."""
        self._worker_thread = threading.Thread(
            target=self._process_acknowledgements, daemon=True, name="AckProcessor"
        )
        self._worker_thread.start()

    def acknowledge(self, queue_url: str, receipt_handle: str) -> None:
        """
        Queue a message for acknowledgement.

        If immediate acknowledgement is configured (interval=0 and threshold=0),
        the message is deleted immediately. Otherwise, it's queued for batching.

        Args:
            queue_url: URL of the queue containing the message
            receipt_handle: Receipt handle of the message to acknowledge
        """
        # Immediate acknowledgement mode
        if self.config.interval_seconds == 0 and self.config.threshold == 0:
            self._delete_message(queue_url, receipt_handle)
            return

        # Ordered acknowledgement for FIFO queues
        if self.config.ordering == AcknowledgementOrdering.ORDERED:
            with self._lock:
                self._ordered_queues[queue_url].append(receipt_handle)
        else:
            # Queue for batched acknowledgement
            request = _AckRequest(
                queue_url=queue_url,
                receipt_handle=receipt_handle,
                timestamp=time.time(),
            )
            self._ack_queue.put(request)

    def acknowledge_batch(self, queue_url: str, receipt_handles: List[str]) -> None:
        """
        Acknowledge multiple messages immediately.

        This method bypasses the batching mechanism and deletes the messages
        immediately using a batch delete operation.

        Args:
            queue_url: URL of the queue containing the messages
            receipt_handles: List of receipt handles to acknowledge
        """
        if not receipt_handles:
            return

        self._delete_messages_batch(queue_url, receipt_handles)

    def flush(self) -> None:
        """
        Flush all pending acknowledgements immediately.

        This method processes all queued acknowledgements without waiting
        for the batch interval or threshold. It's typically called during
        shutdown to ensure no acknowledgements are lost.
        """
        # Process ordered queues first
        if self.config.ordering == AcknowledgementOrdering.ORDERED:
            with self._lock:
                for queue_url, handles in self._ordered_queues.items():
                    if handles:
                        self._delete_messages_batch(queue_url, list(handles))
                        handles.clear()

        # Process regular queue
        pending: Dict[str, List[str]] = defaultdict(list)
        while not self._ack_queue.empty():
            try:
                request = self._ack_queue.get_nowait()
                pending[request.queue_url].append(request.receipt_handle)
            except Exception:
                break

        for queue_url, receipt_handles in pending.items():
            if receipt_handles:
                self._delete_messages_batch(queue_url, receipt_handles)

    def shutdown(self, timeout_seconds: int = 20) -> None:
        """
        Shutdown the acknowledgement processor.

        This method stops the background worker thread and flushes all
        pending acknowledgements.

        Args:
            timeout_seconds: Maximum time to wait for shutdown
        """
        self._shutdown_event.set()

        # Flush pending acknowledgements
        self.flush()

        # Wait for worker thread to finish
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout_seconds)
            if self._worker_thread.is_alive():
                logger.warning(
                    "Acknowledgement processor worker thread did not stop within timeout",
                    timeout_seconds=timeout_seconds,
                )

    def _process_acknowledgements(self) -> None:
        """
        Background worker that batches and sends acknowledgements.

        This method runs in a separate thread and processes acknowledgements
        based on the configured interval and threshold.
        """
        pending: Dict[str, List[str]] = defaultdict(list)
        last_flush_time = time.time()

        while not self._shutdown_event.is_set():
            try:
                # Check if we should flush based on interval
                current_time = time.time()
                time_since_flush = current_time - last_flush_time
                should_flush_by_time = (
                    self.config.interval_seconds > 0
                    and time_since_flush >= self.config.interval_seconds
                )

                # Process ordered queues if it's time to flush
                if should_flush_by_time and self.config.ordering == AcknowledgementOrdering.ORDERED:
                    with self._lock:
                        for queue_url, handles in self._ordered_queues.items():
                            if handles:
                                # Take up to threshold messages
                                batch_size = min(
                                    len(handles),
                                    self.config.threshold if self.config.threshold > 0 else len(handles)
                                )
                                batch = [handles.popleft() for _ in range(batch_size)]
                                self._delete_messages_batch(queue_url, batch)
                    last_flush_time = current_time

                # Try to get a request with a short timeout
                try:
                    request = self._ack_queue.get(timeout=0.1)
                    pending[request.queue_url].append(request.receipt_handle)
                except Exception:
                    # No request available, check if we should flush
                    if should_flush_by_time and pending:
                        for queue_url, receipt_handles in pending.items():
                            if receipt_handles:
                                self._delete_messages_batch(queue_url, receipt_handles)
                        pending.clear()
                        last_flush_time = current_time
                    continue

                # Check if we should flush based on threshold
                should_flush_by_threshold = any(
                    len(handles) >= self.config.threshold
                    for handles in pending.values()
                    if self.config.threshold > 0
                )

                if should_flush_by_threshold or should_flush_by_time:
                    for queue_url, receipt_handles in pending.items():
                        if receipt_handles:
                            self._delete_messages_batch(queue_url, receipt_handles)
                    pending.clear()
                    last_flush_time = current_time

            except Exception as e:
                logger.error(
                    "Error in acknowledgement processor worker",
                    error=str(e),
                    exc_info=True,
                )

        # Flush any remaining pending messages when shutting down
        for queue_url, receipt_handles in pending.items():
            if receipt_handles:
                self._delete_messages_batch(queue_url, receipt_handles)

    def _delete_message(self, queue_url: str, receipt_handle: str) -> None:
        """
        Delete a single message from the queue.

        Args:
            queue_url: URL of the queue
            receipt_handle: Receipt handle of the message
        """
        try:
            self.client.delete_message(
                QueueUrl=queue_url, ReceiptHandle=receipt_handle
            )
        except Exception as e:
            logger.error(
                "Failed to acknowledge message",
                queue_url=queue_url,
                receipt_handle=receipt_handle[:20] + "...",
                error=str(e),
                exc_info=True,
            )

    def _delete_messages_batch(self, queue_url: str, receipt_handles: List[str]) -> None:
        """
        Delete multiple messages from the queue in a batch.

        Args:
            queue_url: URL of the queue
            receipt_handles: List of receipt handles to delete
        """
        if not receipt_handles:
            return

        # SQS batch delete supports up to 10 messages at a time
        batch_size = 10
        for i in range(0, len(receipt_handles), batch_size):
            batch = receipt_handles[i : i + batch_size]
            entries = [
                {"Id": str(idx), "ReceiptHandle": handle}
                for idx, handle in enumerate(batch)
            ]

            try:
                response = self.client.delete_message_batch(
                    QueueUrl=queue_url, Entries=entries
                )

                # Log failures
                if "Failed" in response and response["Failed"]:
                    for failure in response["Failed"]:
                        logger.error(
                            "Failed to acknowledge message in batch",
                            queue_url=queue_url,
                            message_id=failure["Id"],
                            error_code=failure.get("Code", "Unknown"),
                            error_message=failure.get("Message", "No message"),
                        )

            except Exception as e:
                logger.error(
                    "Failed to acknowledge batch of messages",
                    queue_url=queue_url,
                    batch_size=len(batch),
                    error=str(e),
                    exc_info=True,
                )
