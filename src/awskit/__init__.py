"""
AWSKit - A Pythonic, Spring-inspired toolkit for AWS services.

This library provides decorator-based patterns, automatic conversion,
and flexible configuration strategies for AWS services.

Currently supported services:
- SQS (Simple Queue Service)

Future services:
- SNS (Simple Notification Service)
- DynamoDB
- S3
- And more...
"""

try:
    from importlib.metadata import version
    __version__ = version("awskit")
except Exception:
    __version__ = "0.0.1"

# Configure structlog before any other imports
from awskit.logging_config import configure_structlog

configure_structlog()

# Convenience imports for SQS (most common use case)
from awskit.sqs import (
    sqs_listener,
    start_listeners,
    stop_listeners,
    get_listener_context,
    SqsTemplate,
    Message,
    SendResult,
    BatchSendResult,
    MessageListenerContainer,
    AcknowledgementProcessor,
    BackpressureManager,
    ListenerRegistry,
    SendFailure,
)

# Core shared modules
from awskit.config import (
    AcknowledgementMode,
    AcknowledgementOrdering,
    BackpressureMode,
    FifoGroupStrategy,
    QueueNotFoundStrategy,
    SendBatchFailureStrategy,
    SqsConfig,
    TemplateConfig,
    ListenerConfig,
    ContainerConfig,
    AcknowledgementConfig,
    load_config_from_env,
)
from awskit.converter import JsonMessageConverter, MessageConverter
from awskit.exceptions import (
    SqsIntegrationError,
    ConfigurationError,
    QueueNotFoundError,
    SerializationError,
    DeserializationError,
    ListenerError,
)
from awskit.metrics import (
    MetricsCollector,
    InMemoryMetricsCollector,
    NoOpMetricsCollector,
    CallbackMetricsCollector,
    PrometheusMetricsCollector,
    StatsDMetricsCollector,
    MetricCounts,
    LifecycleEvent,
    MonitoringCallback,
)

__all__ = [
    "__version__",
    # SQS - Main API
    "sqs_listener",
    "start_listeners",
    "stop_listeners",
    "get_listener_context",
    "SqsTemplate",
    "Message",
    "SendResult",
    "BatchSendResult",
    "SendFailure",
    "MessageListenerContainer",
    "AcknowledgementProcessor",
    "BackpressureManager",
    "ListenerRegistry",
    # Configuration
    "SqsConfig",
    "TemplateConfig",
    "ListenerConfig",
    "ContainerConfig",
    "AcknowledgementConfig",
    "AcknowledgementMode",
    "AcknowledgementOrdering",
    "BackpressureMode",
    "FifoGroupStrategy",
    "QueueNotFoundStrategy",
    "SendBatchFailureStrategy",
    "load_config_from_env",
    # Converters
    "MessageConverter",
    "JsonMessageConverter",
    # Exceptions
    "SqsIntegrationError",
    "ConfigurationError",
    "QueueNotFoundError",
    "SerializationError",
    "DeserializationError",
    "ListenerError",
    # Metrics
    "MetricsCollector",
    "InMemoryMetricsCollector",
    "NoOpMetricsCollector",
    "CallbackMetricsCollector",
    "PrometheusMetricsCollector",
    "StatsDMetricsCollector",
    "MetricCounts",
    "LifecycleEvent",
    "MonitoringCallback",
]
