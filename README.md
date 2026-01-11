# AWSKit - Python AWS Integration Toolkit

A Pythonic, Spring-inspired toolkit for AWS services that simplifies integration with AWS. This library provides decorator-based patterns, automatic conversion, flexible configuration strategies, and comprehensive error handling - making it easy to build robust cloud-native applications.

## Currently Supported Services

- **SQS (Simple Queue Service)** - Full-featured message queue integration

## Features

- **🎯 Decorator-based patterns**: Define listeners and handlers using simple Python decorators
- **🚀 Automatic container management**: Just call `start_listeners()` - threading, polling, and lifecycle are handled automatically (like Spring Cloud AWS)
- **🔄 Automatic message conversion**: Seamless serialization/deserialization of Python objects (dataclasses, Pydantic models, dicts)
- **✅ Flexible acknowledgement strategies**: Control when messages are deleted from queues (on success, always, or manual)
- **📋 FIFO queue support**: First-class support for FIFO queues with message ordering and exactly-once processing
- **⚡ Backpressure management**: Automatic polling rate control based on processing capacity to prevent overload
- **🛡️ Comprehensive error handling**: Robust error handling with custom error handlers and exponential backoff
- **📊 Observability**: Built-in metrics collection with Prometheus and StatsD support, structured logging
- **🔧 Type hints**: Full type hint support for better IDE integration and type safety
- **🧪 Comprehensive testing**: Full test coverage with support for LocalStack integration testing

## Installation

Install from PyPI:

```bash
pip install awskit
```

For metrics support (Prometheus/StatsD):

```bash
pip install awskit[metrics]
```

## Quick Start

### Basic SQS Message Receiving (Automatic Container Management)

The simplest way to start processing SQS messages - just define your listener and call `start_listeners()`:

```python
import boto3
from awskit.sqs import sqs_listener, start_listeners
from dataclasses import dataclass

@dataclass
class Order:
    order_id: int
    amount: float

# Just define your listener - threading is handled automatically!
@sqs_listener("orders-queue", max_concurrent_messages=5)
def process_order(message: Order):
    """Process incoming orders."""
    print(f"Processing order {message.order_id} for ${message.amount}")
    # Your business logic here

# Start all listeners with one line - container, threads, and polling are automatic
client = boto3.client('sqs', region_name='us-east-1')
start_listeners(client)
```

**That's it!** The library automatically:
- Creates the message listener container
- Sets up thread pools for concurrent processing
- Starts polling threads for each queue
- Manages all threading and lifecycle

> **Multiple listeners?** Yes! Define as many `@sqs_listener` functions as you need for different queues. A single `start_listeners()` call starts them all. See [Multiple Listeners Guide](MULTIPLE_LISTENERS.md).

> **Migrating from manual container management?** See the [Migration Guide](MIGRATION_GUIDE.md) for a smooth transition.

### Basic Message Sending

Send messages to SQS queues with automatic serialization:

```python
import boto3
from sqs_integration import SqsTemplate, JsonMessageConverter

# Create SQS client
client = boto3.client('sqs', region_name='us-east-1')

# Create template with JSON converter
template = SqsTemplate(
    client=client,
    converter=JsonMessageConverter()
)

# Send a message
result = template.send(
    queue="my-queue",
    payload={"order_id": 123, "amount": 99.99}
)
print(f"Message sent: {result.message_id}")
```

### Multiple Listeners

Define multiple listeners for different queues - they all start with one call:

```python
from sqs_integration import sqs_listener, start_listeners

# Listener 1: Process orders
@sqs_listener("orders-queue", max_concurrent_messages=10)
def process_order(message: Order):
    print(f"Processing order: {message.order_id}")

# Listener 2: Process payments
@sqs_listener("payments-queue", max_concurrent_messages=5)
def process_payment(message: Payment):
    print(f"Processing payment: {message.payment_id}")

# Listener 3: Send notifications
@sqs_listener("notifications-queue", max_concurrent_messages=20)
def send_notification(message: Notification):
    print(f"Sending notification: {message.type}")

# Start ALL listeners with ONE call!
client = boto3.client('sqs', region_name='us-east-1')
start_listeners(client)  # All 3 listeners now running!
```

Each listener:
- Has its own polling thread
- Respects its own concurrency limits
- Can have different acknowledgement modes
- Can process different message types

See the [Multiple Listeners Guide](MULTIPLE_LISTENERS.md) for more details.

### Manual Container Management (Advanced)

For advanced use cases, you can manually manage the container:

```python
from sqs_integration import MessageListenerContainer, JsonMessageConverter

# Manually create and configure the container
container = MessageListenerContainer(
    client=client,
    converter=JsonMessageConverter(),
    acknowledgement_processor=acknowledgement_processor,
    backpressure_manager=backpressure_manager
)
container.start()
```

### Manual Acknowledgement

Control exactly when messages are deleted from the queue:

```python
from sqs_integration import sqs_listener, AcknowledgementMode, Acknowledgement

@sqs_listener(
    "critical-queue",
    acknowledgement_mode=AcknowledgementMode.MANUAL
)
def process_critical_message(message: dict, ack: Acknowledgement):
    """Process critical messages with manual acknowledgement."""
    try:
        # Process the message
        result = process_payment(message)
        
        # Only acknowledge if processing succeeded
        if result.success:
            ack.acknowledge()
    except Exception as e:
        # Don't acknowledge - message will be retried
        print(f"Processing failed: {e}")
```

### FIFO Queue Support

Work with FIFO queues for ordered message processing:

