"""
Exception hierarchy for the SQS integration library.

This module defines all custom exceptions used throughout the library,
providing a clear hierarchy for error handling.
"""


class SqsIntegrationError(Exception):
    """
    Base exception for all library errors.

    All custom exceptions in this library inherit from this base class,
    allowing users to catch all library-specific errors with a single
    exception handler if desired.
    """

    pass


class ConfigurationError(SqsIntegrationError):
    """
    Raised when configuration is invalid.

    This exception is raised during initialization when the provided
    configuration contains invalid values, missing required fields,
    or conflicting settings.

    Examples:
        - Invalid enum values
        - Negative timeouts or thresholds
        - Missing required fields
        - Conflicting settings
    """

    pass


class QueueNotFoundError(SqsIntegrationError):
    """
    Raised when a queue doesn't exist and strategy is FAIL.

    This exception is raised when attempting to interact with a queue
    that doesn't exist and the configured QueueNotFoundStrategy is set
    to FAIL rather than CREATE.
    """

    pass


class SerializationError(SqsIntegrationError):
    """
    Raised when message serialization fails.

    This exception is raised when the MessageConverter is unable to
    serialize a payload to the target format (e.g., JSON).
    """

    pass


class DeserializationError(SqsIntegrationError):
    """
    Raised when message deserialization fails.

    This exception is raised when the MessageConverter is unable to
    deserialize a message body to the target Python type. The exception
    should include context about the message body, target type, and
    underlying error.
    """

    pass


class ListenerError(SqsIntegrationError):
    """
    Wrapper for exceptions raised by listener functions.

    This exception wraps exceptions that occur during listener function
    execution, providing additional context about the message being
    processed and the queue it came from.
    """

    pass
