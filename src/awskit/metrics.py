"""
Metrics collection for the SQS integration library.

This module provides abstract and concrete implementations for collecting
metrics about message processing lifecycle events.
"""

import structlog
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Any, Callable, Dict, List, Optional

logger = structlog.get_logger(__name__)


class LifecycleEvent(Enum):
    """
    Message lifecycle events for monitoring callbacks.
    
    Attributes:
        MESSAGE_RECEIVED: Message was received from SQS
        MESSAGE_PROCESSED: Message was successfully processed
        MESSAGE_FAILED: Message processing failed
        MESSAGE_ACKNOWLEDGED: Message was acknowledged (deleted)
    """
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_PROCESSED = "message_processed"
    MESSAGE_FAILED = "message_failed"
    MESSAGE_ACKNOWLEDGED = "message_acknowledged"


# Type alias for monitoring callbacks
# Callback signature: (event: LifecycleEvent, queue_url: str, context: Dict[str, Any]) -> None
MonitoringCallback = Callable[[LifecycleEvent, str, Dict[str, Any]], None]


@dataclass
class MetricCounts:
    """
    Container for metric counters.
    
    Attributes:
        received: Number of messages received from SQS
        processed: Number of messages successfully processed
        failed: Number of messages that failed processing
        acknowledged: Number of messages acknowledged (deleted)
    """
    received: int = 0
    processed: int = 0
    failed: int = 0
    acknowledged: int = 0


class MetricsCollector(ABC):
    """
    Abstract base class for metrics collectors.
    
    Implementations should provide concrete mechanisms for recording
    and exposing metrics (e.g., Prometheus, StatsD, CloudWatch).
    """

    @abstractmethod
    def increment_received(self, queue_url: str, count: int = 1) -> None:
        """
        Increment the count of messages received.
        
        Args:
            queue_url: The queue URL
            count: Number of messages received (default: 1)
        """
        pass

    @abstractmethod
    def increment_processed(self, queue_url: str, count: int = 1) -> None:
        """
        Increment the count of messages successfully processed.
        
        Args:
            queue_url: The queue URL
            count: Number of messages processed (default: 1)
        """
        pass

    @abstractmethod
    def increment_failed(self, queue_url: str, count: int = 1) -> None:
        """
        Increment the count of messages that failed processing.
        
        Args:
            queue_url: The queue URL
            count: Number of messages failed (default: 1)
        """
        pass

    @abstractmethod
    def increment_acknowledged(self, queue_url: str, count: int = 1) -> None:
        """
        Increment the count of messages acknowledged (deleted).
        
        Args:
            queue_url: The queue URL
            count: Number of messages acknowledged (default: 1)
        """
        pass

    @abstractmethod
    def get_metrics(self, queue_url: Optional[str] = None) -> Dict[str, MetricCounts]:
        """
        Get current metric counts.
        
        Args:
            queue_url: Optional queue URL to filter by. If None, returns all queues.
        
        Returns:
            Dictionary mapping queue URLs to their metric counts
        """
        pass


class InMemoryMetricsCollector(MetricsCollector):
    """
    Simple in-memory metrics collector for testing and development.
    
    This collector stores metrics in memory and provides thread-safe
    access to metric counts. It's suitable for testing and single-instance
    deployments but doesn't persist metrics or aggregate across instances.
    """

    def __init__(self) -> None:
        """Initialize the in-memory metrics collector."""
        self._metrics: Dict[str, MetricCounts] = {}
        self._lock = Lock()

    def increment_received(self, queue_url: str, count: int = 1) -> None:
        """Increment the count of messages received."""
        with self._lock:
            if queue_url not in self._metrics:
                self._metrics[queue_url] = MetricCounts()
            self._metrics[queue_url].received += count

    def increment_processed(self, queue_url: str, count: int = 1) -> None:
        """Increment the count of messages successfully processed."""
        with self._lock:
            if queue_url not in self._metrics:
                self._metrics[queue_url] = MetricCounts()
            self._metrics[queue_url].processed += count

    def increment_failed(self, queue_url: str, count: int = 1) -> None:
        """Increment the count of messages that failed processing."""
        with self._lock:
            if queue_url not in self._metrics:
                self._metrics[queue_url] = MetricCounts()
            self._metrics[queue_url].failed += count

    def increment_acknowledged(self, queue_url: str, count: int = 1) -> None:
        """Increment the count of messages acknowledged (deleted)."""
        with self._lock:
            if queue_url not in self._metrics:
                self._metrics[queue_url] = MetricCounts()
            self._metrics[queue_url].acknowledged += count

    def get_metrics(self, queue_url: Optional[str] = None) -> Dict[str, MetricCounts]:
        """Get current metric counts."""
        with self._lock:
            if queue_url is not None:
                if queue_url in self._metrics:
                    return {queue_url: self._metrics[queue_url]}
                else:
                    return {queue_url: MetricCounts()}
            else:
                # Return a copy to avoid external modification
                return dict(self._metrics)

    def reset(self, queue_url: Optional[str] = None) -> None:
        """
        Reset metrics to zero.
        
        Args:
            queue_url: Optional queue URL to reset. If None, resets all queues.
        """
        with self._lock:
            if queue_url is not None:
                if queue_url in self._metrics:
                    self._metrics[queue_url] = MetricCounts()
            else:
                self._metrics.clear()


