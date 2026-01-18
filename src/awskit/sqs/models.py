"""
Data models for the SQS integration library.

This module defines all data models used throughout the library, including
messages, send results, and acknowledgement handles.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from awskit.sqs.acknowledgement import AcknowledgementProcessor


@dataclass
class Message:
    """
    Represents an SQS message with deserialized payload.

    Attributes:
        message_id: Unique identifier for the message
        receipt_handle: Handle for acknowledging/deleting the message
        body: Deserialized message payload
        attributes: System attributes from SQS
        message_attributes: Custom message attributes
        queue_url: URL of the queue the message came from
    """

    message_id: str
    receipt_handle: str
    body: Any
    attributes: dict[str, Any]
    message_attributes: dict[str, Any]
    queue_url: str


@dataclass
class SendResult:
    """
    Result of sending a single message.

    Attributes:
        message_id: Unique identifier assigned by SQS
        sequence_number: Sequence number for FIFO queues (None for standard queues)
    """

    message_id: str
    sequence_number: Optional[str] = None


@dataclass
class SendFailure:
    """
    Details of a failed message send in a batch operation.

    Attributes:
        id: Client-provided ID for the failed message
        code: Error code from SQS
        message: Error message describing the failure
        sender_fault: Whether the failure was due to sender error
    """

    id: str
    code: str
    message: str
    sender_fault: bool


@dataclass
class BatchSendResult:
    """
    Result of sending a batch of messages.

    Attributes:
        successful: List of successfully sent messages
        failed: List of failed message sends with error details
    """

    successful: list[SendResult]
    failed: list[SendFailure]


@dataclass
class Acknowledgement:
    """
    Handle for manual message acknowledgement.

    This object is provided to listeners when acknowledgement_mode is MANUAL,
    allowing the listener to explicitly control when the message is deleted
    from the queue.

    Attributes:
        queue_url: URL of the queue the message came from
        receipt_handle: Handle for deleting the message
        processor: AcknowledgementProcessor to use for deletion
    """

    queue_url: str
    receipt_handle: str
    processor: "AcknowledgementProcessor"

    def acknowledge(self) -> None:
        """
        Acknowledge (delete) this message from the queue.

        This method queues the message for acknowledgement, which may be
        batched with other acknowledgements based on the configured
        acknowledgement settings.
        """
        self.processor.acknowledge(self.queue_url, self.receipt_handle)
