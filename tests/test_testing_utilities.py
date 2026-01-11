"""
Tests for testing utilities.

This module tests the testing utilities provided by the library,
including MockSqsTemplate, trigger_listener, and other test helpers.
"""

import pytest

from awskit.config import AcknowledgementMode, ListenerConfig
from awskit.converter import JsonMessageConverter
from awskit.sqs.decorator import sqs_listener
from awskit.sqs.registry import ListenerRegistry
from awskit.sqs.testing import (
    MockSqsTemplate,
    create_test_message,
    disable_listener_registration,
    get_listener_type_hint,
    trigger_listener,
    wait_for_processing,
)


class TestMockSqsTemplate:
    """Tests for MockSqsTemplate."""

    def test_send_records_message(self):
        """Test that send() records messages."""
        converter = JsonMessageConverter()
        template = MockSqsTemplate(converter)

        result = template.send("test-queue", {"order_id": 123})

        assert result.message_id is not None
        assert len(template.sent_messages) == 1
        assert template.sent_messages[0]["queue"] == "test-queue"
        assert template.sent_messages[0]["payload"] == {"order_id": 123}

    def test_send_with_attributes(self):
        """Test that send() records message attributes."""
        converter = JsonMessageConverter()
        template = MockSqsTemplate(converter)

        result = template.send(
            "test-queue",
            {"data": "test"},
            delay_seconds=10,
            message_attributes={"priority": "high"},
        )

        assert result.message_id is not None
        assert len(template.sent_messages) == 1
        msg = template.sent_messages[0]
        assert msg["delay_seconds"] == 10
        assert msg["message_attributes"]["priority"] == "high"

    def test_send_fifo_requires_group_id(self):
        """Test that FIFO queues require message_group_id."""
        converter = JsonMessageConverter()
        template = MockSqsTemplate(converter)

        with pytest.raises(ValueError, match="message_group_id is required"):
            template.send("test-queue.fifo", {"data": "test"})

    def test_send_fifo_with_group_id(self):
        """Test sending to FIFO queue with message_group_id."""
        converter = JsonMessageConverter()
        template = MockSqsTemplate(converter)

        result = template.send(
            "test-queue.fifo",
            {"data": "test"},
            message_group_id="group-1",
        )

        assert result.message_id is not None
        assert result.sequence_number is not None
        assert len(template.sent_messages) == 1
        msg = template.sent_messages[0]
        assert msg["message_group_id"] == "group-1"
        assert msg["is_fifo"] is True

    def test_send_batch(self):
        """Test that send_batch() records all messages."""
        converter = JsonMessageConverter()
        template = MockSqsTemplate(converter)

        payloads = [{"id": 1}, {"id": 2}, {"id": 3}]
        result = template.send_batch("test-queue", payloads)

        assert len(result.successful) == 3
        assert len(result.failed) == 0
        assert len(template.sent_messages) == 3
        assert template.sent_messages[0]["payload"] == {"id": 1}
        assert template.sent_messages[1]["payload"] == {"id": 2}
        assert template.sent_messages[2]["payload"] == {"id": 3}

    def test_send_batch_empty_raises_error(self):
        """Test that send_batch() raises error for empty batch."""
        converter = JsonMessageConverter()
        template = MockSqsTemplate(converter)

        with pytest.raises(ValueError, match="Cannot send empty batch"):
            template.send_batch("test-queue", [])

    def test_send_batch_too_large_raises_error(self):
        """Test that send_batch() raises error for batch > 10."""
        converter = JsonMessageConverter()
        template = MockSqsTemplate(converter)

        payloads = [{"id": i} for i in range(11)]

        with pytest.raises(ValueError, match="exceeds maximum of 10"):
            template.send_batch("test-queue", payloads)

    def test_receive_returns_sent_messages(self):
        """Test that receive() returns previously sent messages."""
        converter = JsonMessageConverter()
        template = MockSqsTemplate(converter)

        # Send messages
        template.send("test-queue", {"id": 1})
        template.send("test-queue", {"id": 2})
        template.send("other-queue", {"id": 3})

        # Receive from test-queue
        messages = template.receive("test-queue", max_messages=2)

        assert len(messages) == 2
        assert messages[0].body == {"id": 1}
        assert messages[1].body == {"id": 2}

    def test_clear_removes_all_messages(self):
        """Test that clear() removes all recorded messages."""
        converter = JsonMessageConverter()
        template = MockSqsTemplate(converter)

        template.send("test-queue", {"data": "test"})
        assert len(template.sent_messages) == 1

        template.clear()
        assert len(template.sent_messages) == 0

    def test_get_messages_for_queue(self):
        """Test get_messages_for_queue() filters by queue."""
        converter = JsonMessageConverter()
        template = MockSqsTemplate(converter)

        template.send("queue-1", {"data": "test1"})
        template.send("queue-2", {"data": "test2"})
        template.send("queue-1", {"data": "test3"})

        messages = template.get_messages_for_queue("queue-1")

        assert len(messages) == 2
        assert messages[0]["payload"] == {"data": "test1"}
        assert messages[1]["payload"] == {"data": "test3"}

    def test_get_message_count(self):
        """Test get_message_count() returns correct counts."""
        converter = JsonMessageConverter()
        template = MockSqsTemplate(converter)

        template.send("queue-1", {"data": "test1"})
        template.send("queue-1", {"data": "test2"})
        template.send("queue-2", {"data": "test3"})

        assert template.get_message_count() == 3
        assert template.get_message_count("queue-1") == 2
        assert template.get_message_count("queue-2") == 1
        assert template.get_message_count("queue-3") == 0


