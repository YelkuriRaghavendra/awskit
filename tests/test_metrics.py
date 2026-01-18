"""
Tests for metrics collection functionality.
"""

from unittest.mock import MagicMock, patch

import pytest

from awskit.metrics import (
    CallbackMetricsCollector,
    InMemoryMetricsCollector,
    LifecycleEvent,
    NoOpMetricsCollector,
)


class TestInMemoryMetricsCollector:
    """Tests for InMemoryMetricsCollector."""

    def test_increment_received(self):
        """Test incrementing received messages count."""
        collector = InMemoryMetricsCollector()
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"

        collector.increment_received(queue_url, 5)

        metrics = collector.get_metrics(queue_url)
        assert queue_url in metrics
        assert metrics[queue_url].received == 5
        assert metrics[queue_url].processed == 0
        assert metrics[queue_url].failed == 0
        assert metrics[queue_url].acknowledged == 0

    def test_increment_processed(self):
        """Test incrementing processed messages count."""
        collector = InMemoryMetricsCollector()
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"

        collector.increment_processed(queue_url, 3)

        metrics = collector.get_metrics(queue_url)
        assert metrics[queue_url].processed == 3

    def test_increment_failed(self):
        """Test incrementing failed messages count."""
        collector = InMemoryMetricsCollector()
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"

        collector.increment_failed(queue_url, 2)

        metrics = collector.get_metrics(queue_url)
        assert metrics[queue_url].failed == 2

    def test_increment_acknowledged(self):
        """Test incrementing acknowledged messages count."""
        collector = InMemoryMetricsCollector()
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"

        collector.increment_acknowledged(queue_url, 4)

        metrics = collector.get_metrics(queue_url)
        assert metrics[queue_url].acknowledged == 4

    def test_multiple_increments(self):
        """Test multiple increments accumulate correctly."""
        collector = InMemoryMetricsCollector()
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"

        collector.increment_received(queue_url, 10)
        collector.increment_received(queue_url, 5)
        collector.increment_processed(queue_url, 8)
        collector.increment_failed(queue_url, 2)
        collector.increment_acknowledged(queue_url, 8)

        metrics = collector.get_metrics(queue_url)
        assert metrics[queue_url].received == 15
        assert metrics[queue_url].processed == 8
        assert metrics[queue_url].failed == 2
        assert metrics[queue_url].acknowledged == 8

    def test_multiple_queues(self):
        """Test metrics are tracked separately per queue."""
        collector = InMemoryMetricsCollector()
        queue1 = "https://sqs.us-east-1.amazonaws.com/123456789/queue1"
        queue2 = "https://sqs.us-east-1.amazonaws.com/123456789/queue2"

        collector.increment_received(queue1, 10)
        collector.increment_received(queue2, 5)

        metrics = collector.get_metrics()
        assert len(metrics) == 2
        assert metrics[queue1].received == 10
        assert metrics[queue2].received == 5

    def test_get_metrics_for_specific_queue(self):
        """Test getting metrics for a specific queue."""
        collector = InMemoryMetricsCollector()
        queue1 = "https://sqs.us-east-1.amazonaws.com/123456789/queue1"
        queue2 = "https://sqs.us-east-1.amazonaws.com/123456789/queue2"

        collector.increment_received(queue1, 10)
        collector.increment_received(queue2, 5)

        metrics = collector.get_metrics(queue1)
        assert len(metrics) == 1
        assert queue1 in metrics
        assert queue2 not in metrics

    def test_get_metrics_for_nonexistent_queue(self):
        """Test getting metrics for a queue that hasn't been tracked."""
        collector = InMemoryMetricsCollector()
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"

        metrics = collector.get_metrics(queue_url)
        assert len(metrics) == 1
        assert metrics[queue_url].received == 0
        assert metrics[queue_url].processed == 0
        assert metrics[queue_url].failed == 0
        assert metrics[queue_url].acknowledged == 0

    def test_reset_specific_queue(self):
        """Test resetting metrics for a specific queue."""
        collector = InMemoryMetricsCollector()
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"

        collector.increment_received(queue_url, 10)
        collector.reset(queue_url)

        metrics = collector.get_metrics(queue_url)
        assert metrics[queue_url].received == 0

    def test_reset_all_queues(self):
        """Test resetting metrics for all queues."""
        collector = InMemoryMetricsCollector()
        queue1 = "https://sqs.us-east-1.amazonaws.com/123456789/queue1"
        queue2 = "https://sqs.us-east-1.amazonaws.com/123456789/queue2"

        collector.increment_received(queue1, 10)
        collector.increment_received(queue2, 5)
        collector.reset()

        metrics = collector.get_metrics()
        assert len(metrics) == 0


