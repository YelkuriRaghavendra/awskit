"""
Unit tests for BackpressureManager.
"""


from awskit.sqs.backpressure import BackpressureManager
from awskit.config import BackpressureMode, ListenerConfig


class TestBackpressureManager:
    """Tests for BackpressureManager."""

    def test_initialize_queue(self) -> None:
        """Test initializing a queue with semaphore."""
        manager = BackpressureManager(BackpressureMode.AUTO)
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"

        manager.initialize_queue(queue_url, max_concurrent_messages=5)

        assert queue_url in manager._semaphores
        assert queue_url in manager._high_throughput_mode
        assert manager._high_throughput_mode[queue_url] is False

    def test_should_poll_with_available_capacity(self) -> None:
        """Test should_poll returns True when capacity is available."""
        manager = BackpressureManager(BackpressureMode.AUTO)
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        config = ListenerConfig(queue="test-queue", max_concurrent_messages=5)

        # Should be able to poll initially
        assert manager.should_poll(queue_url, config) is True

    def test_should_poll_with_no_capacity(self) -> None:
        """Test should_poll returns False when capacity is exhausted."""
        manager = BackpressureManager(BackpressureMode.AUTO)
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        config = ListenerConfig(queue="test-queue", max_concurrent_messages=2)

        manager.initialize_queue(queue_url, max_concurrent_messages=2)

        # Acquire all permits
        assert manager.acquire_permit(queue_url, count=2) is True

        # Should not be able to poll now
        assert manager.should_poll(queue_url, config) is False

        # Release permits
        manager.release_permit(queue_url, count=2)

        # Should be able to poll again
        assert manager.should_poll(queue_url, config) is True

    def test_acquire_permit_success(self) -> None:
        """Test acquiring permits successfully."""
        manager = BackpressureManager(BackpressureMode.AUTO)
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"

        manager.initialize_queue(queue_url, max_concurrent_messages=5)

        # Should be able to acquire 3 permits
        assert manager.acquire_permit(queue_url, count=3) is True

    def test_acquire_permit_failure(self) -> None:
        """Test acquiring permits fails when not enough capacity."""
        manager = BackpressureManager(BackpressureMode.AUTO)
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"

        manager.initialize_queue(queue_url, max_concurrent_messages=2)

        # Acquire 2 permits
        assert manager.acquire_permit(queue_url, count=2) is True

        # Try to acquire 1 more - should fail
        assert manager.acquire_permit(queue_url, count=1) is False

    def test_acquire_permit_partial_failure_releases_all(self) -> None:
        """Test that partial acquisition failures release all acquired permits."""
        manager = BackpressureManager(BackpressureMode.AUTO)
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"

        manager.initialize_queue(queue_url, max_concurrent_messages=3)

        # Acquire 2 permits
        assert manager.acquire_permit(queue_url, count=2) is True

        # Try to acquire 2 more (only 1 available) - should fail and release nothing
        assert manager.acquire_permit(queue_url, count=2) is False

        # Should still be able to acquire 1 more
        assert manager.acquire_permit(queue_url, count=1) is True

    def test_release_permit(self) -> None:
        """Test releasing permits."""
        manager = BackpressureManager(BackpressureMode.AUTO)
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"

        manager.initialize_queue(queue_url, max_concurrent_messages=3)

        # Acquire all permits
        assert manager.acquire_permit(queue_url, count=3) is True

        # Release 2 permits
        manager.release_permit(queue_url, count=2)

        # Should be able to acquire 2 more
        assert manager.acquire_permit(queue_url, count=2) is True

    def test_on_messages_received_auto_mode(self) -> None:
        """Test on_messages_received switches to high-throughput in AUTO mode."""
        manager = BackpressureManager(BackpressureMode.AUTO)
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"

        manager.initialize_queue(queue_url, max_concurrent_messages=5)

        # Initially in low-throughput mode
        assert manager.is_high_throughput_mode(queue_url) is False

        # Receive messages
        manager.on_messages_received(queue_url, count=5)

        # Should switch to high-throughput mode
        assert manager.is_high_throughput_mode(queue_url) is True

    def test_on_empty_poll_auto_mode(self) -> None:
        """Test on_empty_poll switches to low-throughput in AUTO mode."""
        manager = BackpressureManager(BackpressureMode.AUTO)
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"

        manager.initialize_queue(queue_url, max_concurrent_messages=5)

        # Switch to high-throughput mode
        manager.on_messages_received(queue_url, count=5)
        assert manager.is_high_throughput_mode(queue_url) is True

        # Empty poll
        manager.on_empty_poll(queue_url)

        # Should switch back to low-throughput mode
        assert manager.is_high_throughput_mode(queue_url) is False

    def test_always_poll_max_mode(self) -> None:
        """Test ALWAYS_POLL_MAX mode always returns high-throughput."""
        manager = BackpressureManager(BackpressureMode.ALWAYS_POLL_MAX)
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"

        manager.initialize_queue(queue_url, max_concurrent_messages=5)

        # Should always be in high-throughput mode
        assert manager.is_high_throughput_mode(queue_url) is True

        # Empty poll should not change mode
        manager.on_empty_poll(queue_url)
        assert manager.is_high_throughput_mode(queue_url) is True

    def test_fixed_high_throughput_mode(self) -> None:
        """Test FIXED_HIGH_THROUGHPUT mode always returns high-throughput."""
        manager = BackpressureManager(BackpressureMode.FIXED_HIGH_THROUGHPUT)
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"

        manager.initialize_queue(queue_url, max_concurrent_messages=5)

        # Should always be in high-throughput mode
        assert manager.is_high_throughput_mode(queue_url) is True

        # Empty poll should not change mode
        manager.on_empty_poll(queue_url)
        assert manager.is_high_throughput_mode(queue_url) is True

    def test_multiple_queues_independent(self) -> None:
        """Test that multiple queues are tracked independently."""
        manager = BackpressureManager(BackpressureMode.AUTO)
        queue1 = "https://sqs.us-east-1.amazonaws.com/123456789012/queue1"
        queue2 = "https://sqs.us-east-1.amazonaws.com/123456789012/queue2"

        manager.initialize_queue(queue1, max_concurrent_messages=3)
        manager.initialize_queue(queue2, max_concurrent_messages=5)

        # Acquire permits from queue1
        assert manager.acquire_permit(queue1, count=3) is True

        # Should still be able to acquire from queue2
        assert manager.acquire_permit(queue2, count=5) is True

        # Switch queue1 to high-throughput
        manager.on_messages_received(queue1, count=1)
        assert manager.is_high_throughput_mode(queue1) is True
        assert manager.is_high_throughput_mode(queue2) is False

    def test_on_messages_received_zero_count_no_mode_change(self) -> None:
        """Test that receiving 0 messages doesn't change mode."""
        manager = BackpressureManager(BackpressureMode.AUTO)
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"

        manager.initialize_queue(queue_url, max_concurrent_messages=5)

        # Initially in low-throughput mode
        assert manager.is_high_throughput_mode(queue_url) is False

        # Receive 0 messages
        manager.on_messages_received(queue_url, count=0)

        # Should remain in low-throughput mode
        assert manager.is_high_throughput_mode(queue_url) is False

    def test_release_permit_on_uninitialized_queue_graceful(self) -> None:
        """Test that releasing permits on uninitialized queue is handled gracefully."""
        manager = BackpressureManager(BackpressureMode.AUTO)
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"

        # Should not raise an error
        manager.release_permit(queue_url, count=1)

    def test_acquire_permit_on_uninitialized_queue_returns_false(self) -> None:
        """Test that acquiring permits on uninitialized queue returns False."""
        manager = BackpressureManager(BackpressureMode.AUTO)
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"

        # Should return False gracefully
        assert manager.acquire_permit(queue_url, count=1) is False
