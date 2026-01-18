"""
AWS SQS integration module.

This module provides Spring-inspired patterns for working with AWS SQS,
including decorator-based listeners, automatic message conversion, and
flexible acknowledgement strategies.
"""

from awskit.sqs.acknowledgement import AcknowledgementProcessor
from awskit.sqs.backpressure import BackpressureManager
from awskit.sqs.container import MessageListenerContainer
from awskit.sqs.context import (
    SqsListenerContext,
    get_listener_context,
    start_listeners,
    stop_listeners,
)
from awskit.sqs.decorator import sqs_listener
from awskit.sqs.models import (
    BatchSendResult,
    Message,
    SendFailure,
    SendResult,
)
from awskit.sqs.registry import ListenerRegistry
from awskit.sqs.template import SqsTemplate

__all__ = [
    # Core classes
    "SqsTemplate",
    "MessageListenerContainer",
    "AcknowledgementProcessor",
    "BackpressureManager",
    "ListenerRegistry",
    # Decorators
    "sqs_listener",
    # Context management
    "start_listeners",
    "stop_listeners",
    "get_listener_context",
    "SqsListenerContext",
    # Models
    "Message",
    "SendResult",
    "BatchSendResult",
    "SendFailure",
]