class TestNoOpMetricsCollector:
    """Tests for NoOpMetricsCollector."""

    def test_no_op_collector_does_nothing(self):
        """Test that NoOpMetricsCollector doesn't track anything."""
        collector = NoOpMetricsCollector()
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"

        collector.increment_received(queue_url, 10)
        collector.increment_processed(queue_url, 5)
        collector.increment_failed(queue_url, 2)
        collector.increment_acknowledged(queue_url, 5)

        metrics = collector.get_metrics()
        assert len(metrics) == 0


class TestCallbackMetricsCollector:
    """Tests for CallbackMetricsCollector."""

    def test_register_and_invoke_callback(self):
        """Test registering and invoking a callback."""
        base_collector = InMemoryMetricsCollector()
        collector = CallbackMetricsCollector(base_collector)

        callback_invoked = []

        def callback(event, queue_url, context):
            callback_invoked.append((event, queue_url, context))

        collector.register_callback(LifecycleEvent.MESSAGE_RECEIVED, callback)

        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"
        collector.increment_received(queue_url, 5)

        # Check callback was invoked
        assert len(callback_invoked) == 1
        assert callback_invoked[0][0] == LifecycleEvent.MESSAGE_RECEIVED
        assert callback_invoked[0][1] == queue_url
        assert callback_invoked[0][2] == {"count": 5}

        # Check base collector was updated
        metrics = collector.get_metrics(queue_url)
        assert metrics[queue_url].received == 5

    def test_multiple_callbacks_for_same_event(self):
        """Test multiple callbacks can be registered for the same event."""
        base_collector = InMemoryMetricsCollector()
        collector = CallbackMetricsCollector(base_collector)

        callback1_invoked = []
        callback2_invoked = []

        def callback1(event, queue_url, context):
            callback1_invoked.append(True)

        def callback2(event, queue_url, context):
            callback2_invoked.append(True)

        collector.register_callback(LifecycleEvent.MESSAGE_PROCESSED, callback1)
        collector.register_callback(LifecycleEvent.MESSAGE_PROCESSED, callback2)

        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"
        collector.increment_processed(queue_url, 1)

        assert len(callback1_invoked) == 1
        assert len(callback2_invoked) == 1

    def test_callbacks_for_different_events(self):
        """Test callbacks are invoked only for their registered events."""
        base_collector = InMemoryMetricsCollector()
        collector = CallbackMetricsCollector(base_collector)

        received_invoked = []
        processed_invoked = []

        def received_callback(event, queue_url, context):
            received_invoked.append(True)

        def processed_callback(event, queue_url, context):
            processed_invoked.append(True)

        collector.register_callback(LifecycleEvent.MESSAGE_RECEIVED, received_callback)
        collector.register_callback(LifecycleEvent.MESSAGE_PROCESSED, processed_callback)

        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"
        collector.increment_received(queue_url, 1)

        assert len(received_invoked) == 1
        assert len(processed_invoked) == 0

    def test_unregister_callback(self):
        """Test unregistering a callback."""
        base_collector = InMemoryMetricsCollector()
        collector = CallbackMetricsCollector(base_collector)

        callback_invoked = []

        def callback(event, queue_url, context):
            callback_invoked.append(True)

        collector.register_callback(LifecycleEvent.MESSAGE_FAILED, callback)
        collector.unregister_callback(LifecycleEvent.MESSAGE_FAILED, callback)

        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"
        collector.increment_failed(queue_url, 1)

        assert len(callback_invoked) == 0

    def test_callback_exception_is_logged_but_not_raised(self):
        """Test that exceptions in callbacks are logged but don't break processing."""
        base_collector = InMemoryMetricsCollector()
        collector = CallbackMetricsCollector(base_collector)

        def bad_callback(event, queue_url, context):
            raise ValueError("Callback error")

        collector.register_callback(LifecycleEvent.MESSAGE_ACKNOWLEDGED, bad_callback)

        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"

        # Should not raise exception
        collector.increment_acknowledged(queue_url, 1)

        # Base collector should still be updated
        metrics = collector.get_metrics(queue_url)
        assert metrics[queue_url].acknowledged == 1

    def test_all_lifecycle_events(self):
        """Test callbacks work for all lifecycle events."""
        base_collector = InMemoryMetricsCollector()
        collector = CallbackMetricsCollector(base_collector)

        events_received = []

        def callback(event, queue_url, context):
            events_received.append(event)

        # Register callback for all events
        for event in LifecycleEvent:
            collector.register_callback(event, callback)

        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"

        collector.increment_received(queue_url, 1)
        collector.increment_processed(queue_url, 1)
        collector.increment_failed(queue_url, 1)
        collector.increment_acknowledged(queue_url, 1)

        assert len(events_received) == 4
        assert LifecycleEvent.MESSAGE_RECEIVED in events_received
        assert LifecycleEvent.MESSAGE_PROCESSED in events_received
        assert LifecycleEvent.MESSAGE_FAILED in events_received
        assert LifecycleEvent.MESSAGE_ACKNOWLEDGED in events_received


