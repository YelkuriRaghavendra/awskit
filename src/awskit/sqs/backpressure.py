"""
Backpressure management for controlling message polling rate.

This module provides the BackpressureManager class that manages polling rate
and concurrent message processing based on message availability and processing
capacity.
"""

from threading import Semaphore

import structlog

from awskit.config import BackpressureMode, ListenerConfig

logger = structlog.get_logger(__name__)


class BackpressureManager:
    """
    Manages backpressure and polling rate based on message availability.

    The BackpressureManager controls when queues should be polled and limits
    concurrent message processing using semaphores. It supports multiple modes:
    - AUTO: Switches between low and high throughput based on message availability
    - ALWAYS_POLL_MAX: Always polls for maximum messages
    - FIXED_HIGH_THROUGHPUT: Always uses parallel polls at high rate

    Attributes:
        mode: The backpressure mode to use
    """

    def __init__(self, mode: BackpressureMode):
        """
        Initialize the BackpressureManager.

        Args:
            mode: The backpressure mode to use
        """
        self.mode = mode
        self._high_throughput_mode: dict[str, bool] = {}
        self._semaphores: dict[str, Semaphore] = {}

    def should_poll(self, queue_url: str, config: ListenerConfig) -> bool:
        """
        Determine if we should poll this queue now.

        This method checks if there are available permits (capacity) to process
        more messages from the queue.

        Args:
            queue_url: The URL of the queue
            config: The listener configuration for this queue

        Returns:
            True if the queue should be polled, False otherwise
        """
        # Ensure semaphore exists for this queue
        if queue_url not in self._semaphores:
            self._semaphores[queue_url] = Semaphore(config.max_concurrent_messages)

        # Check if we have available capacity
        # We can poll if we can acquire at least one permit
        semaphore = self._semaphores[queue_url]
        can_acquire = semaphore.acquire(blocking=False)
        if can_acquire:
            # Release it immediately - we're just checking
            semaphore.release()
            return True
        return False

    def acquire_permit(self, queue_url: str, count: int = 1) -> bool:
        """
        Try to acquire permits for processing messages.

        This method attempts to acquire the specified number of permits from
        the semaphore for the given queue. If successful, the caller can
        proceed with processing that many messages.

        Args:
            queue_url: The URL of the queue
            count: Number of permits to acquire (default: 1)

        Returns:
            True if permits were acquired, False otherwise
        """
        if queue_url not in self._semaphores:
            # This shouldn't happen if should_poll is called first
            # But we'll handle it gracefully
            return False

        semaphore = self._semaphores[queue_url]

        # Try to acquire the requested number of permits
        acquired = 0
        for _ in range(count):
            if semaphore.acquire(blocking=False):
                acquired += 1
            else:
                # Couldn't acquire all requested permits
                # Release what we acquired and return False
                for _ in range(acquired):
                    semaphore.release()
                return False

        return True

    def release_permit(self, queue_url: str, count: int = 1) -> None:
        """
        Release permits after message processing.

        This method releases the specified number of permits back to the
        semaphore for the given queue, allowing more messages to be processed.

        Args:
            queue_url: The URL of the queue
            count: Number of permits to release (default: 1)
        """
        if queue_url not in self._semaphores:
            # This shouldn't happen, but we'll handle it gracefully
            return

        semaphore = self._semaphores[queue_url]
        for _ in range(count):
            semaphore.release()

    def on_messages_received(self, queue_url: str, count: int) -> None:
        """
        Update state when messages are received.

        In AUTO mode, receiving messages switches the queue to high-throughput
        mode. In other modes, this is a no-op.

        Args:
            queue_url: The URL of the queue
            count: Number of messages received
        """
        if self.mode == BackpressureMode.AUTO and count > 0:
            # Switch to high-throughput mode when messages are available
            self._high_throughput_mode.get(queue_url, False)
            self._high_throughput_mode[queue_url] = True

    def on_empty_poll(self, queue_url: str) -> None:
        """
        Update state when a poll returns no messages.

        In AUTO mode, an empty poll switches the queue back to low-throughput
        mode. In other modes, this is a no-op.

        Args:
            queue_url: The URL of the queue
        """
        if self.mode == BackpressureMode.AUTO:
            # Switch to low-throughput mode when no messages are available
            self._high_throughput_mode.get(queue_url, False)
            self._high_throughput_mode[queue_url] = False
        if self.mode == BackpressureMode.AUTO:
            # Switch to low-throughput mode when no messages are available
            self._high_throughput_mode[queue_url] = False

    def is_high_throughput_mode(self, queue_url: str) -> bool:
        """
        Check if the queue is in high-throughput mode.

        Args:
            queue_url: The URL of the queue

        Returns:
            True if in high-throughput mode, False otherwise
        """
        if self.mode == BackpressureMode.ALWAYS_POLL_MAX:
            return True
        elif self.mode == BackpressureMode.FIXED_HIGH_THROUGHPUT:
            return True
        elif self.mode == BackpressureMode.AUTO:
            return self._high_throughput_mode.get(queue_url, False)
        return False

    def initialize_queue(self, queue_url: str, max_concurrent_messages: int) -> None:
        """
        Initialize tracking for a new queue.

        This method sets up the semaphore and throughput mode tracking for
        a queue. It should be called when a queue is first registered.

        Args:
            queue_url: The URL of the queue
            max_concurrent_messages: Maximum concurrent messages for this queue
        """
        if queue_url not in self._semaphores:
            self._semaphores[queue_url] = Semaphore(max_concurrent_messages)

        if queue_url not in self._high_throughput_mode:
            # Start in low-throughput mode (AUTO mode starts low)
            self._high_throughput_mode[queue_url] = False
