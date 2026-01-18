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

from awskit.config import (
    AcknowledgementConfig,
    AcknowledgementMode,
    AcknowledgementOrdering,
    BackpressureMode,
    ContainerConfig,
    FifoGroupStrategy,
    ListenerConfig,
    QueueNotFoundStrategy,
    SendBatchFailureStrategy,
    SqsConfig,
    TemplateConfig,
    load_config_from_env,
)
from awskit.converter import JsonMessageConverter, MessageConverter
from awskit.exceptions import (
    ConfigurationError,
    DeserializationError,
    ListenerError,
    QueueNotFoundError,
    SerializationError,
    SqsIntegrationError,
)
from awskit.logging_config import configure_structlog
from awskit.metrics import (
    CallbackMetricsCollector,
    InMemoryMetricsCollector,
    LifecycleEvent,
    MetricCounts,
    MetricsCollector,
    MonitoringCallback,
    NoOpMetricsCollector,
    PrometheusMetricsCollector,
    StatsDMetricsCollector,
)
from awskit.sqs import (
    AcknowledgementProcessor,
    BackpressureManager,
    BatchSendResult,
    ListenerRegistry,
    Message,
    MessageListenerContainer,
    SendFailure,
    SendResult,
    SqsTemplate,
    get_listener_context,
    sqs_listener,
    start_listeners,
    stop_listeners,
)

configure_structlog()

__all__ = [
    "__version__",
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
    "MessageConverter",
    "JsonMessageConverter",
    "SqsIntegrationError",
    "ConfigurationError",
    "QueueNotFoundError",
    "SerializationError",
    "DeserializationError",
    "ListenerError",
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