class TestPrometheusMetricsCollector:
    """Tests for PrometheusMetricsCollector."""

    def test_import_error_when_prometheus_client_not_installed(self):
        """Test that ImportError is raised when prometheus_client is not available."""
        with patch.dict("sys.modules", {"prometheus_client": None}):
            with pytest.raises(ImportError) as exc_info:
                from awskit.metrics import PrometheusMetricsCollector

                PrometheusMetricsCollector()

            assert "prometheus_client is required" in str(exc_info.value)

    def test_initialization_with_default_namespace(self):
        """Test PrometheusMetricsCollector initializes with default namespace."""
        pytest.importorskip("prometheus_client")
        from prometheus_client import CollectorRegistry

        from awskit.metrics import PrometheusMetricsCollector

        registry = CollectorRegistry()
        PrometheusMetricsCollector(registry=registry)

        # Verify metrics are created
        metric_names = [metric.name for metric in registry.collect()]
        assert "sqs_integration_messages_received" in metric_names
        assert "sqs_integration_messages_processed" in metric_names
        assert "sqs_integration_messages_failed" in metric_names
        assert "sqs_integration_messages_acknowledged" in metric_names

    def test_initialization_with_custom_namespace(self):
        """Test PrometheusMetricsCollector initializes with custom namespace."""
        pytest.importorskip("prometheus_client")
        from prometheus_client import CollectorRegistry

        from awskit.metrics import PrometheusMetricsCollector

        registry = CollectorRegistry()
        PrometheusMetricsCollector(namespace="my_app", registry=registry)

        # Verify metrics are created with custom namespace
        metric_names = [metric.name for metric in registry.collect()]
        assert "my_app_messages_received" in metric_names
        assert "my_app_messages_processed" in metric_names
        assert "my_app_messages_failed" in metric_names
        assert "my_app_messages_acknowledged" in metric_names

    def test_increment_received(self):
        """Test incrementing received messages count."""
        pytest.importorskip("prometheus_client")
        from prometheus_client import CollectorRegistry

        from awskit.metrics import PrometheusMetricsCollector

        registry = CollectorRegistry()
        collector = PrometheusMetricsCollector(registry=registry)

        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"
        collector.increment_received(queue_url, 5)

        # Verify counter was incremented
        for metric in registry.collect():
            if metric.name == "sqs_integration_messages_received":
                for sample in metric.samples:
                    # Check the _total sample, not _created
                    if (
                        sample.name.endswith("_total")
                        and sample.labels.get("queue_name") == "test-queue"
                    ):
                        assert sample.value == 5.0

    def test_increment_processed(self):
        """Test incrementing processed messages count."""
        pytest.importorskip("prometheus_client")
        from prometheus_client import CollectorRegistry

        from awskit.metrics import PrometheusMetricsCollector

        registry = CollectorRegistry()
        collector = PrometheusMetricsCollector(registry=registry)

        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"
        collector.increment_processed(queue_url, 3)

        # Verify counter was incremented
        for metric in registry.collect():
            if metric.name == "sqs_integration_messages_processed":
                for sample in metric.samples:
                    if (
                        sample.name.endswith("_total")
                        and sample.labels.get("queue_name") == "test-queue"
                    ):
                        assert sample.value == 3.0

    def test_increment_failed(self):
        """Test incrementing failed messages count."""
        pytest.importorskip("prometheus_client")
        from prometheus_client import CollectorRegistry

        from awskit.metrics import PrometheusMetricsCollector

        registry = CollectorRegistry()
        collector = PrometheusMetricsCollector(registry=registry)

        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"
        collector.increment_failed(queue_url, 2)

        # Verify counter was incremented
        for metric in registry.collect():
            if metric.name == "sqs_integration_messages_failed":
                for sample in metric.samples:
                    if (
                        sample.name.endswith("_total")
                        and sample.labels.get("queue_name") == "test-queue"
                    ):
                        assert sample.value == 2.0

    def test_increment_acknowledged(self):
        """Test incrementing acknowledged messages count."""
        pytest.importorskip("prometheus_client")
        from prometheus_client import CollectorRegistry

        from awskit.metrics import PrometheusMetricsCollector

        registry = CollectorRegistry()
        collector = PrometheusMetricsCollector(registry=registry)

        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"
        collector.increment_acknowledged(queue_url, 4)

        # Verify counter was incremented
        for metric in registry.collect():
            if metric.name == "sqs_integration_messages_acknowledged":
                for sample in metric.samples:
                    if (
                        sample.name.endswith("_total")
                        and sample.labels.get("queue_name") == "test-queue"
                    ):
                        assert sample.value == 4.0

    def test_multiple_increments_accumulate(self):
        """Test multiple increments accumulate correctly."""
        pytest.importorskip("prometheus_client")
        from prometheus_client import CollectorRegistry

        from awskit.metrics import PrometheusMetricsCollector

        registry = CollectorRegistry()
        collector = PrometheusMetricsCollector(registry=registry)

        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"
        collector.increment_received(queue_url, 10)
        collector.increment_received(queue_url, 5)

        # Verify counter accumulated
        for metric in registry.collect():
            if metric.name == "sqs_integration_messages_received":
                for sample in metric.samples:
                    if (
                        sample.name.endswith("_total")
                        and sample.labels.get("queue_name") == "test-queue"
                    ):
                        assert sample.value == 15.0

    def test_multiple_queues_tracked_separately(self):
        """Test metrics are tracked separately per queue."""
        pytest.importorskip("prometheus_client")
        from prometheus_client import CollectorRegistry

        from awskit.metrics import PrometheusMetricsCollector

        registry = CollectorRegistry()
        collector = PrometheusMetricsCollector(registry=registry)

        queue1 = "https://sqs.us-east-1.amazonaws.com/123456789/queue1"
        queue2 = "https://sqs.us-east-1.amazonaws.com/123456789/queue2"

        collector.increment_received(queue1, 10)
        collector.increment_received(queue2, 5)

        # Verify both queues are tracked
        queue_values = {}
        for metric in registry.collect():
            if metric.name == "sqs_integration_messages_received":
                for sample in metric.samples:
                    if sample.name.endswith("_total"):
                        queue_name = sample.labels.get("queue_name")
                        if queue_name:
                            queue_values[queue_name] = sample.value

        assert queue_values.get("queue1") == 10.0
        assert queue_values.get("queue2") == 5.0

    def test_extract_queue_name_from_url(self):
        """Test queue name extraction from URL."""
        pytest.importorskip("prometheus_client")
        from prometheus_client import CollectorRegistry

        from awskit.metrics import PrometheusMetricsCollector

        registry = CollectorRegistry()
        collector = PrometheusMetricsCollector(registry=registry)

        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/my-test-queue.fifo"
        collector.increment_received(queue_url, 1)

        # Verify queue name is extracted correctly
        for metric in registry.collect():
            if metric.name == "sqs_integration_messages_received":
                for sample in metric.samples:
                    if sample.value == 1.0:
                        assert sample.labels.get("queue_name") == "my-test-queue.fifo"

    def test_get_metrics_returns_empty_with_warning(self):
        """Test get_metrics returns empty dict and logs warning."""
        pytest.importorskip("prometheus_client")
        from prometheus_client import CollectorRegistry

        from awskit.metrics import PrometheusMetricsCollector

        registry = CollectorRegistry()
        collector = PrometheusMetricsCollector(registry=registry)

        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"
        collector.increment_received(queue_url, 5)

        # get_metrics is not recommended for Prometheus
        metrics = collector.get_metrics(queue_url)
        assert metrics == {}


