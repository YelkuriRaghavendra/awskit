"""
SqsTemplate for sending and receiving messages.

This module provides the high-level SqsTemplate class for interacting with
SQS queues, including sending messages, batch sending, and receiving messages.
"""

import structlog
from typing import Any, Dict, List, Optional

from awskit.config import QueueNotFoundStrategy, SendBatchFailureStrategy, TemplateConfig
from awskit.converter import MessageConverter
from awskit.exceptions import QueueNotFoundError, SerializationError
from awskit.sqs.models import BatchSendResult, Message, SendFailure, SendResult

logger = structlog.get_logger(__name__)


class SqsTemplate:
    """
    High-level template for sending messages to SQS.

    This class provides a simplified interface for interacting with SQS queues,
    handling message serialization, queue URL resolution, and error handling.

    Attributes:
        client: boto3 SQS client
        converter: MessageConverter for serialization/deserialization
        config: TemplateConfig with behavior settings
    """

    def __init__(
        self,
        client: Any,
        converter: MessageConverter,
        config: Optional[TemplateConfig] = None,
    ):
        """
        Initialize SqsTemplate.

        Args:
            client: boto3 SQS client
            converter: MessageConverter for payload serialization
            config: Optional TemplateConfig (uses defaults if not provided)
        """
        self.client = client
        self.converter = converter
        self.config = config or TemplateConfig()
        self._queue_url_cache: Dict[str, str] = {}

    def _resolve_queue_url(self, queue: str) -> str:
        """
        Resolve queue name or URL to a queue URL.

        Args:
            queue: Queue name or URL

        Returns:
            Queue URL

        Raises:
            QueueNotFoundError: If queue doesn't exist and strategy is FAIL
        """
        # If it looks like a URL, return it directly
        if queue.startswith("https://") or queue.startswith("http://"):
            return queue
        if queue in self._queue_url_cache:
            return self._queue_url_cache[queue]
        try:
            response = self.client.get_queue_url(QueueName=queue)
            queue_url: str = response["QueueUrl"]
            self._queue_url_cache[queue] = queue_url
            return queue_url
        except self.client.exceptions.QueueDoesNotExist:
            raise QueueNotFoundError(f"Queue not found: {queue}")

    def send(
        self,
        queue: str,
        payload: Any,
        *,
        delay_seconds: int = 0,
        message_attributes: Optional[Dict[str, Any]] = None,
        message_group_id: Optional[str] = None,
        deduplication_id: Optional[str] = None,
    ) -> SendResult:
        """
        Send a single message to a queue.

        Args:
            queue: Queue name or URL
            payload: Message payload (will be serialized)
            delay_seconds: Delay before message becomes visible (0-900 seconds)
            message_attributes: Custom message attributes
            message_group_id: Message group ID for FIFO queues (required for FIFO)
            deduplication_id: Deduplication ID for FIFO queues (optional)

        Returns:
            SendResult with message ID and sequence number

        Raises:
            QueueNotFoundError: If queue doesn't exist and strategy is FAIL
            SerializationError: If payload serialization fails
            ValueError: If message_group_id is missing for FIFO queue
        """
        # Resolve queue URL
        queue_url = self._resolve_queue_url(queue)
        is_fifo = queue_url.endswith(".fifo")
        if is_fifo and not message_group_id:
            raise ValueError(f"message_group_id is required for FIFO queue: {queue}")
        body, type_attrs = self.converter.serialize(payload)
        attrs = self._build_message_attributes(type_attrs, message_attributes)
        send_params: Dict[str, Any] = {
            "QueueUrl": queue_url,
            "MessageBody": body,
        }
        if attrs:
            send_params["MessageAttributes"] = attrs
        if delay_seconds > 0:
            send_params["DelaySeconds"] = delay_seconds
        if is_fifo:
            if message_group_id:
                send_params["MessageGroupId"] = message_group_id
            if deduplication_id:
                send_params["MessageDeduplicationId"] = deduplication_id
        response = self.client.send_message(**send_params)
        message_id = response["MessageId"]
        sequence_number = response.get("SequenceNumber")
        logger.info(
            "Message sent to queue",
            message_id=message_id,
            queue_name=queue,
            queue_url=queue_url,
            is_fifo=is_fifo,
            delay_seconds=delay_seconds,
            message_group_id=message_group_id,
            sequence_number=sequence_number,
        )
        return SendResult(
            message_id=message_id,
            sequence_number=sequence_number,
        )

    def _build_message_attributes(
        self,
        type_attrs: Dict[str, Any],
        custom_attrs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Build SQS message attributes from type info and custom attributes.

        Args:
            type_attrs: Type information attributes
            custom_attrs: Custom message attributes

        Returns:
            Dictionary of SQS message attributes
        """
        attrs: Dict[str, Any] = {}
        for key, value in type_attrs.items():
            attrs[key] = {"DataType": "String", "StringValue": str(value)}
        if custom_attrs:
            for key, value in custom_attrs.items():
                if isinstance(value, str):
                    attrs[key] = {"DataType": "String", "StringValue": value}
                elif isinstance(value, (int, float)):
                    attrs[key] = {"DataType": "Number", "StringValue": str(value)}
                elif isinstance(value, bytes):
                    attrs[key] = {"DataType": "Binary", "BinaryValue": value}
                else:
                    attrs[key] = {"DataType": "String", "StringValue": str(value)}
        return attrs

    def send_batch(
        self,
        queue: str,
        payloads: List[Any],
        **kwargs: Any,
    ) -> BatchSendResult:
        """
        Send multiple messages in a batch.

        Args:
            queue: Queue name or URL
            payloads: List of message payloads
            **kwargs: Additional parameters passed to each message (delay_seconds, etc.)

        Returns:
            BatchSendResult with successful and failed messages

        Raises:
            QueueNotFoundError: If queue doesn't exist and strategy is FAIL
            SerializationError: If payload serialization fails
            ValueError: If batch is empty or too large (>10 messages)
        """
        if not payloads:
            raise ValueError("Cannot send empty batch")

        if len(payloads) > 10:
            raise ValueError(f"Batch size {len(payloads)} exceeds maximum of 10")

        # Resolve queue URL
        queue_url = self._resolve_queue_url(queue)

        # Check if this is a FIFO queue
        is_fifo = queue_url.endswith(".fifo")

        # Build batch entries
        entries = []
        for i, payload in enumerate(payloads):
            # Serialize payload
            body, type_attrs = self.converter.serialize(payload)

            # Build message attributes
            attrs = self._build_message_attributes(type_attrs, kwargs.get("message_attributes"))

            # Build entry
            entry: Dict[str, Any] = {
                "Id": str(i),
                "MessageBody": body,
            }

            if attrs:
                entry["MessageAttributes"] = attrs

            if kwargs.get("delay_seconds", 0) > 0:
                entry["DelaySeconds"] = kwargs["delay_seconds"]

            if is_fifo:
                # For FIFO, each message needs a group ID
                message_group_id = kwargs.get("message_group_id")
                if not message_group_id:
                    raise ValueError(f"message_group_id is required for FIFO queue: {queue}")
                entry["MessageGroupId"] = message_group_id

                # Optional deduplication ID
                if "deduplication_id" in kwargs:
                    entry["MessageDeduplicationId"] = kwargs["deduplication_id"]

            entries.append(entry)

        # Send batch
        response = self.client.send_message_batch(QueueUrl=queue_url, Entries=entries)

        # Process results
        successful = [
            SendResult(
                message_id=item["MessageId"],
                sequence_number=item.get("SequenceNumber"),
            )
            for item in response.get("Successful", [])
        ]

        failed = [
            SendFailure(
                id=item["Id"],
                code=item["Code"],
                message=item["Message"],
                sender_fault=item["SenderFault"],
            )
            for item in response.get("Failed", [])
        ]

        result = BatchSendResult(successful=successful, failed=failed)

        # Log batch send results with context
        logger.info(
            "Batch send to queue completed",
            queue_name=queue,
            queue_url=queue_url,
            is_fifo=is_fifo,
            total_messages=len(payloads),
            successful_count=len(successful),
            failed_count=len(failed),
            message_ids=[s.message_id for s in successful],
        )

        if failed:
            logger.warning(
                "Batch send failures",
                queue_name=queue,
                queue_url=queue_url,
                failed_count=len(failed),
                failures=[
                    {
                        "id": f.id,
                        "code": f.code,
                        "message": f.message,
                        "sender_fault": f.sender_fault,
                    }
                    for f in failed
                ],
            )

        if failed and self.config.send_batch_failure_strategy == SendBatchFailureStrategy.THROW:
            raise SerializationError(f"Batch send failed for {len(failed)} message(s): {failed}")
        return result

    def receive(
        self,
        queue: str,
        *,
        max_messages: int = 1,
        wait_time_seconds: int = 0,
        visibility_timeout: Optional[int] = None,
    ) -> List[Message]:
        """
        Receive messages from a queue (for testing/manual use).

        Args:
            queue: Queue name or URL
            max_messages: Maximum number of messages to receive (1-10)
            wait_time_seconds: Long polling wait time (0-20 seconds)
            visibility_timeout: Custom visibility timeout (seconds)

        Returns:
            List of received messages with deserialized payloads

        Raises:
            QueueNotFoundError: If queue doesn't exist and strategy is FAIL
        """
        queue_url = self._resolve_queue_url(queue)
        receive_params: Dict[str, Any] = {
            "QueueUrl": queue_url,
            "MaxNumberOfMessages": max_messages,
            "WaitTimeSeconds": wait_time_seconds,
            "MessageAttributeNames": ["All"],
            "AttributeNames": ["All"],
        }
        if visibility_timeout is not None:
            receive_params["VisibilityTimeout"] = visibility_timeout
        response = self.client.receive_message(**receive_params)
        messages = []
        for msg in response.get("Messages", []):
            type_info = {}
            msg_attrs = msg.get("MessageAttributes", {})
            for key, value in msg_attrs.items():
                if key.startswith("__"):
                    type_info[key] = value.get("StringValue", "")
            try:
                body = self.converter.deserialize(msg["Body"], type_info, dict)
            except Exception:
                body = msg["Body"]
            messages.append(
                Message(
                    message_id=msg["MessageId"],
                    receipt_handle=msg["ReceiptHandle"],
                    body=body,
                    attributes=msg.get("Attributes", {}),
                    message_attributes=msg_attrs,
                    queue_url=queue_url,
                )
            )
        logger.info(
            "Received messages from queue",
            queue_name=queue,
            queue_url=queue_url,
            message_count=len(messages),
            message_ids=[m.message_id for m in messages],
            max_messages=max_messages,
            wait_time_seconds=wait_time_seconds,
        )
        return messages
