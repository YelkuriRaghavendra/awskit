"""
Tests for error handling and resilience features.

This module tests:
- Polling error handling with backoff
- Custom error handlers
"""

from unittest.mock import MagicMock, Mock

import pytest

from awskit.sqs.acknowledgement import AcknowledgementProcessor
from awskit.sqs.backpressure import BackpressureManager
from awskit.config import (
    AcknowledgementConfig,
    AcknowledgementMode,
    BackoffPolicy,
    BackpressureMode,
    ContainerConfig,
    ListenerConfig,
)
from awskit.sqs.container import MessageListenerContainer
from awskit.converter import JsonMessageConverter
from awskit.sqs.decorator import sqs_listener
from awskit.sqs.models import Message
from awskit.sqs.registry import ListenerRegistry


class TestPollingErrorHandling:
    """Tests for polling error handling with backoff."""

    def setup_method(self):
        """Set up test fixtures."""
        ListenerRegistry.clear()
        self.client = MagicMock()
        self.converter = JsonMessageConverter()
        self.ack_processor = AcknowledgementProcessor(self.client, AcknowledgementConfig())
        self.backpressure_manager = BackpressureManager(BackpressureMode.AUTO)

    def test_backoff_calculation_exponential(self):
        """Test that backoff delay increases exponentially."""
        backoff_policy = BackoffPolicy(
            initial_interval_seconds=1.0,
            multiplier=2.0,
            max_interval_seconds=60.0,
        )
        config = ContainerConfig(backoff_policy=backoff_policy)

        container = MessageListenerContainer(
            self.client,
            self.converter,
            self.ack_processor,
            self.backpressure_manager,
            config,
        )

        # Simulate errors for a queue
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        container._error_counts[queue_url] = 0
        container._error_locks[queue_url] = MagicMock()
        container._error_locks[queue_url].__enter__ = Mock(return_value=None)
        container._error_locks[queue_url].__exit__ = Mock(return_value=None)

        # First error: 1.0 * 2^0 = 1.0
        delay = container._calculate_backoff_delay(queue_url)
        assert delay == 1.0

        # Second error: 1.0 * 2^1 = 2.0
        container._error_counts[queue_url] = 1
        delay = container._calculate_backoff_delay(queue_url)
        assert delay == 2.0

        # Third error: 1.0 * 2^2 = 4.0
        container._error_counts[queue_url] = 2
        delay = container._calculate_backoff_delay(queue_url)
        assert delay == 4.0

        # Fourth error: 1.0 * 2^3 = 8.0
        container._error_counts[queue_url] = 3
        delay = container._calculate_backoff_delay(queue_url)
        assert delay == 8.0

    def test_backoff_respects_max_interval(self):
        """Test that backoff delay is capped at max_interval."""
        backoff_policy = BackoffPolicy(
            initial_interval_seconds=1.0,
            multiplier=2.0,
            max_interval_seconds=10.0,
        )
        config = ContainerConfig(backoff_policy=backoff_policy)

        container = MessageListenerContainer(
            self.client,
            self.converter,
            self.ack_processor,
            self.backpressure_manager,
            config,
        )

        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        container._error_counts[queue_url] = 10  # Would be 1024 without cap
        container._error_locks[queue_url] = MagicMock()
        container._error_locks[queue_url].__enter__ = Mock(return_value=None)
        container._error_locks[queue_url].__exit__ = Mock(return_value=None)

        delay = container._calculate_backoff_delay(queue_url)
        assert delay == 10.0  # Capped at max_interval

    def test_error_count_increments_on_polling_error(self):
        """Test that error count increments when polling fails."""
        container = MessageListenerContainer(
            self.client,
            self.converter,
            self.ack_processor,
            self.backpressure_manager,
        )

        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        container._error_counts[queue_url] = 0
        container._error_locks[queue_url] = MagicMock()
        container._error_locks[queue_url].__enter__ = Mock(return_value=None)
        container._error_locks[queue_url].__exit__ = Mock(return_value=None)

        # Increment error count
        count = container._increment_error_count(queue_url)
        assert count == 1

        count = container._increment_error_count(queue_url)
        assert count == 2

    def test_error_count_resets_on_successful_poll(self):
        """Test that error count resets after successful poll."""
        container = MessageListenerContainer(
            self.client,
            self.converter,
            self.ack_processor,
            self.backpressure_manager,
        )

        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        container._error_counts[queue_url] = 5
        container._error_locks[queue_url] = MagicMock()
        container._error_locks[queue_url].__enter__ = Mock(return_value=None)
        container._error_locks[queue_url].__exit__ = Mock(return_value=None)

        # Reset error count
        container._reset_error_count(queue_url)

        # Verify it was reset
        assert container._error_counts[queue_url] == 0


