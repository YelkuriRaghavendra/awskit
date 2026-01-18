"""
Tests for listener registry and decorator functionality.
"""

import pytest

from awskit.config import (
    AcknowledgementMode,
    FifoGroupStrategy,
    ListenerConfig,
)
from awskit.sqs import (
    ListenerRegistry,
    sqs_listener,
)
from awskit.sqs.models import Acknowledgement


class TestListenerRegistry:
    """Tests for ListenerRegistry."""

    def setup_method(self):
        """Clear registry before each test."""
        ListenerRegistry.clear()

    def teardown_method(self):
        """Clear registry after each test."""
        ListenerRegistry.clear()

    def test_register_and_get_listeners(self):
        """Test registering a listener and retrieving it."""

        def my_listener(message: str):
            pass

        config = ListenerConfig(queue="test-queue")
        ListenerRegistry.register(my_listener, config)

        listeners = ListenerRegistry.get_listeners()
        assert len(listeners) == 1
        assert listeners[0][0] == my_listener
        assert listeners[0][1].queue == "test-queue"

    def test_register_multiple_listeners(self):
        """Test registering multiple listeners."""

        def listener1(message: str):
            pass

        def listener2(message: dict):
            pass

        config1 = ListenerConfig(queue="queue1")
        config2 = ListenerConfig(queue="queue2")

        ListenerRegistry.register(listener1, config1)
        ListenerRegistry.register(listener2, config2)

        listeners = ListenerRegistry.get_listeners()
        assert len(listeners) == 2

    def test_get_listener_config(self):
        """Test retrieving configuration for a specific listener."""

        def my_listener(message: str):
            pass

        config = ListenerConfig(
            queue="test-queue", max_concurrent_messages=5, poll_timeout_seconds=20
        )
        ListenerRegistry.register(my_listener, config)

        retrieved_config = ListenerRegistry.get_listener_config(my_listener)
        assert retrieved_config.queue == "test-queue"
        assert retrieved_config.max_concurrent_messages == 5
        assert retrieved_config.poll_timeout_seconds == 20

    def test_get_listener_config_not_found(self):
        """Test retrieving configuration for unregistered listener raises KeyError."""

        def my_listener(message: str):
            pass

        with pytest.raises(KeyError):
            ListenerRegistry.get_listener_config(my_listener)

    def test_clear(self):
        """Test clearing all registered listeners."""

        def listener1(message: str):
            pass

        def listener2(message: dict):
            pass

        ListenerRegistry.register(listener1, ListenerConfig(queue="queue1"))
        ListenerRegistry.register(listener2, ListenerConfig(queue="queue2"))

        assert len(ListenerRegistry.get_listeners()) == 2

        ListenerRegistry.clear()
        assert len(ListenerRegistry.get_listeners()) == 0


