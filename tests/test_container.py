"""
Tests for MessageListenerContainer.
"""

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from awskit.sqs import (
    AcknowledgementProcessor,
    BackpressureManager,
    ListenerRegistry,
    MessageListenerContainer,
    sqs_listener,
)
from awskit.config import (
    AcknowledgementConfig,
    AcknowledgementMode,
    BackpressureMode,
    ContainerConfig,
)
from awskit.converter import JsonMessageConverter


@dataclass
class TestMessage:
    """Test message type."""

    id: str
    content: str


class TestMessageListenerContainer:
    """Tests for MessageListenerContainer."""

    def setup_method(self):
        """Clear registry before each test."""
        ListenerRegistry.clear()

    def teardown_method(self):
        """Clear registry after each test."""
        ListenerRegistry.clear()

    def test_container_initialization(self):
        """Test container initializes correctly."""
        # Create mock client
        client = MagicMock()
        client.get_queue_url.return_value = {
            "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        }

        # Register a listener
        @sqs_listener("test-queue")
        def my_listener(message: dict):
            pass

        # Create container
        converter = JsonMessageConverter()
        ack_processor = AcknowledgementProcessor(client, AcknowledgementConfig())
        backpressure = BackpressureManager(BackpressureMode.AUTO)
        config = ContainerConfig()

        container = MessageListenerContainer(
            client=client,
            converter=converter,
            acknowledgement_processor=ack_processor,
            backpressure_manager=backpressure,
            config=config,
        )

        # Verify container loaded the listener
        assert len(container._listeners) == 1
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        assert queue_url in container._listeners

    def test_container_resolves_queue_urls(self):
        """Test container resolves queue names to URLs."""
        # Create mock client
        client = MagicMock()
        client.get_queue_url.return_value = {
            "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789012/my-queue"
        }

        # Register a listener
        @sqs_listener("my-queue")
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

        # Verify get_queue_url was called
        client.get_queue_url.assert_called_once_with(QueueName="my-queue")

    def test_container_handles_queue_url_directly(self):
        """Test container handles queue URLs directly without resolution."""
        # Create mock client
        client = MagicMock()

        # Register a listener with a URL
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"

        @sqs_listener(queue_url)
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

        # Verify get_queue_url was NOT called (URL was used directly)
        client.get_queue_url.assert_not_called()

        # Verify listener was registered
        assert queue_url in container._listeners

    def test_container_initializes_backpressure_for_queues(self):
        """Test container initializes backpressure manager for each queue."""
        # Create mock client
        client = MagicMock()
        client.get_queue_url.side_effect = [
            {"QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789012/queue1"},
            {"QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789012/queue2"},
        ]

        # Register multiple listeners
        @sqs_listener("queue1", max_concurrent_messages=5)
        def listener1(message: dict):
            pass

        @sqs_listener("queue2", max_concurrent_messages=10)
        def listener2(message: dict):
            pass

        # Create container with mock backpressure manager
        converter = JsonMessageConverter()
        ack_processor = AcknowledgementProcessor(client, AcknowledgementConfig())
        backpressure = MagicMock(spec=BackpressureManager)

        container = MessageListenerContainer(
            client=client,
            converter=converter,
            acknowledgement_processor=ack_processor,
            backpressure_manager=backpressure,
        )

        # Verify backpressure manager was initialized for both queues
        assert backpressure.initialize_queue.call_count == 2

    def test_get_listener_target_type_with_type_hints(self):
        """Test extracting target type from listener with type hints."""
        # Create mock client
        client = MagicMock()
        client.get_queue_url.return_value = {
            "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        }

        # Register a listener with type hints
        @sqs_listener("test-queue")
        def my_listener(message: TestMessage):
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

        # Get target type
        target_type = container._get_listener_target_type(my_listener)
        assert target_type == TestMessage

    def test_get_listener_target_type_defaults_to_dict(self):
        """Test target type defaults to dict when no type hints."""
        # Create mock client
        client = MagicMock()
        client.get_queue_url.return_value = {
            "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        }

        # Register a listener without type hints
        @sqs_listener("test-queue")
        def my_listener(message):
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

        # Get target type
        target_type = container._get_listener_target_type(my_listener)
        assert target_type == dict

    def test_container_start_creates_thread_pool(self):
        """Test container start creates thread pool."""
        # Create mock client
        client = MagicMock()
        client.get_queue_url.return_value = {
            "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        }

        # Register a listener
        @sqs_listener("test-queue")
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

        # Start container
        container.start()

        # Verify executor was created
        assert container._executor is not None

        # Verify polling threads were started
        assert len(container._polling_threads) == 1

        # Stop container
        container.stop()

    def test_container_stop_shuts_down_gracefully(self):
        """Test container stop performs graceful shutdown."""
        # Create mock client
        client = MagicMock()
        client.get_queue_url.return_value = {
            "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        }

        # Register a listener
        @sqs_listener("test-queue")
        def my_listener(message: dict):
            pass

        # Create container
        converter = JsonMessageConverter()
        ack_processor = MagicMock(spec=AcknowledgementProcessor)
        backpressure = BackpressureManager(BackpressureMode.AUTO)

        container = MessageListenerContainer(
            client=client,
            converter=converter,
            acknowledgement_processor=ack_processor,
            backpressure_manager=backpressure,
        )

        # Start and stop container
        container.start()
        container.stop()

        # Verify executor was shut down
        assert container._executor is None

        # Verify acknowledgement processor was flushed
        ack_processor.flush.assert_called_once()

    def test_acknowledgement_on_success_mode_acknowledges_on_success(self):
        """Test ON_SUCCESS mode acknowledges message when listener succeeds."""
        # Create mock client
        client = MagicMock()
        client.get_queue_url.return_value = {
            "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        }

        # Register a listener with ON_SUCCESS mode
        @sqs_listener("test-queue", acknowledgement_mode=AcknowledgementMode.ON_SUCCESS)
        def my_listener(message: dict):
            # Listener succeeds
            pass

        # Create container
        converter = JsonMessageConverter()
        ack_processor = MagicMock(spec=AcknowledgementProcessor)
        backpressure = BackpressureManager(BackpressureMode.AUTO)

        container = MessageListenerContainer(
            client=client,
            converter=converter,
            acknowledgement_processor=ack_processor,
            backpressure_manager=backpressure,
        )

        # Create a test message
        from awskit.sqs.models import Message

        message = Message(
            message_id="test-msg-1",
            receipt_handle="test-receipt-1",
            body={"test": "data"},
            attributes={},
            message_attributes={},
            queue_url="https://sqs.us-east-1.amazonaws.com/123456789012/test-queue",
        )

        # Get the listener config
        listener_func, listener_config = container._listeners[
            "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        ][0]

        # Invoke listener
        container._invoke_listener(listener_func, message, listener_config)

        # Verify message was acknowledged
        ack_processor.acknowledge.assert_called_once_with(
            "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue", "test-receipt-1"
        )

    def test_acknowledgement_on_success_mode_does_not_acknowledge_on_failure(self):
        """Test ON_SUCCESS mode does not acknowledge message when listener fails."""
        # Create mock client
        client = MagicMock()
        client.get_queue_url.return_value = {
            "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        }

        # Register a listener with ON_SUCCESS mode that fails
        @sqs_listener("test-queue", acknowledgement_mode=AcknowledgementMode.ON_SUCCESS)
        def my_listener(message: dict):
            raise ValueError("Processing failed")

        # Create container
        converter = JsonMessageConverter()
        ack_processor = MagicMock(spec=AcknowledgementProcessor)
        backpressure = BackpressureManager(BackpressureMode.AUTO)

        container = MessageListenerContainer(
            client=client,
            converter=converter,
            acknowledgement_processor=ack_processor,
            backpressure_manager=backpressure,
        )

        # Create a test message
        from awskit.sqs.models import Message

        message = Message(
            message_id="test-msg-1",
            receipt_handle="test-receipt-1",
            body={"test": "data"},
            attributes={},
            message_attributes={},
            queue_url="https://sqs.us-east-1.amazonaws.com/123456789012/test-queue",
        )

        # Get the listener config
        listener_func, listener_config = container._listeners[
            "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        ][0]

        # Invoke listener (should raise exception)
        from awskit.exceptions import ListenerError

        with pytest.raises(ListenerError):
            container._invoke_listener(listener_func, message, listener_config)

        # Verify message was NOT acknowledged
        ack_processor.acknowledge.assert_not_called()

    def test_acknowledgement_always_mode_acknowledges_on_success(self):
        """Test ALWAYS mode acknowledges message when listener succeeds."""
        # Create mock client
        client = MagicMock()
        client.get_queue_url.return_value = {
            "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        }

        # Register a listener with ALWAYS mode
        @sqs_listener("test-queue", acknowledgement_mode=AcknowledgementMode.ALWAYS)
        def my_listener(message: dict):
            # Listener succeeds
            pass

        # Create container
        converter = JsonMessageConverter()
        ack_processor = MagicMock(spec=AcknowledgementProcessor)
        backpressure = BackpressureManager(BackpressureMode.AUTO)

        container = MessageListenerContainer(
            client=client,
            converter=converter,
            acknowledgement_processor=ack_processor,
            backpressure_manager=backpressure,
        )

        # Create a test message
        from awskit.sqs.models import Message

        message = Message(
            message_id="test-msg-1",
            receipt_handle="test-receipt-1",
            body={"test": "data"},
            attributes={},
            message_attributes={},
            queue_url="https://sqs.us-east-1.amazonaws.com/123456789012/test-queue",
        )

        # Get the listener config
        listener_func, listener_config = container._listeners[
            "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        ][0]

        # Invoke listener
        container._invoke_listener(listener_func, message, listener_config)

        # Verify message was acknowledged
        ack_processor.acknowledge.assert_called_once_with(
            "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue", "test-receipt-1"
        )

    def test_acknowledgement_always_mode_acknowledges_on_failure(self):
        """Test ALWAYS mode acknowledges message even when listener fails."""
        # Create mock client
        client = MagicMock()
        client.get_queue_url.return_value = {
            "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        }

        # Register a listener with ALWAYS mode that fails
        @sqs_listener("test-queue", acknowledgement_mode=AcknowledgementMode.ALWAYS)
        def my_listener(message: dict):
            raise ValueError("Processing failed")

        # Create container
        converter = JsonMessageConverter()
        ack_processor = MagicMock(spec=AcknowledgementProcessor)
        backpressure = BackpressureManager(BackpressureMode.AUTO)

        container = MessageListenerContainer(
            client=client,
            converter=converter,
            acknowledgement_processor=ack_processor,
            backpressure_manager=backpressure,
        )

        # Create a test message
        from awskit.sqs.models import Message

        message = Message(
            message_id="test-msg-1",
            receipt_handle="test-receipt-1",
            body={"test": "data"},
            attributes={},
            message_attributes={},
            queue_url="https://sqs.us-east-1.amazonaws.com/123456789012/test-queue",
        )

        # Get the listener config
        listener_func, listener_config = container._listeners[
            "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        ][0]

        # Invoke listener (should raise exception)
        from awskit.exceptions import ListenerError

        with pytest.raises(ListenerError):
            container._invoke_listener(listener_func, message, listener_config)

        # Verify message WAS acknowledged despite failure
        ack_processor.acknowledge.assert_called_once_with(
            "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue", "test-receipt-1"
        )

    def test_acknowledgement_manual_mode_provides_handle_and_does_not_auto_acknowledge(self):
        """Test MANUAL mode provides Acknowledgement handle and does not auto-acknowledge."""
        # Create mock client
        client = MagicMock()
        client.get_queue_url.return_value = {
            "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        }

        # Track if acknowledgement handle was provided
        ack_handle_received = []

        # Register a listener with MANUAL mode
        @sqs_listener("test-queue", acknowledgement_mode=AcknowledgementMode.MANUAL)
        def my_listener(message: dict, ack):
            # Store the acknowledgement handle
            ack_handle_received.append(ack)
            # Don't call ack.acknowledge() - listener controls acknowledgement

        # Create container
        converter = JsonMessageConverter()
        ack_processor = MagicMock(spec=AcknowledgementProcessor)
        backpressure = BackpressureManager(BackpressureMode.AUTO)

        container = MessageListenerContainer(
            client=client,
            converter=converter,
            acknowledgement_processor=ack_processor,
            backpressure_manager=backpressure,
        )

        # Create a test message
        from awskit.sqs.models import Acknowledgement, Message

        message = Message(
            message_id="test-msg-1",
            receipt_handle="test-receipt-1",
            body={"test": "data"},
            attributes={},
            message_attributes={},
            queue_url="https://sqs.us-east-1.amazonaws.com/123456789012/test-queue",
        )

        # Get the listener config
        listener_func, listener_config = container._listeners[
            "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        ][0]

        # Invoke listener
        container._invoke_listener(listener_func, message, listener_config)

        # Verify acknowledgement handle was provided
        assert len(ack_handle_received) == 1
        assert isinstance(ack_handle_received[0], Acknowledgement)
        assert (
            ack_handle_received[0].queue_url
            == "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        )
        assert ack_handle_received[0].receipt_handle == "test-receipt-1"

        # Verify message was NOT auto-acknowledged
        ack_processor.acknowledge.assert_not_called()

    def test_acknowledgement_manual_mode_listener_can_acknowledge_explicitly(self):
        """Test MANUAL mode allows listener to acknowledge explicitly."""
        # Create mock client
        client = MagicMock()
        client.get_queue_url.return_value = {
            "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        }

        # Register a listener with MANUAL mode that acknowledges explicitly
        @sqs_listener("test-queue", acknowledgement_mode=AcknowledgementMode.MANUAL)
        def my_listener(message: dict, ack):
            # Listener explicitly acknowledges
            ack.acknowledge()

        # Create container
        converter = JsonMessageConverter()
        ack_processor = MagicMock(spec=AcknowledgementProcessor)
        backpressure = BackpressureManager(BackpressureMode.AUTO)

        container = MessageListenerContainer(
            client=client,
            converter=converter,
            acknowledgement_processor=ack_processor,
            backpressure_manager=backpressure,
        )

        # Create a test message
        from awskit.sqs.models import Message

        message = Message(
            message_id="test-msg-1",
            receipt_handle="test-receipt-1",
            body={"test": "data"},
            attributes={},
            message_attributes={},
            queue_url="https://sqs.us-east-1.amazonaws.com/123456789012/test-queue",
        )

        # Get the listener config
        listener_func, listener_config = container._listeners[
            "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        ][0]

        # Invoke listener
        container._invoke_listener(listener_func, message, listener_config)

        # Verify message was acknowledged by the listener
        ack_processor.acknowledge.assert_called_once_with(
            "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue", "test-receipt-1"
        )
