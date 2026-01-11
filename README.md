# AWSKit - Python AWS Integration Toolkit

A Pythonic, Spring-inspired toolkit for AWS services that simplifies cloud-native application development. Built with decorator-based patterns, automatic lifecycle management, and comprehensive observability.

[![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## Currently Supported Services

- **Amazon SQS** - Full-featured message queue integration with FIFO support

## Key Features

### Core Capabilities
- **Decorator-Based Patterns** - Define message listeners with simple `@sqs_listener` decorators
- **Automatic Lifecycle Management** - Container, threading, and polling handled automatically
- **Smart Message Conversion** - Seamless serialization/deserialization (dataclasses, Pydantic, dicts)
- **Flexible Acknowledgement** - Control message deletion: on success, always, or manual
- **FIFO Queue Support** - Message ordering and exactly-once processing guaranteed

### Advanced Features
- **Intelligent Backpressure** - Automatic polling rate control prevents system overload
- **Robust Error Handling** - Custom error handlers with exponential backoff retry
- **Built-in Observability** - Prometheus/StatsD metrics + structured logging (structlog)
- **Full Type Safety** - Complete type hints for excellent IDE support
- **Testing Ready** - LocalStack integration for local development and testing

## Installation

```bash
# Basic installation
pip install awskit

# With metrics support (Prometheus/StatsD)
pip install awskit[metrics]

# With all optional dependencies
pip install awskit[all]
```

**Requirements:**
- Python 3.9+
- boto3 >= 1.26.0
- structlog >= 23.1.0

## Quick Start

### Receiving Messages (Automatic Mode)

The simplest way to process SQS messages - just define listeners and call `start_listeners()`:

```python
import boto3
from awskit.sqs import sqs_listener, start_listeners
from dataclasses import dataclass

@dataclass
class Order:
    order_id: int
    amount: float
    customer_id: str

# Define your listener - threading handled automatically!
@sqs_listener("orders-queue", max_concurrent_messages=5)
def process_order(order: Order):
    print(f"Processing order {order.order_id} for ${order.amount}")
    # Your business logic here

# Start processing with one line
client = boto3.client('sqs', region_name='us-east-1')
start_listeners(client)
```

**That's it!** The library automatically handles:
- Message listener container creation
- Thread pool management
- Polling threads for each queue
- Message deserialization
- Graceful shutdown

### Sending Messages

Send messages with automatic serialization:

```python
from awskit.sqs import SqsTemplate
from awskit.converter import JsonMessageConverter

# Create template
template = SqsTemplate(
    client=boto3.client('sqs', region_name='us-east-1'),
    converter=JsonMessageConverter()
)

# Send a message
result = template.send(
    queue="orders-queue",
    payload={"order_id": 123, "amount": 99.99}
)
print(f"Message sent: {result.message_id}")
```

## Usage Examples

### Multiple Listeners

Process different queues with independent configurations:

```python
from awskit.sqs import sqs_listener, start_listeners

@sqs_listener("orders-queue", max_concurrent_messages=10)
def process_order(order: Order):
    print(f"Processing order: {order.order_id}")

@sqs_listener("payments-queue", max_concurrent_messages=5)
def process_payment(payment: Payment):
    print(f"Processing payment: {payment.payment_id}")

@sqs_listener("notifications-queue", max_concurrent_messages=20)
def send_notification(notification: Notification):
    print(f"Sending notification: {notification.type}")

# Start ALL listeners with ONE call
client = boto3.client('sqs', region_name='us-east-1')
start_listeners(client)
```

### Manual Acknowledgement

Control exactly when messages are deleted:

```python
from awskit.sqs import sqs_listener, AcknowledgementMode, Acknowledgement

@sqs_listener("critical-queue", acknowledgement_mode=AcknowledgementMode.MANUAL)
def process_critical_message(message: dict, ack: Acknowledgement):
    try:
        result = process_payment(message)
        if result.success:
            ack.acknowledge()  # Only acknowledge on success
    except Exception as e:
        # Don't acknowledge - message will be retried
        print(f"Processing failed: {e}")
```

### FIFO Queue Support

Process messages in order with FIFO queues:

```python
from awskit.sqs import sqs_listener, FifoGroupStrategy

# Send to FIFO queue
template.send(
    queue="orders.fifo",
    payload={"order_id": 123, "status": "pending"},
    message_group_id="customer-456",
    deduplication_id="order-123-v1"
)

# Process FIFO messages
@sqs_listener(
    "orders.fifo",
    message_group_strategy=FifoGroupStrategy.PARALLEL_BATCHES_PER_GROUP
)
def process_fifo_order(order: dict):
    print(f"Processing order {order['order_id']} in order")
```

### Batch Processing

Process multiple messages at once:

```python
from typing import List

@sqs_listener("batch-queue", batch=True, max_messages_per_poll=10)
def process_batch(messages: List[dict]):
    print(f"Processing batch of {len(messages)} messages")
    for message in messages:
        # Process each message
        handle_message(message)
```

### Custom Error Handling

Define custom error handlers:

```python
def handle_error(exception: Exception, message: Any, context: dict):
    print(f"Error processing {context.get('message_id')}: {exception}")
    # Send to DLQ, log to external service, etc.

@sqs_listener("my-queue", error_handler=handle_error)
def process_message(message: dict):
    # Your processing logic
    process_data(message)
```

## Configuration

### Python Configuration

```python
from awskit.sqs import SqsConfig, TemplateConfig, ContainerConfig, BackpressureMode

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

start_listeners(client, config=config)
```

### Environment Variables

```bash
export SQS_REGION=us-east-1
export SQS_ENDPOINT_URL=http://localhost:4566  # For LocalStack
export SQS_TEMPLATE_QUEUE_NOT_FOUND_STRATEGY=CREATE
export SQS_CONTAINER_BACKPRESSURE_MODE=AUTO
export SQS_ACKNOWLEDGEMENT_INTERVAL_SECONDS=1.0
```

Load from environment:

```python
from awskit.sqs import load_config_from_env

config = load_config_from_env(prefix="SQS")
start_listeners(client, config=config)
```

## Observability

### Metrics Collection

Built-in support for Prometheus and StatsD:

```python
from awskit.metrics import PrometheusMetricsCollector, InMemoryMetricsCollector

# Prometheus metrics
metrics = PrometheusMetricsCollector(namespace="my_app")

# Or in-memory for testing
metrics = InMemoryMetricsCollector()

start_listeners(client, metrics_collector=metrics)
```

**Available Metrics:**
- `messages_received_total` - Total messages received from SQS
- `messages_processed_total` - Successfully processed messages
- `messages_failed_total` - Failed message processing attempts
- `messages_acknowledged_total` - Messages acknowledged (deleted)

### Structured Logging

Built-in structured logging with contextual information:

```python
import structlog

logger = structlog.get_logger(__name__)

@sqs_listener("orders-queue")
def process_order(order: Order):
    logger.info("processing_order", order_id=order.order_id, amount=order.amount)
    # Logs include: message_id, queue_url, timestamp, etc.
```

## Complete Example

Here's a production-ready example:

```python
import boto3
from dataclasses import dataclass
from awskit.sqs import (
    sqs_listener,
    start_listeners,
    stop_listeners,
    AcknowledgementMode,
    SqsConfig,
    ContainerConfig,
    BackpressureMode,
)

@dataclass
class OrderMessage:
    order_id: int
    customer_id: str
    amount: float
    items: list

@sqs_listener(
    "orders-queue",
    acknowledgement_mode=AcknowledgementMode.ON_SUCCESS,
    max_concurrent_messages=10
)
def process_order(order: OrderMessage):
    print(f"Processing order {order.order_id} for customer {order.customer_id}")
    calculate_total(order)
    update_inventory(order.items)
    send_confirmation(order.customer_id)

# Configure and start
config = SqsConfig(
    container=ContainerConfig(backpressure_mode=BackpressureMode.AUTO)
)

client = boto3.client('sqs', region_name='us-east-1')
start_listeners(client, config=config)

# Graceful shutdown
try:
    import time
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Shutting down...")
    stop_listeners(timeout_seconds=30)
```

## Testing

### Running Tests

```bash
# Install with test dependencies
pip install awskit[test]

# Run test suite
pytest tests/

# Run with coverage
pytest --cov=awskit tests/
```

### LocalStack Integration

Test with LocalStack for local AWS simulation:

```python
import boto3

# Connect to LocalStack
client = boto3.client(
    'sqs',
    region_name='us-east-1',
    endpoint_url='http://localhost:4566'
)

# Use with awskit as normal
from awskit.sqs import SqsTemplate, JsonMessageConverter

template = SqsTemplate(client=client, converter=JsonMessageConverter())
# Test your code locally!
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Links

- **PyPI**: https://pypi.org/project/awskit/
- **Documentation**: Full API documentation available in docstrings
- **Issues**: Report bugs and request features on GitHub