class TestDisableListenerRegistration:
    """Tests for disable_listener_registration context manager."""

    def test_disables_registration(self):
        """Test that registration is disabled within context."""
        ListenerRegistry.clear()

        with disable_listener_registration():
            @sqs_listener("test-queue")
            def my_listener(message: dict):
                pass

            # Listener should not be registered
            assert len(ListenerRegistry.get_listeners()) == 0

    def test_restores_registration(self):
        """Test that registration is restored after context."""
        ListenerRegistry.clear()

        # Register a listener before context
        @sqs_listener("queue-1")
        def listener1(message: dict):
            pass

        assert len(ListenerRegistry.get_listeners()) == 1

        with disable_listener_registration():
            # Existing registrations remain, but new ones are blocked
            assert len(ListenerRegistry.get_listeners()) == 1

            @sqs_listener("queue-2")
            def listener2(message: dict):
                pass

            # listener2 should not be registered
            assert len(ListenerRegistry.get_listeners()) == 1

        # After context, registration should work again
        @sqs_listener("queue-3")
        def listener3(message: dict):
            pass

        # Now we should have listener1 and listener3 (listener2 was blocked)
        assert len(ListenerRegistry.get_listeners()) == 2
        listeners = ListenerRegistry.get_listeners()
        queues = [config.queue for _, config in listeners]
        assert "queue-1" in queues
        assert "queue-3" in queues
        assert "queue-2" not in queues


class TestTriggerListener:
    """Tests for trigger_listener function."""

    def test_triggers_simple_listener(self):
        """Test triggering a simple listener function."""
        result_holder = []

        def my_listener(message: dict):
            result_holder.append(message)
            return message["value"] * 2

        result = trigger_listener(my_listener, {"value": 5})

        assert result == 10
        assert result_holder[0] == {"value": 5}

    def test_triggers_listener_with_type_hint(self):
        """Test triggering listener with type hint."""
        from dataclasses import dataclass

        @dataclass
        class Order:
            order_id: int
            amount: float

        result_holder = []

        def order_listener(message: Order):
            result_holder.append(message)
            return message.order_id

        order = Order(order_id=123, amount=99.99)
        result = trigger_listener(order_listener, order)

        assert result == 123
        assert result_holder[0] == order


class TestWaitForProcessing:
    """Tests for wait_for_processing function."""

    def test_returns_true_when_condition_met(self):
        """Test that function returns True when condition is met."""
        counter = [0]

        def condition():
            counter[0] += 1
            return counter[0] >= 3

        result = wait_for_processing(condition, timeout_seconds=1.0, poll_interval_seconds=0.1)

        assert result is True
        assert counter[0] >= 3

    def test_returns_false_on_timeout(self):
        """Test that function returns False on timeout."""

        def condition():
            return False

        result = wait_for_processing(condition, timeout_seconds=0.5, poll_interval_seconds=0.1)

        assert result is False

    def test_returns_immediately_if_condition_true(self):
        """Test that function returns immediately if condition is already true."""
        import time

        def condition():
            return True

        start = time.time()
        result = wait_for_processing(condition, timeout_seconds=5.0, poll_interval_seconds=0.1)
        elapsed = time.time() - start

        assert result is True
        assert elapsed < 0.5  # Should return almost immediately


class TestCreateTestMessage:
    """Tests for create_test_message function."""

    def test_creates_message_with_defaults(self):
        """Test creating message with default values."""
        message = create_test_message({"data": "test"})

        assert message.body == {"data": "test"}
        assert message.message_id == "test-message-id"
        assert message.receipt_handle == "test-receipt-handle"
        assert message.attributes == {}
        assert message.message_attributes == {}

    def test_creates_message_with_custom_values(self):
        """Test creating message with custom values."""
        message = create_test_message(
            {"data": "test"},
            message_id="custom-id",
            receipt_handle="custom-handle",
            message_attributes={"priority": "high"},
        )

        assert message.body == {"data": "test"}
        assert message.message_id == "custom-id"
        assert message.receipt_handle == "custom-handle"
        assert message.message_attributes["priority"] == "high"


class TestGetListenerTypeHint:
    """Tests for get_listener_type_hint function."""

    def test_extracts_dict_type_hint(self):
        """Test extracting dict type hint."""

        def my_listener(message: dict):
            pass

        hint = get_listener_type_hint(my_listener)
        assert hint == dict

    def test_extracts_custom_type_hint(self):
        """Test extracting custom type hint."""
        from dataclasses import dataclass

        @dataclass
        class Order:
            order_id: int

        def order_listener(message: Order):
            pass

        hint = get_listener_type_hint(order_listener)
        assert hint == Order

    def test_returns_none_for_no_hint(self):
        """Test returns None when no type hint."""

        def my_listener(message):
            pass

        hint = get_listener_type_hint(my_listener)
        assert hint is None
