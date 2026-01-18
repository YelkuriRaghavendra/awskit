"""
Configuration models for the SQS integration library.

This module defines all configuration dataclasses and enums used to configure
the behavior of the SQS integration library, including template settings,
listener settings, container settings, and acknowledgement settings.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional, Type, TypeVar, get_type_hints

from awskit.exceptions import ConfigurationError


class AcknowledgementMode(Enum):
    """
    When to acknowledge (delete) messages from the queue.

    Attributes:
        ON_SUCCESS: Delete messages only if the listener function succeeds
        ALWAYS: Delete messages regardless of listener outcome
        MANUAL: Listener controls acknowledgement explicitly
    """

    ON_SUCCESS = "on_success"
    ALWAYS = "always"
    MANUAL = "manual"


class QueueNotFoundStrategy(Enum):
    """
    What to do when a queue doesn't exist.

    Attributes:
        CREATE: Create the queue automatically with default settings
        FAIL: Raise a QueueNotFoundError
    """

    CREATE = "create"
    FAIL = "fail"


class SendBatchFailureStrategy(Enum):
    """
    How to handle batch send failures.

    Attributes:
        THROW: Raise an exception with failure details
        DO_NOT_THROW: Return result with failures without raising
    """

    THROW = "throw"
    DO_NOT_THROW = "do_not_throw"


class BackpressureMode(Enum):
    """
    Backpressure strategy for controlling polling rate.

    Attributes:
        AUTO: Switch between low and high throughput based on message availability
        ALWAYS_POLL_MAX: Always poll for maximum messages
        FIXED_HIGH_THROUGHPUT: Always use parallel polls at high rate
    """

    AUTO = "auto"
    ALWAYS_POLL_MAX = "always_poll_max"
    FIXED_HIGH_THROUGHPUT = "fixed_high_throughput"


class FifoGroupStrategy(Enum):
    """
    How to batch FIFO messages by message group.

    Attributes:
        PARALLEL_BATCHES_PER_GROUP: Create separate batches per message group
        MIXED_GROUPS_IN_BATCH: Allow mixed message groups in a single batch
    """

    PARALLEL_BATCHES_PER_GROUP = "parallel_batches_per_group"
    MIXED_GROUPS_IN_BATCH = "mixed_groups_in_batch"


class AcknowledgementOrdering(Enum):
    """
    Order of acknowledgements for FIFO queues.

    Attributes:
        PARALLEL: Acknowledge messages in any order
        ORDERED: Acknowledge messages in receive order
    """

    PARALLEL = "parallel"
    ORDERED = "ordered"


@dataclass
class TemplateConfig:
    """
    Configuration for SqsTemplate.

    Attributes:
        queue_not_found_strategy: What to do when a queue doesn't exist
        default_poll_timeout_seconds: Default wait time for long polling
        default_max_messages: Default maximum messages to receive per poll
        send_batch_failure_strategy: How to handle batch send failures
    """

    queue_not_found_strategy: QueueNotFoundStrategy = QueueNotFoundStrategy.CREATE
    default_poll_timeout_seconds: int = 10
    default_max_messages: int = 10
    send_batch_failure_strategy: SendBatchFailureStrategy = SendBatchFailureStrategy.THROW


@dataclass
class ListenerConfig:
    """
    Configuration for a single message listener.

    Attributes:
        queue: Queue name or URL to listen to
        acknowledgement_mode: When to acknowledge messages
        max_concurrent_messages: Maximum messages to process concurrently
        max_messages_per_poll: Maximum messages to retrieve per poll
        poll_timeout_seconds: Wait time for long polling
        batch: Whether to receive messages in batches
        visibility_timeout: Custom visibility timeout for messages (seconds)
        message_group_strategy: Strategy for batching FIFO messages
        error_handler: Optional custom error handler function
    """

    queue: str
    acknowledgement_mode: AcknowledgementMode = AcknowledgementMode.ON_SUCCESS
    max_concurrent_messages: int = 10
    max_messages_per_poll: int = 10
    poll_timeout_seconds: int = 10
    batch: bool = False
    visibility_timeout: Optional[int] = None
    message_group_strategy: Optional[FifoGroupStrategy] = None
    error_handler: Optional[Callable[[Exception, Any, Dict[str, Any]], None]] = None


@dataclass
class BackoffPolicy:
    """
    Configuration for exponential backoff on polling errors.

    Attributes:
        initial_interval_seconds: Initial backoff interval
        multiplier: Multiplier for each retry (exponential backoff)
        max_interval_seconds: Maximum backoff interval
        max_retries: Maximum number of retries before giving up (None for infinite)
    """

    initial_interval_seconds: float = 1.0
    multiplier: float = 2.0
    max_interval_seconds: float = 60.0
    max_retries: Optional[int] = None


@dataclass
class ContainerConfig:
    """
    Configuration for MessageListenerContainer.

    Attributes:
        backpressure_mode: Strategy for controlling polling rate
        max_delay_between_polls_seconds: Maximum delay between poll attempts
        listener_shutdown_timeout_seconds: Timeout for listener shutdown
        acknowledgement_shutdown_timeout_seconds: Timeout for acknowledgement flush
        auto_startup: Whether to start the container automatically
        backoff_policy: Backoff policy for polling errors
    """

    backpressure_mode: BackpressureMode = BackpressureMode.AUTO
    max_delay_between_polls_seconds: int = 10
    listener_shutdown_timeout_seconds: int = 20
    acknowledgement_shutdown_timeout_seconds: int = 20
    auto_startup: bool = True
    backoff_policy: BackoffPolicy = field(default_factory=BackoffPolicy)


@dataclass
class AcknowledgementConfig:
    """
    Configuration for acknowledgement processing.

    Attributes:
        interval_seconds: Time interval for batching acknowledgements
        threshold: Number of messages to trigger batch acknowledgement
        ordering: Order of acknowledgements (parallel or ordered)
    """

    interval_seconds: float = 1.0
    threshold: int = 10
    ordering: AcknowledgementOrdering = AcknowledgementOrdering.PARALLEL


@dataclass
class SqsConfig:
    """
    Root configuration for the SQS integration library.

    Attributes:
        region: AWS region name
        endpoint_url: Custom endpoint URL (for LocalStack, etc.)
        aws_access_key_id: AWS access key ID
        aws_secret_access_key: AWS secret access key
        template: Template configuration
        container: Container configuration
        acknowledgement: Acknowledgement configuration
    """

    region: Optional[str] = None
    endpoint_url: Optional[str] = None
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    template: TemplateConfig = field(default_factory=TemplateConfig)
    container: ContainerConfig = field(default_factory=ContainerConfig)
    acknowledgement: AcknowledgementConfig = field(default_factory=AcknowledgementConfig)


T = TypeVar("T")


def _parse_value(value: str, target_type: Type[Any]) -> Any:
    """
    Parse a string value to the target type.

    Args:
        value: String value from environment variable
        target_type: Target type to convert to

    Returns:
        Parsed value of the target type

    Raises:
        ConfigurationError: If value cannot be parsed to target type
    """
    # Handle None/Optional
    if value.lower() in ("none", "null", ""):
        return None

    # Handle bool
    if target_type == bool:
        if value.lower() in ("true", "1", "yes", "on"):
            return True
        elif value.lower() in ("false", "0", "no", "off"):
            return False
        else:
            raise ConfigurationError(f"Invalid boolean value: {value}")

    # Handle int
    if target_type == int:
        try:
            return int(value)
        except ValueError:
            raise ConfigurationError(f"Invalid integer value: {value}")

    # Handle float
    if target_type == float:
        try:
            return float(value)
        except ValueError:
            raise ConfigurationError(f"Invalid float value: {value}")

    # Handle Enum types
    if isinstance(target_type, type) and issubclass(target_type, Enum):
        try:
            # Try by value first
            return target_type(value)
        except ValueError:
            # Try by name
            try:
                return target_type[value.upper()]
            except KeyError:
                valid_values = [e.value for e in target_type]
                raise ConfigurationError(
                    f"Invalid {target_type.__name__} value: {value}. "
                    f"Valid values: {', '.join(valid_values)}"
                )

    # Handle str (default)
    return value


def _load_nested_config(prefix: str, config_class: Type[T], env_vars: Dict[str, str]) -> T:
    """
    Load a nested configuration object from environment variables.

    Args:
        prefix: Environment variable prefix (e.g., "SQS_TEMPLATE")
        config_class: Configuration dataclass to instantiate
        env_vars: Dictionary of environment variables

    Returns:
        Instance of config_class with values from environment variables
    """
    type_hints = get_type_hints(config_class)
    kwargs: Dict[str, Any] = {}

    for field_name, field_type in type_hints.items():
        # Convert field_name to uppercase with underscores
        env_key = f"{prefix}_{field_name.upper()}"

        if env_key in env_vars:
            try:
                kwargs[field_name] = _parse_value(env_vars[env_key], field_type)
            except ConfigurationError as e:
                raise ConfigurationError(f"Error parsing {env_key}: {e}")

    return config_class(**kwargs)


def load_config_from_env(prefix: str = "SQS") -> SqsConfig:
    """
    Load SqsConfig from environment variables.

    Environment variables should be prefixed with the given prefix (default "SQS").
    Nested configuration uses double underscores, e.g.:
    - SQS_REGION for region
    - SQS_TEMPLATE_DEFAULT_POLL_TIMEOUT_SECONDS for template.default_poll_timeout_seconds
    - SQS_CONTAINER_BACKPRESSURE_MODE for container.backpressure_mode
    - SQS_ACKNOWLEDGEMENT_INTERVAL_SECONDS for acknowledgement.interval_seconds

    Args:
        prefix: Environment variable prefix (default: "SQS")

    Returns:
        SqsConfig instance populated from environment variables

    Raises:
        ConfigurationError: If environment variables contain invalid values

    Example:
        >>> os.environ["SQS_REGION"] = "us-east-1"
        >>> os.environ["SQS_TEMPLATE_DEFAULT_POLL_TIMEOUT_SECONDS"] = "20"
        >>> config = load_config_from_env()
        >>> config.region
        'us-east-1'
        >>> config.template.default_poll_timeout_seconds
        20
    """
    env_vars = dict(os.environ)

    # Load root-level fields
    root_kwargs: Dict[str, Any] = {}
    root_type_hints = get_type_hints(SqsConfig)

    for field_name, field_type in root_type_hints.items():
        env_key = f"{prefix}_{field_name.upper()}"

        # Skip nested config objects
        if field_type in (TemplateConfig, ContainerConfig, AcknowledgementConfig):
            continue

        if env_key in env_vars:
            try:
                root_kwargs[field_name] = _parse_value(env_vars[env_key], field_type)
            except ConfigurationError as e:
                raise ConfigurationError(f"Error parsing {env_key}: {e}")

    # Load nested configurations
    template_prefix = f"{prefix}_TEMPLATE"
    container_prefix = f"{prefix}_CONTAINER"
    acknowledgement_prefix = f"{prefix}_ACKNOWLEDGEMENT"

    # Check if any nested config vars exist
    has_template_vars = any(k.startswith(template_prefix) for k in env_vars)
    has_container_vars = any(k.startswith(container_prefix) for k in env_vars)
    has_acknowledgement_vars = any(k.startswith(acknowledgement_prefix) for k in env_vars)

    if has_template_vars:
        root_kwargs["template"] = _load_nested_config(template_prefix, TemplateConfig, env_vars)

    if has_container_vars:
        root_kwargs["container"] = _load_nested_config(container_prefix, ContainerConfig, env_vars)

    if has_acknowledgement_vars:
        root_kwargs["acknowledgement"] = _load_nested_config(
            acknowledgement_prefix, AcknowledgementConfig, env_vars
        )

    return SqsConfig(**root_kwargs)