class TestCustomErrorHandlers:
    """Tests for custom error handler functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        ListenerRegistry.clear()
        self.client = MagicMock()
        self.converter = JsonMessageConverter()
        self.ack_processor = AcknowledgementProcessor(self.client, AcknowledgementConfig())
        self.backpressure_manager = BackpressureManager(BackpressureMode.AUTO)

    def test_custom_error_handler_invoked_on_listener_exception(self):
        """Test that custom error handler is invoked when listener raises exception."""
        # Create a mock error handler
        error_handler = Mock()

        # Create listener function that raises an exception
        def failing_listener(message: dict):
            raise ValueError("Test error")

        # Create container
        container = MessageListenerContainer(
            self.client,
            self.converter,
            self.ack_processor,
            self.backpressure_manager,
        )

        # Create message
        message = Message(
            message_id="test-msg-1",
            receipt_handle="test-receipt-1",
            body={"test": "data"},
            attributes={},
            message_attributes={},
            queue_url="https://sqs.us-east-1.amazonaws.com/123456789012/test-queue",
        )

        # Create config with error handler
        config = ListenerConfig(
            queue="test-queue",
            acknowledgement_mode=AcknowledgementMode.ON_SUCCESS,
            error_handler=error_handler,
        )

        # Invoke listener (should raise exception but call error handler)
        with pytest.raises(Exception):
            container._invoke_listener(failing_listener, message, config)

        # Verify error handler was called
        error_handler.assert_called_once()

        # Verify error handler received correct arguments
        call_args = error_handler.call_args
        exception, body, context = call_args[0]

        assert isinstance(exception, ValueError)
        assert str(exception) == "Test error"
        assert body == {"test": "data"}
        assert context["message_id"] == "test-msg-1"
        assert context["queue_url"] == message.queue_url
        assert context["listener_name"] == "failing_listener"

    def test_custom_error_handler_receives_full_context(self):
        """Test that error handler receives complete context information."""
        error_handler = Mock()

        def failing_listener(message: dict):
            raise RuntimeError("Processing failed")

        container = MessageListenerContainer(
            self.client,
            self.converter,
            self.ack_processor,
            self.backpressure_manager,
        )

        message = Message(
            message_id="msg-123",
            receipt_handle="receipt-456",
            body={"order_id": 789},
            attributes={"ApproximateReceiveCount": "1"},
            message_attributes={"CustomAttr": {"StringValue": "test"}},
            queue_url="https://sqs.us-east-1.amazonaws.com/123456789012/orders-queue",
        )

        config = ListenerConfig(
            queue="orders-queue",
            error_handler=error_handler,
        )

        with pytest.raises(Exception):
            container._invoke_listener(failing_listener, message, config)

        # Verify context contains all expected fields
        call_args = error_handler.call_args
        _, _, context = call_args[0]

        assert context["message_id"] == "msg-123"
        assert context["queue_url"] == message.queue_url
        assert context["listener_name"] == "failing_listener"
        assert context["attributes"] == {"ApproximateReceiveCount": "1"}
        assert "CustomAttr" in context["message_attributes"]

    def test_error_handler_exception_is_logged_but_not_raised(self):
        """Test that exceptions in error handler are logged but don't prevent processing."""

        def buggy_error_handler(exception, message, context):
            raise RuntimeError("Error handler itself failed")

        def failing_listener(message: dict):
            raise ValueError("Listener failed")

        container = MessageListenerContainer(
            self.client,
            self.converter,
            self.ack_processor,
            self.backpressure_manager,
        )

        message = Message(
            message_id="test-msg",
            receipt_handle="test-receipt",
            body={"data": "test"},
            attributes={},
            message_attributes={},
            queue_url="https://sqs.us-east-1.amazonaws.com/123456789012/test-queue",
        )

        config = ListenerConfig(
            queue="test-queue",
            error_handler=buggy_error_handler,
        )

        # Should still raise the original listener exception
        with pytest.raises(Exception) as exc_info:
            container._invoke_listener(failing_listener, message, config)

        # The raised exception should be the listener error, not the error handler error
        assert "Listener failed" in str(exc_info.value)

    def test_no_error_handler_means_normal_exception_handling(self):
        """Test that without error handler, exceptions are handled normally."""

        def failing_listener(message: dict):
            raise ValueError("Test error")

        container = MessageListenerContainer(
            self.client,
            self.converter,
            self.ack_processor,
            self.backpressure_manager,
        )

        message = Message(
            message_id="test-msg",
            receipt_handle="test-receipt",
            body={"data": "test"},
            attributes={},
            message_attributes={},
            queue_url="https://sqs.us-east-1.amazonaws.com/123456789012/test-queue",
        )

        config = ListenerConfig(
            queue="test-queue",
            error_handler=None,  # No error handler
        )

        # Should raise exception normally
        with pytest.raises(Exception) as exc_info:
            container._invoke_listener(failing_listener, message, config)

        assert "Test error" in str(exc_info.value)

    def test_error_handler_with_decorator(self):
        """Test that error handler can be configured via decorator."""
        ListenerRegistry.clear()

        error_handler = Mock()

        @sqs_listener("test-queue", error_handler=error_handler)
        def my_listener(message: dict):
            pass

        # Verify listener was registered with error handler
        listeners = ListenerRegistry.get_listeners()
        assert len(listeners) == 1

        _, config = listeners[0]
        assert config.error_handler is error_handler