```python
from sqs_integration import sqs_listener, FifoGroupStrategy

# Send to FIFO queue
template.send(
    queue="orders.fifo",
    payload={"order_id": 123, "status": "pending"},
    message_group_id="customer-456",
    deduplication_id="order-123-v1"
)

# Listen to FIFO queue
@sqs_listener(
    "orders.fifo",
    message_group_strategy=FifoGroupStrategy.PARALLEL_BATCHES_PER_GROUP
)
def process_fifo_order(message: dict):
    """Process orders in order within each customer group."""
    print(f"Processing order {message['order_id']}")
```

### Batch Processing

Process multiple messages at once for improved throughput:

```python
from typing import List

@sqs_listener(
    "batch-queue",
    batch=True,
    max_messages_per_poll=10
)
def process_batch(messages: List[dict]):
    """Process messages in batches."""
    print(f"Processing batch of {len(messages)} messages")
    for message in messages:
        # Process each message
        pass
```

### Custom Error Handling

Define custom error handlers for specific queues:

```python
def handle_processing_error(exception: Exception, message: Any, context: dict):
    """Custom error handler for failed messages."""
    print(f"Error processing message {context.get('message_id')}: {exception}")
    # Send to dead letter queue, log to external service, etc.

@sqs_listener(
    "my-queue",
    error_handler=handle_processing_error
)
def process_message(message: dict):
    """Process messages with custom error handling."""
    # Your processing logic
    pass
```

### Configuration

Configure the library using Python objects or environment variables:

```python
from sqs_integration import (
    SqsConfig,
    TemplateConfig,
    ContainerConfig,
    AcknowledgementConfig,
    QueueNotFoundStrategy,
    BackpressureMode
)

# Create configuration
config = SqsConfig(
    region="us-east-1",
    template=TemplateConfig(
        queue_not_found_strategy=QueueNotFoundStrategy.CREATE
    ),
    container=ContainerConfig(
        backpressure_mode=BackpressureMode.AUTO,
        max_delay_between_polls_seconds=10
    ),
    acknowledgement=AcknowledgementConfig(
        interval_seconds=1.0,
        threshold=10
    )
)

# Or load from environment variables
from sqs_integration import load_config_from_env

config = load_config_from_env(prefix="SQS_")
```

Environment variables:
```bash
export SQS_REGION=us-east-1
export SQS_ENDPOINT_URL=http://localhost:4566  # For LocalStack
export SQS_TEMPLATE_QUEUE_NOT_FOUND_STRATEGY=CREATE
export SQS_CONTAINER_BACKPRESSURE_MODE=AUTO
```

## Complete Example

Here's a complete example showing automatic container management:

```python
import boto3
from dataclasses import dataclass
from sqs_integration import (
    sqs_listener,
    start_listeners,
    stop_listeners,
    AcknowledgementMode,
    SqsConfig,
    ContainerConfig,
    BackpressureMode,
)

# Define your message model
@dataclass
class OrderMessage:
    order_id: int
    customer_id: str
    amount: float
    items: list

# Define listener with decorator - threading is automatic!
@sqs_listener(
    "orders-queue",
    acknowledgement_mode=AcknowledgementMode.ON_SUCCESS,
    max_concurrent_messages=10
)
def process_order(message: OrderMessage):
    """Process incoming orders."""
    print(f"Processing order {message.order_id} for customer {message.customer_id}")
    # Your business logic here
    calculate_total(message)
    update_inventory(message.items)
    send_confirmation(message.customer_id)

# Optional: Create custom configuration
config = SqsConfig(
    container=ContainerConfig(
        backpressure_mode=BackpressureMode.AUTO
    )
)

# Start all listeners - container and threading managed automatically
client = boto3.client('sqs', region_name='us-east-1')
start_listeners(client, config=config)

# That's it! The container is now running and processing messages
# Press Ctrl+C to stop gracefully
try:
    import time
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Shutting down...")
    stop_listeners(timeout_seconds=30)
```

### Manual Container Management (Advanced)

For advanced use cases where you need full control:

```python
from sqs_integration import (
    MessageListenerContainer,
    JsonMessageConverter,
    AcknowledgementProcessor,
    BackpressureManager,
    AcknowledgementConfig,
    ContainerConfig,
)

# Create components manually
converter = JsonMessageConverter()
ack_processor = AcknowledgementProcessor(
    client=client,
    config=AcknowledgementConfig(interval_seconds=1.0, threshold=10)
)
backpressure_manager = BackpressureManager(mode=BackpressureMode.AUTO)

# Create and start container
container = MessageListenerContainer(
    client=client,
    converter=converter,
    acknowledgement_processor=ack_processor,
    backpressure_manager=backpressure_manager,
    config=ContainerConfig(auto_startup=True)
)

try:
    container.start()
    # Keep running until interrupted
    import time
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Shutting down...")
    container.stop(timeout_seconds=30)
```

## Testing

The library includes comprehensive test coverage. You can run the test suite with:

```bash
pip install python-aws-integration[test]
pytest tests/
```

For integration testing, use LocalStack to simulate AWS SQS locally:

```python
import boto3

# Create SQS client connected to LocalStack
client = boto3.client(
    'sqs',
    region_name='us-east-1',
    endpoint_url='http://localhost:4566'  # LocalStack endpoint
)

# Use the client with SqsTemplate as usual
from sqs_integration import SqsTemplate, JsonMessageConverter

template = SqsTemplate(client=client, converter=JsonMessageConverter())
# Now you can test with LocalStack
```

## Requirements

- Python 3.9 or later
- boto3 >= 1.26.0
- typing-extensions >= 4.5.0

## Documentation

This README provides a quick start guide. For detailed documentation:

- **Installation**: `pip install python-aws-integration`
- **Quick Start**: See examples above
- **Full API**: All classes and functions are fully documented with docstrings
- **Type Hints**: The library uses comprehensive type hints for better IDE support

For questions or issues, please open an issue on the GitHub repository.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see [LICENSE](LICENSE) file for details.