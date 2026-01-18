"""
Unit tests for SqsTemplate.
"""

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from awskit.config import QueueNotFoundStrategy, SendBatchFailureStrategy, TemplateConfig
from awskit.converter import JsonMessageConverter
from awskit.exceptions import QueueNotFoundError, SerializationError
from awskit.sqs.template import SqsTemplate


@dataclass
class TestPayload:
    """Test payload for messages."""

    id: int
    message: str


class TestSqsTemplate:
    """Tests for SqsTemplate."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.client = MagicMock()
        self.converter = JsonMessageConverter()
        self.config = TemplateConfig()
        self.template = SqsTemplate(self.client, self.converter, self.config)

    def test_resolve_queue_url_with_url(self) -> None:
        """Test resolving queue URL when given a URL."""
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"
        result = self.template._resolve_queue_url(queue_url)
        assert result == queue_url
        # Should not call AWS API
        self.client.get_queue_url.assert_not_called()

    def test_resolve_queue_url_by_name(self) -> None:
        """Test resolving queue URL by name."""
        queue_name = "test-queue"
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"
        self.client.get_queue_url.return_value = {"QueueUrl": queue_url}

        result = self.template._resolve_queue_url(queue_name)

        assert result == queue_url
        self.client.get_queue_url.assert_called_once_with(QueueName=queue_name)

    def test_resolve_queue_url_caching(self) -> None:
        """Test that queue URL resolution is cached."""
        queue_name = "test-queue"
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"
        self.client.get_queue_url.return_value = {"QueueUrl": queue_url}

        # First call
        result1 = self.template._resolve_queue_url(queue_name)
        # Second call
        result2 = self.template._resolve_queue_url(queue_name)

        assert result1 == queue_url
        assert result2 == queue_url
        # Should only call AWS API once
        self.client.get_queue_url.assert_called_once()

    def test_resolve_queue_url_not_found_create(self) -> None:
        """Test that queue not found raises error even with CREATE strategy."""
        queue_name = "new-queue"

        # Mock QueueDoesNotExist exception
        queue_not_exist = type("QueueDoesNotExist", (Exception,), {})
        self.client.exceptions.QueueDoesNotExist = queue_not_exist
        self.client.get_queue_url.side_effect = queue_not_exist()

        # Should raise QueueNotFoundError (queue creation not implemented)
        with pytest.raises(QueueNotFoundError) as exc_info:
            self.template._resolve_queue_url(queue_name)

        assert "new-queue" in str(exc_info.value)

    def test_resolve_queue_url_not_found_create_fifo(self) -> None:
        """Test that FIFO queue not found raises error even with CREATE strategy."""
        queue_name = "new-queue.fifo"

        # Mock QueueDoesNotExist exception
        queue_not_exist = type("QueueDoesNotExist", (Exception,), {})
        self.client.exceptions.QueueDoesNotExist = queue_not_exist
        self.client.get_queue_url.side_effect = queue_not_exist()

        # Should raise QueueNotFoundError (queue creation not implemented)
        with pytest.raises(QueueNotFoundError) as exc_info:
            self.template._resolve_queue_url(queue_name)

        assert "new-queue.fifo" in str(exc_info.value)

    def test_resolve_queue_url_not_found_fail(self) -> None:
        """Test raising error when queue doesn't exist and strategy is FAIL."""
        queue_name = "missing-queue"
        self.config.queue_not_found_strategy = QueueNotFoundStrategy.FAIL

        # Mock QueueDoesNotExist exception
        queue_not_exist = type("QueueDoesNotExist", (Exception,), {})
        self.client.exceptions.QueueDoesNotExist = queue_not_exist
        self.client.get_queue_url.side_effect = queue_not_exist()

        with pytest.raises(QueueNotFoundError) as exc_info:
            self.template._resolve_queue_url(queue_name)

        assert "missing-queue" in str(exc_info.value)

    def test_send_basic_message(self) -> None:
        """Test sending a basic message."""
        queue_name = "test-queue"
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"
        payload = TestPayload(id=1, message="test")

        self.client.get_queue_url.return_value = {"QueueUrl": queue_url}
        self.client.send_message.return_value = {
            "MessageId": "msg-123",
        }

        result = self.template.send(queue_name, payload)

        assert result.message_id == "msg-123"
        assert result.sequence_number is None

        # Verify send_message was called correctly
        call_args = self.client.send_message.call_args
        assert call_args.kwargs["QueueUrl"] == queue_url
        assert "MessageBody" in call_args.kwargs
        assert "MessageAttributes" in call_args.kwargs

    def test_send_with_delay(self) -> None:
        """Test sending a message with delay."""
        queue_name = "test-queue"
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"
        payload = {"test": "data"}

        self.client.get_queue_url.return_value = {"QueueUrl": queue_url}
        self.client.send_message.return_value = {"MessageId": "msg-123"}

        self.template.send(queue_name, payload, delay_seconds=30)

        call_args = self.client.send_message.call_args
        assert call_args.kwargs["DelaySeconds"] == 30

    def test_send_with_custom_attributes(self) -> None:
        """Test sending a message with custom attributes."""
        queue_name = "test-queue"
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"
        payload = {"test": "data"}
        custom_attrs = {"priority": "high", "version": 1}

        self.client.get_queue_url.return_value = {"QueueUrl": queue_url}
        self.client.send_message.return_value = {"MessageId": "msg-123"}

        self.template.send(queue_name, payload, message_attributes=custom_attrs)

        call_args = self.client.send_message.call_args
        attrs = call_args.kwargs["MessageAttributes"]
        assert "priority" in attrs
        assert attrs["priority"]["StringValue"] == "high"
        assert "version" in attrs
        assert attrs["version"]["StringValue"] == "1"

    def test_send_fifo_without_group_id_raises_error(self) -> None:
        """Test that sending to FIFO queue without group ID raises error."""
        queue_name = "test-queue.fifo"
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue.fifo"
        payload = {"test": "data"}

        self.client.get_queue_url.return_value = {"QueueUrl": queue_url}

        with pytest.raises(ValueError) as exc_info:
            self.template.send(queue_name, payload)

        assert "message_group_id is required" in str(exc_info.value)

    def test_send_fifo_with_group_id(self) -> None:
        """Test sending to FIFO queue with group ID."""
        queue_name = "test-queue.fifo"
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue.fifo"
        payload = {"test": "data"}

        self.client.get_queue_url.return_value = {"QueueUrl": queue_url}
        self.client.send_message.return_value = {
            "MessageId": "msg-123",
            "SequenceNumber": "12345",
        }

        result = self.template.send(
            queue_name, payload, message_group_id="group1", deduplication_id="dedup1"
        )

        assert result.message_id == "msg-123"
        assert result.sequence_number == "12345"

        call_args = self.client.send_message.call_args
        assert call_args.kwargs["MessageGroupId"] == "group1"
        assert call_args.kwargs["MessageDeduplicationId"] == "dedup1"

    def test_send_batch_basic(self) -> None:
        """Test sending a batch of messages."""
        queue_name = "test-queue"
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"
        payloads = [{"id": 1}, {"id": 2}, {"id": 3}]

        self.client.get_queue_url.return_value = {"QueueUrl": queue_url}
        self.client.send_message_batch.return_value = {
            "Successful": [
                {"Id": "0", "MessageId": "msg-1"},
                {"Id": "1", "MessageId": "msg-2"},
                {"Id": "2", "MessageId": "msg-3"},
            ],
            "Failed": [],
        }

        result = self.template.send_batch(queue_name, payloads)

        assert len(result.successful) == 3
        assert len(result.failed) == 0
        assert result.successful[0].message_id == "msg-1"

    def test_send_batch_empty_raises_error(self) -> None:
        """Test that sending empty batch raises error."""
        with pytest.raises(ValueError) as exc_info:
            self.template.send_batch("test-queue", [])

        assert "empty batch" in str(exc_info.value)

    def test_send_batch_too_large_raises_error(self) -> None:
        """Test that sending batch >10 messages raises error."""
        payloads = [{"id": i} for i in range(11)]

        with pytest.raises(ValueError) as exc_info:
            self.template.send_batch("test-queue", payloads)

        assert "exceeds maximum of 10" in str(exc_info.value)

    def test_send_batch_with_failures_throw_strategy(self) -> None:
        """Test batch send with failures and THROW strategy."""
        queue_name = "test-queue"
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"
        payloads = [{"id": 1}, {"id": 2}]

        self.client.get_queue_url.return_value = {"QueueUrl": queue_url}
        self.client.send_message_batch.return_value = {
            "Successful": [{"Id": "0", "MessageId": "msg-1"}],
            "Failed": [
                {
                    "Id": "1",
                    "Code": "InvalidMessageContents",
                    "Message": "Invalid message",
                    "SenderFault": True,
                }
            ],
        }

        with pytest.raises(SerializationError) as exc_info:
            self.template.send_batch(queue_name, payloads)

        assert "Batch send failed" in str(exc_info.value)

    def test_send_batch_with_failures_no_throw_strategy(self) -> None:
        """Test batch send with failures and DO_NOT_THROW strategy."""
        queue_name = "test-queue"
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"
        payloads = [{"id": 1}, {"id": 2}]

        self.config.send_batch_failure_strategy = SendBatchFailureStrategy.DO_NOT_THROW
        self.client.get_queue_url.return_value = {"QueueUrl": queue_url}
        self.client.send_message_batch.return_value = {
            "Successful": [{"Id": "0", "MessageId": "msg-1"}],
            "Failed": [
                {
                    "Id": "1",
                    "Code": "InvalidMessageContents",
                    "Message": "Invalid message",
                    "SenderFault": True,
                }
            ],
        }

        result = self.template.send_batch(queue_name, payloads)

        assert len(result.successful) == 1
        assert len(result.failed) == 1
        assert result.failed[0].code == "InvalidMessageContents"

    def test_send_batch_fifo_without_group_id_raises_error(self) -> None:
        """Test that batch send to FIFO queue without group ID raises error."""
        queue_name = "test-queue.fifo"
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue.fifo"
        payloads = [{"id": 1}, {"id": 2}]

        self.client.get_queue_url.return_value = {"QueueUrl": queue_url}

        with pytest.raises(ValueError) as exc_info:
            self.template.send_batch(queue_name, payloads)

        assert "message_group_id is required" in str(exc_info.value)

    def test_receive_basic(self) -> None:
        """Test receiving messages."""
        queue_name = "test-queue"
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"

        self.client.get_queue_url.return_value = {"QueueUrl": queue_url}
        self.client.receive_message.return_value = {
            "Messages": [
                {
                    "MessageId": "msg-1",
                    "ReceiptHandle": "handle-1",
                    "Body": '{"id": 1, "message": "test"}',
                    "Attributes": {},
                    "MessageAttributes": {"__type__": {"StringValue": "test.TestPayload"}},
                }
            ]
        }

        messages = self.template.receive(queue_name)

        assert len(messages) == 1
        assert messages[0].message_id == "msg-1"
        assert messages[0].receipt_handle == "handle-1"
        assert messages[0].body == {"id": 1, "message": "test"}

    def test_receive_with_parameters(self) -> None:
        """Test receiving messages with custom parameters."""
        queue_name = "test-queue"
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"

        self.client.get_queue_url.return_value = {"QueueUrl": queue_url}
        self.client.receive_message.return_value = {"Messages": []}

        self.template.receive(
            queue_name,
            max_messages=5,
            wait_time_seconds=10,
            visibility_timeout=30,
        )

        call_args = self.client.receive_message.call_args
        assert call_args.kwargs["MaxNumberOfMessages"] == 5
        assert call_args.kwargs["WaitTimeSeconds"] == 10
        assert call_args.kwargs["VisibilityTimeout"] == 30

    def test_receive_empty_queue(self) -> None:
        """Test receiving from empty queue."""
        queue_name = "test-queue"
        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"

        self.client.get_queue_url.return_value = {"QueueUrl": queue_url}
        self.client.receive_message.return_value = {}

        messages = self.template.receive(queue_name)

        assert len(messages) == 0