class TestStatsDMetricsCollector:
    """Tests for StatsDMetricsCollector."""

    def test_import_error_when_statsd_not_installed(self):
        """Test that ImportError is raised when statsd is not available."""
        with patch.dict("sys.modules", {"statsd": None}):
            with pytest.raises(ImportError) as exc_info:
                from awskit.metrics import StatsDMetricsCollector

                StatsDMetricsCollector()

            assert "statsd is required" in str(exc_info.value)

    def test_initialization_with_defaults(self):
        """Test StatsDMetricsCollector initializes with default settings."""
        pytest.importorskip("statsd")
        from awskit.metrics import StatsDMetricsCollector

        with patch("statsd.StatsClient") as mock_client:
            StatsDMetricsCollector()

            mock_client.assert_called_once_with(
                host="localhost", port=8125, prefix="sqs_integration", maxudpsize=512
            )

    def test_initialization_with_custom_settings(self):
        """Test StatsDMetricsCollector initializes with custom settings."""
        pytest.importorskip("statsd")
        from awskit.metrics import StatsDMetricsCollector

        with patch("statsd.StatsClient") as mock_client:
            StatsDMetricsCollector(
                host="statsd.example.com", port=9125, prefix="my_app", maxudpsize=1024
            )

            mock_client.assert_called_once_with(
                host="statsd.example.com", port=9125, prefix="my_app", maxudpsize=1024
            )

    def test_increment_received(self):
        """Test incrementing received messages count."""
        pytest.importorskip("statsd")
        from awskit.metrics import StatsDMetricsCollector

        with patch("statsd.StatsClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            collector = StatsDMetricsCollector()
            queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"
            collector.increment_received(queue_url, 5)

            mock_client.incr.assert_called_once_with("messages_received.test_queue", 5)

    def test_increment_processed(self):
        """Test incrementing processed messages count."""
        pytest.importorskip("statsd")
        from awskit.metrics import StatsDMetricsCollector

        with patch("statsd.StatsClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            collector = StatsDMetricsCollector()
            queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"
            collector.increment_processed(queue_url, 3)

            mock_client.incr.assert_called_once_with("messages_processed.test_queue", 3)

    def test_increment_failed(self):
        """Test incrementing failed messages count."""
        pytest.importorskip("statsd")
        from awskit.metrics import StatsDMetricsCollector

        with patch("statsd.StatsClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            collector = StatsDMetricsCollector()
            queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"
            collector.increment_failed(queue_url, 2)

            mock_client.incr.assert_called_once_with("messages_failed.test_queue", 2)

    def test_increment_acknowledged(self):
        """Test incrementing acknowledged messages count."""
        pytest.importorskip("statsd")
        from awskit.metrics import StatsDMetricsCollector

        with patch("statsd.StatsClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            collector = StatsDMetricsCollector()
            queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"
            collector.increment_acknowledged(queue_url, 4)

            mock_client.incr.assert_called_once_with("messages_acknowledged.test_queue", 4)

    def test_queue_name_sanitization(self):
        """Test queue name is sanitized for StatsD."""
        pytest.importorskip("statsd")
        from awskit.metrics import StatsDMetricsCollector

        with patch("statsd.StatsClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            collector = StatsDMetricsCollector()
            queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/my-test.queue.fifo"
            collector.increment_received(queue_url, 1)

            # Dots and dashes should be replaced with underscores
            mock_client.incr.assert_called_once_with("messages_received.my_test_queue_fifo", 1)

    def test_get_metrics_returns_empty_with_warning(self):
        """Test get_metrics returns empty dict and logs warning."""
        pytest.importorskip("statsd")
        from awskit.metrics import StatsDMetricsCollector

        with patch("statsd.StatsClient"):
            collector = StatsDMetricsCollector()

            queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"

            # get_metrics is not supported for StatsD
            metrics = collector.get_metrics(queue_url)
            assert metrics == {}
