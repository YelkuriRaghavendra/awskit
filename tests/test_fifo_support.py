"""
Tests for FIFO queue support in MessageListenerContainer.
"""

from dataclasses import dataclass
from unittest.mock import MagicMock

from awskit.sqs import (
    AcknowledgementProcessor,
    BackpressureManager,
    ListenerRegistry,
    MessageListenerContainer,
    sqs_listener,
)
from awskit.config import (
    AcknowledgementConfig,
    BackpressureMode,
)
from awskit.converter import JsonMessageConverter


@dataclass
class TestMessage:
    """Test message type."""

    id: str
    content: str


class TestFifoSupport:
    """Tests for FIFO queue support."""

    def setup_method(self):
        """Clear registry before each test."""
        ListenerRegistry.clear()

    def teardown_method(self):
        """Clear registry after each test."""
        ListenerRegistry.clear()

    def test_is_fifo_queue_detection(self):
        """Test FIFO queue detection based on .fifo suffix."""
        # Create mock client
        client = MagicMock()
        client.get_queue_url.return_value = {
            "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue.fifo"
        }

        # Register a listener
        @sqs_listener("test-queue.fifo")
        def my_listener(message: dict):
            pass

        # Create container
        converter = JsonMessageConverter()
        ack_processor = AcknowledgementProcessor(client, AcknowledgementConfig())
        backpressure = BackpressureManager(BackpressureMode.AUTO)

        container = MessageListenerContainer(
            client=client,
            converter=converter,
            acknowledgement_processor=ack_processor,
            backpressure_manager=backpressure,
        )

        # Verify FIFO queue is detected
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue.fifo"
        assert container._is_fifo_queue(queue_url) is True

        # Verify non-FIFO queue is not detected as FIFO
        standard_queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/standard-queue"
        assert container._is_fifo_queue(standard_queue_url) is False

    def test_fifo_queue_initializes_message_group_tracking(self):
        """Test FIFO queue initializes message group tracking structures."""
        # Create mock client
        client = MagicMock()
        client.get_queue_url.return_value = {
            "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue.fifo"
        }

        # Register a listener
        @sqs_listener("test-queue.fifo")
        def my_listener(message: dict):
            pass

        # Create container
        converter = JsonMessageConverter()
        ack_processor = AcknowledgementProcessor(client, AcknowledgementConfig())
        backpressure = BackpressureManager(BackpressureMode.AUTO)

        container = MessageListenerContainer(
            client=client,
            converter=converter,
            acknowledgement_processor=ack_processor,
            backpressure_manager=backpressure,
        )

        # Verify message group tracking is initialized
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue.fifo"
        assert queue_url in container._active_message_groups
        assert queue_url in container._message_group_locks
        assert isinstance(container._active_message_groups[queue_url], set)

    def test_get_message_group_id_extracts_from_attributes(self):
        """Test extracting message group ID from message attributes."""
        # Create mock client
        client = MagicMock()
        client.get_queue_url.return_value = {
            "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue.fifo"
        }

        # Register a listener
        @sqs_listener("test-queue.fifo")
        def my_listener(message: dict):
            pass

        # Create container
        converter = JsonMessageConverter()
        ack_processor = AcknowledgementProcessor(client, AcknowledgementConfig())
        backpressure = BackpressureManager(BackpressureMode.AUTO)

        container = MessageListenerContainer(
            client=client,
            converter=converter,
            acknowledgement_processor=ack_processor,
            backpressure_manager=backpressure,
        )

        # Test message with message group ID
        message_with_group = {"MessageId": "msg-1", "Attributes": {"MessageGroupId": "group-1"}}
        assert container._get_message_group_id(message_with_group) == "group-1"

        # Test message without message group ID
        message_without_group = {"MessageId": "msg-2", "Attributes": {}}
        assert container._get_message_group_id(message_without_group) is None

    def test_extend_visibility_for_message_group_calls_sqs(self):
        """Test extending visibility timeout for message group."""
        # Create mock client
        client = MagicMock()
        client.get_queue_url.return_value = {
            "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue.fifo"
        }

        # Register a listener
        @sqs_listener("test-queue.fifo")
        def my_listener(message: dict):
            pass

        # Create container
        converter = JsonMessageConverter()
        ack_processor = AcknowledgementProcessor(client, AcknowledgementConfig())
        backpressure = BackpressureManager(BackpressureMode.AUTO)

        container = MessageListenerContainer(
            client=client,
            converter=converter,
            acknowledgement_processor=ack_processor,
            backpressure_manager=backpressure,
        )

        # Create test messages in the same group
        messages = [
            {
                "MessageId": "msg-1",
                "ReceiptHandle": "handle-1",
                "Attributes": {"MessageGroupId": "group-1"},
            },
            {
                "MessageId": "msg-2",
                "ReceiptHandle": "handle-2",
                "Attributes": {"MessageGroupId": "group-1"},
            },
            {
                "MessageId": "msg-3",
                "ReceiptHandle": "handle-3",
                "Attributes": {"MessageGroupId": "group-2"},
            },
        ]

        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue.fifo"

        # Extend visibility for group-1
        container._extend_visibility_for_message_group(queue_url, "group-1", messages, 60)

        # Verify change_message_visibility was called for messages in group-1
        assert client.change_message_visibility.call_count == 2
        calls = client.change_message_visibility.call_args_list

        # Check first call
        assert calls[0][1]["QueueUrl"] == queue_url
        assert calls[0][1]["ReceiptHandle"] == "handle-1"
        assert calls[0][1]["VisibilityTimeout"] == 60

        # Check second call
        assert calls[1][1]["QueueUrl"] == queue_url
        assert calls[1][1]["ReceiptHandle"] == "handle-2"
        assert calls[1][1]["VisibilityTimeout"] == 60

    def test_message_group_serialization(self):
        """Test that message group acquire/release works correctly."""
        # Create mock client
        client = MagicMock()
        client.get_queue_url.return_value = {
            "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue.fifo"
        }

        # Register a listener
        @sqs_listener("test-queue.fifo")
        def my_listener(message: dict):
            pass

        # Create container
        converter = JsonMessageConverter()
        ack_processor = AcknowledgementProcessor(client, AcknowledgementConfig())
        backpressure = BackpressureManager(BackpressureMode.AUTO)

        container = MessageListenerContainer(
            client=client,
            converter=converter,
            acknowledgement_processor=ack_processor,
            backpressure_manager=backpressure,
        )

        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue.fifo"

        # Acquire message group
        container._acquire_message_group(queue_url, "group-1")

        # Verify group is marked as active
        assert "group-1" in container._active_message_groups[queue_url]

        # Release message group
        container._release_message_group(queue_url, "group-1")

        # Verify group is no longer active
        assert "group-1" not in container._active_message_groups[queue_url]
