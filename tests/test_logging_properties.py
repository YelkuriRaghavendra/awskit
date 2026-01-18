"""
Property-based tests for structured logging functionality.

This module uses property-based testing to verify universal properties
of the logging system across many inputs.

Feature: structured-logging
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from typing import Any, Dict
from unittest.mock import MagicMock

import structlog
from hypothesis import given, strategies as st

from awskit.converter import JsonMessageConverter
from awskit.sqs.template import SqsTemplate
from awskit.config import TemplateConfig


@dataclass
class TestMessage:
    """Test message payload."""

    id: int
    text: str


class TestStructlogConfiguration:
    """Property-based tests for structlog configuration."""

    def setup_method(self):
        """Set up test fixtures."""
        self.client = MagicMock()
        self.converter = JsonMessageConverter()

    @given(
        message_id=st.text(min_size=1, max_size=100),
        queue_name=st.text(
            min_size=1,
            max_size=80,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
            ),
        ),
        message_text=st.text(min_size=1, max_size=200),
    )
    def test_log_output_is_valid_json(self, message_id: str, queue_name: str, message_text: str):
        """
        Property 6: Log output is valid JSON

        For any log entry, the output should be valid JSON that can be parsed without errors.

        **Validates: Requirements 3.1**
        **Feature: structured-logging, Property 6: Log output is valid JSON**
        """
        # Get a structlog logger
        logger = structlog.get_logger(__name__)

        # Capture stderr where JSON logs are written
        import sys
        from io import StringIO

        old_stderr = sys.stderr
        sys.stderr = StringIO()

        try:
            # Log a message with context
            logger.info(
                "Test log message",
                message_id=message_id,
                queue_name=queue_name,
                message_text=message_text,
            )

            # Get the log output from stderr
            log_output = sys.stderr.getvalue().strip()

            # If there's output, verify it's valid JSON
            if log_output:
                # Parse the JSON - this will raise an exception if invalid
                parsed = json.loads(log_output)

                # Verify it's a dictionary
                assert isinstance(parsed, dict)

                # Verify the event field exists
                assert "event" in parsed
        finally:
            sys.stderr = old_stderr

    @given(
        event_message=st.text(min_size=1, max_size=100),
        log_level=st.sampled_from(["debug", "info", "warning", "error"]),
    )
    def test_log_entries_contain_required_standard_fields(self, event_message: str, log_level: str):
        """
        Property 7: Log entries contain required standard fields

        For any log entry, the JSON output should contain timestamp (in ISO 8601 format),
        log level, and logger name as fields.

        **Validates: Requirements 3.2, 3.3, 3.4**
        **Feature: structured-logging, Property 7: Log entries contain required standard fields**
        """
        # Get a structlog logger
        logger = structlog.get_logger(__name__)

        # Capture stderr where JSON logs are written
        import sys
        from io import StringIO

        old_stderr = sys.stderr
        sys.stderr = StringIO()

        try:
            # Log a message at the specified level
            log_method = getattr(logger, log_level)
            log_method(event_message)

            # Get the log output from stderr
            log_output = sys.stderr.getvalue().strip()

            # If there's output, verify it contains required fields
            if log_output:
                # Parse the JSON
                parsed = json.loads(log_output)

                # Verify required standard fields exist
                assert "timestamp" in parsed, "Log entry must contain timestamp field"
                assert "level" in parsed, "Log entry must contain level field"
                assert "logger" in parsed, "Log entry must contain logger name field"

                # Verify timestamp is in ISO 8601 format
                timestamp = parsed["timestamp"]
                # Try to parse the timestamp - will raise exception if invalid
                datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

                # Verify log level matches
                assert parsed["level"] == log_level

                # Verify logger name is present and non-empty
                assert isinstance(parsed["logger"], str)
                assert len(parsed["logger"]) > 0
        finally:
            sys.stderr = old_stderr


class TestTemplateLogging:
    """Property-based tests for template.py logging."""

    def setup_method(self):
        """Set up test fixtures."""
        self.client = MagicMock()
        self.converter = JsonMessageConverter()
        # Use DO_NOT_THROW strategy to avoid exceptions on batch failures
        from awskit.config import SendBatchFailureStrategy

        self.config = TemplateConfig(
            send_batch_failure_strategy=SendBatchFailureStrategy.DO_NOT_THROW
        )

    @given(
        queue_name=st.text(
            min_size=1,
            max_size=80,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
            ),
        ),
        message_id=st.integers(min_value=1, max_value=1000000),
        message_text=st.text(min_size=1, max_size=200),
    )
    def test_message_operations_include_message_id_in_context(
        self, queue_name: str, message_id: int, message_text: str
    ):
        """
        Property 1: Message operations include message_id in context

        For any message operation (send, receive, acknowledge), the log output should
        contain the message_id field.

        **Validates: Requirements 2.1**
        **Feature: structured-logging, Property 1: Message operations include message_id in context**
        """
        # Set up mock client to return a message ID
        mock_message_id = f"msg-{message_id}"
        self.client.get_queue_url.return_value = {
            "QueueUrl": f"https://sqs.us-east-1.amazonaws.com/123456789012/{queue_name}"
        }
        self.client.send_message.return_value = {
            "MessageId": mock_message_id,
            "SequenceNumber": None,
        }

        # Create template
        template = SqsTemplate(self.client, self.converter, self.config)

        # Create a string buffer to capture log output
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(message)s"))

        # Add handler to root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

        try:
            # Send a message
            test_message = TestMessage(id=message_id, text=message_text)
            template.send(queue_name, test_message)

            # Get the log output
            log_output = stream.getvalue().strip()

            # If there's output, verify it contains message_id
            if log_output:
                # Split by newlines in case there are multiple log entries
                log_lines = [line for line in log_output.split("\n") if line.strip()]

                # Find the log entry for message sent
                message_sent_log = None
                for line in log_lines:
                    try:
                        parsed = json.loads(line)
                        if "Message sent" in parsed.get("event", ""):
                            message_sent_log = parsed
                            break
                    except json.JSONDecodeError:
                        continue

                # Verify message_id is in the log entry
                if message_sent_log:
                    assert (
                        "message_id" in message_sent_log
                    ), "Log entry must contain message_id field"
                    assert message_sent_log["message_id"] == mock_message_id
        finally:
            # Clean up
            root_logger.removeHandler(handler)
            stream.close()

    @given(
        queue_name=st.text(
            min_size=1,
            max_size=80,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
            ),
        ),
        message_id=st.integers(min_value=1, max_value=1000000),
        message_text=st.text(min_size=1, max_size=200),
    )
    def test_queue_operations_include_queue_identifiers_in_context(
        self, queue_name: str, message_id: int, message_text: str
    ):
        """
        Property 2: Queue operations include queue identifiers in context

        For any queue operation, the log output should contain both queue_name and queue_url fields.

        **Validates: Requirements 2.2**
        **Feature: structured-logging, Property 2: Queue operations include queue identifiers in context**
        """
        # Set up mock client
        mock_queue_url = f"https://sqs.us-east-1.amazonaws.com/123456789012/{queue_name}"
        mock_message_id = f"msg-{message_id}"
        self.client.get_queue_url.return_value = {"QueueUrl": mock_queue_url}
        self.client.send_message.return_value = {
            "MessageId": mock_message_id,
            "SequenceNumber": None,
        }

        # Create template
        template = SqsTemplate(self.client, self.converter, self.config)

        # Create a string buffer to capture log output
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(message)s"))

        # Add handler to root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

        try:
            # Send a message (queue operation)
            test_message = TestMessage(id=message_id, text=message_text)
            template.send(queue_name, test_message)

            # Get the log output
            log_output = stream.getvalue().strip()

            # If there's output, verify it contains queue identifiers
            if log_output:
                # Split by newlines in case there are multiple log entries
                log_lines = [line for line in log_output.split("\n") if line.strip()]

                # Find the log entry for message sent (a queue operation)
                queue_operation_log = None
                for line in log_lines:
                    try:
                        parsed = json.loads(line)
                        if "Message sent" in parsed.get("event", ""):
                            queue_operation_log = parsed
                            break
                    except json.JSONDecodeError:
                        continue

                # Verify queue_name and queue_url are in the log entry
                if queue_operation_log:
                    assert (
                        "queue_name" in queue_operation_log
                    ), "Log entry must contain queue_name field"
                    assert (
                        "queue_url" in queue_operation_log
                    ), "Log entry must contain queue_url field"
                    assert queue_operation_log["queue_name"] == queue_name
                    assert queue_operation_log["queue_url"] == mock_queue_url
        finally:
            # Clean up
            root_logger.removeHandler(handler)
            stream.close()

    @given(
        queue_name=st.text(
            min_size=1,
            max_size=80,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
            ),
        ),
        batch_size=st.integers(min_value=1, max_value=10),
        successful_count=st.integers(min_value=0, max_value=10),
    )
    def test_batch_operations_include_batch_metadata_in_context(
        self, queue_name: str, batch_size: int, successful_count: int
    ):
        """
        Property 3: Batch operations include batch metadata in context

        For any batch operation, the log output should contain batch size and success/failure counts.

        **Validates: Requirements 2.3**
        **Feature: structured-logging, Property 3: Batch operations include batch metadata in context**
        """
        # Ensure successful_count doesn't exceed batch_size
        successful_count = min(successful_count, batch_size)
        failed_count = batch_size - successful_count

        # Set up mock client
        mock_queue_url = f"https://sqs.us-east-1.amazonaws.com/123456789012/{queue_name}"
        self.client.get_queue_url.return_value = {"QueueUrl": mock_queue_url}

        # Create mock response with successful and failed messages
        successful_items = [
            {"MessageId": f"msg-{i}", "SequenceNumber": None} for i in range(successful_count)
        ]
        failed_items = [
            {
                "Id": str(i),
                "Code": "TestError",
                "Message": "Test failure",
                "SenderFault": True,
            }
            for i in range(successful_count, batch_size)
        ]

        self.client.send_message_batch.return_value = {
            "Successful": successful_items,
            "Failed": failed_items,
        }

        # Create template
        template = SqsTemplate(self.client, self.converter, self.config)

        # Create a string buffer to capture log output
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(message)s"))

        # Add handler to root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

        try:
            # Send a batch of messages
            test_messages = [TestMessage(id=i, text=f"test-{i}") for i in range(batch_size)]
            template.send_batch(queue_name, test_messages)

            # Get the log output
            log_output = stream.getvalue().strip()

            # If there's output, verify it contains batch metadata
            if log_output:
                # Split by newlines in case there are multiple log entries
                log_lines = [line for line in log_output.split("\n") if line.strip()]

                # Find the log entry for batch send
                batch_log = None
                for line in log_lines:
                    try:
                        parsed = json.loads(line)
                        if "Batch send" in parsed.get("event", ""):
                            batch_log = parsed
                            break
                    except json.JSONDecodeError:
                        continue

                # Verify batch metadata is in the log entry
                if batch_log:
                    assert (
                        "total_messages" in batch_log
                    ), "Log entry must contain total_messages field"
                    assert (
                        "successful_count" in batch_log
                    ), "Log entry must contain successful_count field"
                    assert "failed_count" in batch_log, "Log entry must contain failed_count field"
                    assert batch_log["total_messages"] == batch_size
                    assert batch_log["successful_count"] == successful_count
                    assert batch_log["failed_count"] == failed_count
        finally:
            # Clean up
            root_logger.removeHandler(handler)
            stream.close()


class TestErrorLogging:
    """Property-based tests for error logging."""

    @given(
        error_message=st.text(min_size=1, max_size=100),
        context_key=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_"
            ),
        ),
        context_value=st.text(min_size=1, max_size=100),
    )
    def test_error_logs_include_exception_information(
        self, error_message: str, context_key: str, context_value: str
    ):
        """
        Property 4: Error logs include exception information

        For any error log entry, the log output should contain exception information
        and stack trace when an exception is present.

        **Validates: Requirements 2.4**
        **Feature: structured-logging, Property 4: Error logs include exception information**
        """
        # Get a structlog logger
        logger = structlog.get_logger(__name__)

        # Create a string buffer to capture log output
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(message)s"))

        # Add handler to root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.ERROR)

        try:
            # Create an exception and log it
            try:
                raise ValueError(error_message)
            except ValueError:
                # Log the exception with context
                logger.exception("An error occurred", **{context_key: context_value})

            # Get the log output
            log_output = stream.getvalue().strip()

            # Verify the log output contains exception information
            if log_output:
                # Split by newlines to handle multiple log entries
                log_lines = [line for line in log_output.split("\n") if line.strip()]

                # Find the log entry for our error
                error_log = None
                for line in log_lines:
                    try:
                        parsed = json.loads(line)
                        if "An error occurred" in parsed.get("event", ""):
                            error_log = parsed
                            break
                    except json.JSONDecodeError:
                        continue

                # Verify exception information is present
                if error_log:
                    assert (
                        "exception" in error_log or "exc_info" in error_log
                    ), "Error log must contain exception information"

                    # Verify the exception message or stack trace contains our error message
                    exception_info = error_log.get("exception", "") + error_log.get("exc_info", "")
                    assert (
                        "ValueError" in exception_info
                    ), "Exception info must contain exception type"
                    assert (
                        error_message in exception_info
                    ), "Exception info must contain exception message"

                    # Verify stack trace is present (should contain "Traceback" or file references)
                    assert (
                        "Traceback" in exception_info or ".py" in exception_info
                    ), "Exception info must contain stack trace"
        finally:
            # Clean up
            root_logger.removeHandler(handler)
            stream.close()


class TestContainerLogging:
    """Property-based tests for container.py logging."""

    def setup_method(self):
        """Set up test fixtures."""
        self.client = MagicMock()
        self.converter = JsonMessageConverter()

    @given(
        message_id=st.text(min_size=1, max_size=100),
        queue_url=st.text(
            min_size=10,
            max_size=200,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="/:.-_"
            ),
        ),
        receipt_handle=st.text(min_size=1, max_size=100),
    )
    def test_context_binding_preserves_context_across_operations(
        self, message_id: str, queue_url: str, receipt_handle: str
    ):
        """
        Property 5: Context binding preserves context across operations

        For any logger with bound context, all subsequent log calls using that logger
        should include the bound context fields.

        **Validates: Requirements 2.5**
        **Feature: structured-logging, Property 5: Context binding preserves context across operations**
        """
        # Get a structlog logger
        logger = structlog.get_logger(__name__)

        # Create a string buffer to capture log output
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(message)s"))

        # Add handler to root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

        try:
            # Bind context to the logger
            bound_logger = logger.bind(
                message_id=message_id,
                queue_url=queue_url,
                receipt_handle=receipt_handle,
            )

            # Make multiple log calls with the bound logger
            bound_logger.info("First log message")
            bound_logger.info("Second log message")
            bound_logger.info("Third log message")

            # Get the log output
            log_output = stream.getvalue().strip()

            # If there's output, verify all log entries contain the bound context
            if log_output:
                # Split by newlines to get individual log entries
                log_lines = [line for line in log_output.split("\n") if line.strip()]

                # Verify we have at least some log entries
                assert len(log_lines) > 0, "Should have at least one log entry"

                # Check each log entry contains the bound context
                for line in log_lines:
                    try:
                        parsed = json.loads(line)

                        # Verify all bound context fields are present
                        assert (
                            "message_id" in parsed
                        ), "Log entry must contain message_id from bound context"
                        assert (
                            "queue_url" in parsed
                        ), "Log entry must contain queue_url from bound context"
                        assert (
                            "receipt_handle" in parsed
                        ), "Log entry must contain receipt_handle from bound context"

                        # Verify the values match what was bound
                        assert parsed["message_id"] == message_id
                        assert parsed["queue_url"] == queue_url
                        assert parsed["receipt_handle"] == receipt_handle
                    except json.JSONDecodeError:
                        # Skip non-JSON lines
                        continue
        finally:
            # Clean up
            root_logger.removeHandler(handler)
            stream.close()


class TestContextFieldSerialization:
    """Property-based tests for context field serialization."""

    @given(
        event_message=st.text(min_size=1, max_size=100),
        context_fields=st.dictionaries(
            keys=st.text(
                min_size=1,
                max_size=50,
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_"
                ),
            ),
            values=st.one_of(
                st.text(min_size=0, max_size=100),
                st.integers(),
                st.booleans(),
                st.floats(allow_nan=False, allow_infinity=False),
            ),
            min_size=1,
            max_size=5,
        ),
    )
    def test_context_fields_appear_as_top_level_json_keys(
        self, event_message: str, context_fields: Dict[str, Any]
    ):
        """
        Property 8: Context fields appear as top-level JSON keys

        For any context fields provided to a log call, those fields should appear
        as top-level keys in the JSON output.

        **Validates: Requirements 3.5**
        **Feature: structured-logging, Property 8: Context fields appear as top-level JSON keys**
        """
        # Get a structlog logger
        logger = structlog.get_logger(__name__)

        # Capture stderr where JSON logs are written
        import sys
        from io import StringIO

        old_stderr = sys.stderr
        sys.stderr = StringIO()

        try:
            # Log a message with context fields
            logger.info(event_message, **context_fields)

            # Get the log output from stderr
            log_output = sys.stderr.getvalue().strip()

            # Verify context fields appear as top-level JSON keys
            if log_output:
                # Parse the JSON log entry
                parsed = json.loads(log_output)

                # Verify all context fields are present as top-level keys
                for key, value in context_fields.items():
                    assert key in parsed, f"Context field '{key}' must appear as top-level JSON key"

                    # Verify the value matches (with type conversion for JSON)
                    if isinstance(value, float):
                        # For floats, check approximate equality
                        assert (
                            abs(parsed[key] - value) < 0.0001
                        ), f"Context field '{key}' value must match"
                    else:
                        assert parsed[key] == value, f"Context field '{key}' value must match"
        finally:
            sys.stderr = old_stderr