class TestSqsListenerDecorator:
    """Tests for @sqs_listener decorator."""

    def setup_method(self):
        """Clear registry before each test."""
        ListenerRegistry.clear()

    def teardown_method(self):
        """Clear registry after each test."""
        ListenerRegistry.clear()

    def test_basic_decorator(self):
        """Test basic decorator usage."""

        @sqs_listener("test-queue")
        def my_listener(message: str):
            pass

        listeners = ListenerRegistry.get_listeners()
        assert len(listeners) == 1
        assert listeners[0][0] == my_listener
        assert listeners[0][1].queue == "test-queue"

    def test_decorator_with_acknowledgement_mode(self):
        """Test decorator with custom acknowledgement mode."""

        @sqs_listener("test-queue", acknowledgement_mode=AcknowledgementMode.MANUAL)
        def my_listener(message: str, ack: Acknowledgement):
            pass

        config = ListenerRegistry.get_listener_config(my_listener)
        assert config.acknowledgement_mode == AcknowledgementMode.MANUAL

    def test_decorator_with_max_concurrent_messages(self):
        """Test decorator with custom max concurrent messages."""

        @sqs_listener("test-queue", max_concurrent_messages=5)
        def my_listener(message: str):
            pass

        config = ListenerRegistry.get_listener_config(my_listener)
        assert config.max_concurrent_messages == 5

    def test_decorator_with_poll_settings(self):
        """Test decorator with custom poll settings."""

        @sqs_listener("test-queue", max_messages_per_poll=20, poll_timeout_seconds=15)
        def my_listener(message: str):
            pass

        config = ListenerRegistry.get_listener_config(my_listener)
        assert config.max_messages_per_poll == 20
        assert config.poll_timeout_seconds == 15

    def test_decorator_with_batch_mode(self):
        """Test decorator with batch mode enabled."""

        @sqs_listener("test-queue", batch=True)
        def my_listener(messages: list[str]):
            pass

        config = ListenerRegistry.get_listener_config(my_listener)
        assert config.batch is True

    def test_decorator_with_visibility_timeout(self):
        """Test decorator with custom visibility timeout."""

        @sqs_listener("test-queue", visibility_timeout=60)
        def my_listener(message: str):
            pass

        config = ListenerRegistry.get_listener_config(my_listener)
        assert config.visibility_timeout == 60

    def test_decorator_with_fifo_group_strategy(self):
        """Test decorator with FIFO group strategy."""

        @sqs_listener(
            "test-queue.fifo",
            message_group_strategy=FifoGroupStrategy.PARALLEL_BATCHES_PER_GROUP,
        )
        def my_listener(message: str):
            pass

        config = ListenerRegistry.get_listener_config(my_listener)
        assert config.message_group_strategy == FifoGroupStrategy.PARALLEL_BATCHES_PER_GROUP

    def test_decorator_with_all_options(self):
        """Test decorator with all configuration options."""

        @sqs_listener(
            "test-queue",
            acknowledgement_mode=AcknowledgementMode.ALWAYS,
            max_concurrent_messages=3,
            max_messages_per_poll=5,
            poll_timeout_seconds=20,
            batch=True,
            visibility_timeout=120,
            message_group_strategy=FifoGroupStrategy.MIXED_GROUPS_IN_BATCH,
        )
        def my_listener(messages: list[dict]):
            pass

        config = ListenerRegistry.get_listener_config(my_listener)
        assert config.queue == "test-queue"
        assert config.acknowledgement_mode == AcknowledgementMode.ALWAYS
        assert config.max_concurrent_messages == 3
        assert config.max_messages_per_poll == 5
        assert config.poll_timeout_seconds == 20
        assert config.batch is True
        assert config.visibility_timeout == 120
        assert config.message_group_strategy == FifoGroupStrategy.MIXED_GROUPS_IN_BATCH

    def test_decorator_preserves_function(self):
        """Test that decorator returns the original function."""

        @sqs_listener("test-queue")
        def my_listener(message: str):
            return "processed"

        # Function should still be callable and work normally
        result = my_listener("test")
        assert result == "processed"

    def test_decorator_extracts_type_hints(self):
        """Test that decorator extracts type hints from function."""

        @sqs_listener("test-queue")
        def my_listener(message: dict):
            pass

        # Check that type hints are stored
        assert hasattr(my_listener, "__sqs_type_hints__")
        type_hints = my_listener.__sqs_type_hints__
        assert "message" in type_hints
        assert type_hints["message"] is dict

    def test_decorator_extracts_signature(self):
        """Test that decorator extracts function signature."""

        @sqs_listener("test-queue")
        def my_listener(message: str, ack: Acknowledgement):
            pass

        # Check that signature is stored
        assert hasattr(my_listener, "__sqs_signature__")
        sig = my_listener.__sqs_signature__
        assert "message" in sig.parameters
        assert "ack" in sig.parameters

    def test_multiple_decorated_listeners(self):
        """Test decorating multiple listeners."""

        @sqs_listener("queue1")
        def listener1(message: str):
            pass

        @sqs_listener("queue2", max_concurrent_messages=5)
        def listener2(message: dict):
            pass

        @sqs_listener("queue3", batch=True)
        def listener3(messages: list[str]):
            pass

        listeners = ListenerRegistry.get_listeners()
        assert len(listeners) == 3

        # Verify each listener has correct configuration
        configs = dict(listeners)
        assert configs[listener1].queue == "queue1"
        assert configs[listener2].queue == "queue2"
        assert configs[listener2].max_concurrent_messages == 5
        assert configs[listener3].queue == "queue3"
        assert configs[listener3].batch is True

    def test_decorator_with_no_type_hints(self):
        """Test decorator works with functions that have no type hints."""

        @sqs_listener("test-queue")
        def my_listener(message):
            pass

        # Should still register successfully
        listeners = ListenerRegistry.get_listeners()
        assert len(listeners) == 1

        # Type hints should be empty dict
        assert hasattr(my_listener, "__sqs_type_hints__")