class NoOpMetricsCollector(MetricsCollector):
    """
    No-op metrics collector that does nothing.
    
    This collector can be used when metrics collection is disabled
    or not needed, avoiding the overhead of metric tracking.
    """

    def increment_received(self, queue_url: str, count: int = 1) -> None:
        """No-op implementation."""
        pass

    def increment_processed(self, queue_url: str, count: int = 1) -> None:
        """No-op implementation."""
        pass

    def increment_failed(self, queue_url: str, count: int = 1) -> None:
        """No-op implementation."""
        pass

    def increment_acknowledged(self, queue_url: str, count: int = 1) -> None:
        """No-op implementation."""
        pass

    def get_metrics(self, queue_url: Optional[str] = None) -> Dict[str, MetricCounts]:
        """Return empty metrics."""
        return {}



class PrometheusMetricsCollector(MetricsCollector):
    """
    Prometheus metrics collector using prometheus_client library.
    
    This collector exposes metrics in Prometheus format using Counter metrics.
    Metrics are labeled by queue name for easy filtering and aggregation.
    
    Requires the prometheus_client library to be installed:
        pip install prometheus-client
    
    """

    def __init__(self, namespace: str = "sqs_integration", registry: Any = None) -> None:
        """
        Initialize the Prometheus metrics collector.
        
        Args:
            namespace: Prometheus namespace for metrics (default: "sqs_integration")
            registry: Optional Prometheus registry (uses default if None)
        
        Raises:
            ImportError: If prometheus_client is not installed
        """
        try:
            from prometheus_client import REGISTRY, CollectorRegistry, Counter
        except ImportError:
            raise ImportError(
                "prometheus_client is required for PrometheusMetricsCollector. "
                "Install it with: pip install prometheus-client"
            )

        self._registry = registry or REGISTRY

        # Create Counter metrics with queue_name label
        self._received_counter = Counter(
            f"{namespace}_messages_received_total",
            "Total number of messages received from SQS",
            ["queue_name"],
            registry=self._registry
        )

        self._processed_counter = Counter(
            f"{namespace}_messages_processed_total",
            "Total number of messages successfully processed",
            ["queue_name"],
            registry=self._registry
        )

        self._failed_counter = Counter(
            f"{namespace}_messages_failed_total",
            "Total number of messages that failed processing",
            ["queue_name"],
            registry=self._registry
        )

        self._acknowledged_counter = Counter(
            f"{namespace}_messages_acknowledged_total",
            "Total number of messages acknowledged (deleted)",
            ["queue_name"],
            registry=self._registry
        )

    def _extract_queue_name(self, queue_url: str) -> str:
        """
        Extract queue name from queue URL for use as label.
        
        Args:
            queue_url: The queue URL
        
        Returns:
            Queue name (last part of URL)
        """
        return queue_url.split("/")[-1]

    def increment_received(self, queue_url: str, count: int = 1) -> None:
        """Increment the count of messages received."""
        queue_name = self._extract_queue_name(queue_url)
        self._received_counter.labels(queue_name=queue_name).inc(count)

    def increment_processed(self, queue_url: str, count: int = 1) -> None:
        """Increment the count of messages successfully processed."""
        queue_name = self._extract_queue_name(queue_url)
        self._processed_counter.labels(queue_name=queue_name).inc(count)

    def increment_failed(self, queue_url: str, count: int = 1) -> None:
        """Increment the count of messages that failed processing."""
        queue_name = self._extract_queue_name(queue_url)
        self._failed_counter.labels(queue_name=queue_name).inc(count)

    def increment_acknowledged(self, queue_url: str, count: int = 1) -> None:
        """Increment the count of messages acknowledged (deleted)."""
        queue_name = self._extract_queue_name(queue_url)
        self._acknowledged_counter.labels(queue_name=queue_name).inc(count)

    def get_metrics(self, queue_url: Optional[str] = None) -> Dict[str, MetricCounts]:
        """
        Get current metric counts.
        
        Note: This method queries the Prometheus registry to get current values.
        For Prometheus, it's generally better to query metrics directly from
        the Prometheus server rather than through this method.
        
        Args:
            queue_url: Optional queue URL to filter by
        
        Returns:
            Dictionary mapping queue URLs to their metric counts
        """
        try:
            from prometheus_client import REGISTRY
        except ImportError:
            return {}
        metrics: Dict[str, MetricCounts] = {}
        logger.warning(
            "get_metrics() on PrometheusMetricsCollector is not recommended. "
            "Query metrics directly from Prometheus instead."
        )
        return metrics



