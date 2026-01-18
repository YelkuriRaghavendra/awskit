"""
Tests for automatic container context management.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from awskit.sqs import (
    SqsListenerContext,
    get_listener_context,
    sqs_listener,
    start_listeners,
    stop_listeners,
)
from awskit.config import BackpressureMode, SqsConfig, ContainerConfig
from awskit.sqs.registry import ListenerRegistry


@pytest.fixture(autouse=True)
def clear_registry():
    """Clear the listener registry before each test."""
    ListenerRegistry._listeners.clear()
    SqsListenerContext._instance = None
    yield
    ListenerRegistry._listeners.clear()
    SqsListenerContext._instance = None


@pytest.fixture
def mock_client():
    """Create a mock SQS client."""
    client = MagicMock()
    client.get_queue_url.return_value = {
        "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"
    }
    client.receive_message.return_value = {"Messages": []}
    return client


def test_context_initialization(mock_client):
    """Test that SqsListenerContext initializes correctly."""
    context = SqsListenerContext(client=mock_client)

    assert context.client == mock_client
    assert context.converter is not None
    assert context.acknowledgement_processor is not None
    assert context.backpressure_manager is not None
    assert context._container is not None


def test_context_with_custom_config(mock_client):
    """Test context initialization with custom configuration."""
    config = SqsConfig(
        container=ContainerConfig(backpressure_mode=BackpressureMode.ALWAYS_POLL_MAX)
    )

    context = SqsListenerContext(client=mock_client, config=config)

    assert context.config == config
    assert context.backpressure_manager.mode == BackpressureMode.ALWAYS_POLL_MAX


def test_start_listeners_function(mock_client):
    """Test the start_listeners convenience function."""

    # Define a listener
    @sqs_listener("test-queue")
    def test_listener(message: dict):
        pass

    # Start listeners
    context = start_listeners(mock_client, auto_start=False)

    assert context is not None
    assert isinstance(context, SqsListenerContext)
    assert SqsListenerContext.get_instance() == context
    assert not context.is_running()


def test_start_listeners_auto_start(mock_client):
    """Test that start_listeners auto-starts by default."""

    @sqs_listener("test-queue")
    def test_listener(message: dict):
        pass

    with patch.object(SqsListenerContext, "start") as mock_start:
        context = start_listeners(mock_client, auto_start=True)
        mock_start.assert_called_once()


def test_stop_listeners_function(mock_client):
    """Test the stop_listeners convenience function."""

    @sqs_listener("test-queue")
    def test_listener(message: dict):
        pass

    context = start_listeners(mock_client, auto_start=False)

    with patch.object(context, "stop") as mock_stop:
        stop_listeners(timeout_seconds=10)
        mock_stop.assert_called_once_with(timeout_seconds=10)


def test_get_listener_context(mock_client):
    """Test the get_listener_context function."""
    assert get_listener_context() is None

    context = start_listeners(mock_client, auto_start=False)

    assert get_listener_context() == context


def test_context_singleton(mock_client):
    """Test that context maintains singleton pattern."""
    context1 = start_listeners(mock_client, auto_start=False)

    # Get the instance
    context2 = SqsListenerContext.get_instance()

    assert context1 is context2


def test_context_start_and_stop(mock_client):
    """Test starting and stopping the context."""

    @sqs_listener("test-queue")
    def test_listener(message: dict):
        pass

    context = SqsListenerContext(client=mock_client)

    # Start
    context.start()
    assert context.is_running()

    # Stop
    context.stop()
    # After stop, executor should be None
    assert context._container._executor is None


def test_context_is_running(mock_client):
    """Test the is_running method."""
    context = SqsListenerContext(client=mock_client)

    assert not context.is_running()

    context.start()
    assert context.is_running()

    context.stop()
    assert not context.is_running()


def test_multiple_listeners_with_context(mock_client):
    """Test that context works with multiple listeners."""

    @sqs_listener("queue1")
    def listener1(message: dict):
        pass

    @sqs_listener("queue2")
    def listener2(message: dict):
        pass

    # Mock different queue URLs
    def get_queue_url_side_effect(QueueName):
        return {"QueueUrl": f"https://sqs.us-east-1.amazonaws.com/123456789/{QueueName}"}

    mock_client.get_queue_url.side_effect = get_queue_url_side_effect

    context = start_listeners(mock_client, auto_start=False)

    # Both listeners should be registered
    assert len(ListenerRegistry.get_listeners()) == 2


def test_context_with_custom_converter(mock_client):
    """Test context with custom message converter."""
    from awskit.converter import JsonMessageConverter

    custom_converter = JsonMessageConverter()
    context = SqsListenerContext(client=mock_client, converter=custom_converter)

    assert context.converter is custom_converter


def test_stop_listeners_without_context():
    """Test that stop_listeners handles missing context gracefully."""
    # Should not raise an exception
    stop_listeners()


def test_context_atexit_registration(mock_client):
    """Test that context registers atexit handler."""
    import atexit

    with patch.object(atexit, "register") as mock_register:
        context = SqsListenerContext(client=mock_client)
        mock_register.assert_called_once()


def test_start_listeners_with_metrics_collector(mock_client):
    """Test start_listeners with custom metrics collector."""
    from awskit.metrics import InMemoryMetricsCollector

    metrics = InMemoryMetricsCollector()
    context = start_listeners(mock_client, metrics_collector=metrics, auto_start=False)

    assert context.metrics_collector is metrics