class StatsDMetricsCollector(MetricsCollector):
    """
    StatsD metrics collector using statsd library.
    
    This collector sends metrics to a StatsD server using UDP.
    Metrics are sent as counters with queue name as a tag.
    
    Requires the statsd library to be installed:
        pip install statsd
    
    Example:
        >>> collector = StatsDMetricsCollector(host='localhost', port=8125)
        >>> # Metrics will be sent to StatsD server at localhost:8125
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8125,
        prefix: str = "sqs_integration",
        maxudpsize: int = 512
    ):
        """
        Initialize the StatsD metrics collector.
        
        Args:
            host: StatsD server hostname (default: "localhost")
            port: StatsD server port (default: 8125)
            prefix: Metric name prefix (default: "sqs_integration")
            maxudpsize: Maximum UDP packet size (default: 512)
        
        Raises:
            ImportError: If statsd library is not installed
        """
        try:
            from statsd import StatsClient
        except ImportError:
            raise ImportError(
                "statsd is required for StatsDMetricsCollector. "
                "Install it with: pip install statsd"
            )

        self._client = StatsClient(
            host=host,
            port=port,
            prefix=prefix,
            maxudpsize=maxudpsize
        )

    def _extract_queue_name(self, queue_url: str) -> str:
        """
        Extract queue name from queue URL for use in metric name.
        
        Args:
            queue_url: The queue URL
        
        Returns:
            Queue name (last part of URL), sanitized for StatsD
        """
        queue_name = queue_url.split("/")[-1]
        # Replace dots and other special characters with underscores
        return queue_name.replace(".", "_").replace("-", "_")

    def increment_received(self, queue_url: str, count: int = 1) -> None:
        """Increment the count of messages received."""
        queue_name = self._extract_queue_name(queue_url)
        metric_name = f"messages_received.{queue_name}"
        self._client.incr(metric_name, count)

    def increment_processed(self, queue_url: str, count: int = 1) -> None:
        """Increment the count of messages successfully processed."""
        queue_name = self._extract_queue_name(queue_url)
        metric_name = f"messages_processed.{queue_name}"
        self._client.incr(metric_name, count)

    def increment_failed(self, queue_url: str, count: int = 1) -> None:
        """Increment the count of messages that failed processing."""
        queue_name = self._extract_queue_name(queue_url)
        metric_name = f"messages_failed.{queue_name}"
        self._client.incr(metric_name, count)

    def increment_acknowledged(self, queue_url: str, count: int = 1) -> None:
        """Increment the count of messages acknowledged (deleted)."""
        queue_name = self._extract_queue_name(queue_url)
        metric_name = f"messages_acknowledged.{queue_name}"
        self._client.incr(metric_name, count)

    def get_metrics(self, queue_url: Optional[str] = None) -> Dict[str, MetricCounts]:
        """
        Get current metric counts.
        
        Note: StatsD is a fire-and-forget protocol and doesn't support
        querying current values. This method returns an empty dict.
        Query your StatsD backend (Graphite, etc.) for metric values.
        
        Args:
            queue_url: Optional queue URL (ignored)
        
        Returns:
            Empty dictionary (StatsD doesn't support querying)
        """
        logger.warning(
            "get_metrics() is not supported for StatsDMetricsCollector. "
            "Query your StatsD backend directly for metric values."
        )
        return {}



class CallbackMetricsCollector(MetricsCollector):
    """
    Metrics collector that invokes monitoring callbacks on lifecycle events.
    
    This collector wraps another MetricsCollector and adds support for
    registering callbacks that are invoked when metrics are updated.
    This allows custom monitoring integrations without implementing
    a full MetricsCollector.
    
    """

    def __init__(self, base_collector: MetricsCollector):
        """
        Initialize the callback metrics collector.
        
        Args:
            base_collector: The underlying metrics collector to wrap
        """
        self._base_collector = base_collector
        self._callbacks: Dict[LifecycleEvent, List[MonitoringCallback]] = {
            event: [] for event in LifecycleEvent
        }
        self._lock = Lock()

    def register_callback(
        self,
        event: LifecycleEvent,
        callback: MonitoringCallback
    ) -> None:
        """
        Register a callback for a specific lifecycle event.
        
        Args:
            event: The lifecycle event to listen for
            callback: The callback function to invoke
        """
        with self._lock:
            self._callbacks[event].append(callback)

    def unregister_callback(
        self,
        event: LifecycleEvent,
        callback: MonitoringCallback
    ) -> None:
        """
        Unregister a callback for a specific lifecycle event.
        
        Args:
            event: The lifecycle event
            callback: The callback function to remove
        """
        with self._lock:
            if callback in self._callbacks[event]:
                self._callbacks[event].remove(callback)

    def _invoke_callbacks(
        self,
        event: LifecycleEvent,
        queue_url: str,
        context: Dict[str, Any]
    ) -> None:
        """
        Invoke all registered callbacks for an event.
        
        Args:
            event: The lifecycle event
            queue_url: The queue URL
            context: Additional context information
        """
        with self._lock:
            callbacks = list(self._callbacks[event])

        for callback in callbacks:
            try:
                callback(event, queue_url, context)
            except Exception as e:
                logger.exception(
                    "Error invoking callback for event",
                    lifecycle_event=event.value,
                    queue_url=queue_url,
                    callback=callback.__name__,
                    error=str(e)
                )

    def increment_received(self, queue_url: str, count: int = 1) -> None:
        """Increment the count of messages received."""
        self._base_collector.increment_received(queue_url, count)
        self._invoke_callbacks(
            LifecycleEvent.MESSAGE_RECEIVED,
            queue_url,
            {"count": count}
        )

    def increment_processed(self, queue_url: str, count: int = 1) -> None:
        """Increment the count of messages successfully processed."""
        self._base_collector.increment_processed(queue_url, count)
        self._invoke_callbacks(
            LifecycleEvent.MESSAGE_PROCESSED,
            queue_url,
            {"count": count}
        )

    def increment_failed(self, queue_url: str, count: int = 1) -> None:
        """Increment the count of messages that failed processing."""
        self._base_collector.increment_failed(queue_url, count)
        self._invoke_callbacks(
            LifecycleEvent.MESSAGE_FAILED,
            queue_url,
            {"count": count}
        )

    def increment_acknowledged(self, queue_url: str, count: int = 1) -> None:
        """Increment the count of messages acknowledged (deleted)."""
        self._base_collector.increment_acknowledged(queue_url, count)
        self._invoke_callbacks(
            LifecycleEvent.MESSAGE_ACKNOWLEDGED,
            queue_url,
            {"count": count}
        )

    def get_metrics(self, queue_url: Optional[str] = None) -> Dict[str, MetricCounts]:
        """Get current metric counts from the base collector."""
        return self._base_collector.get_metrics(queue_url)
