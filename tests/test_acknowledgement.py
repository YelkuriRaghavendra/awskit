"""
Tests for the AcknowledgementProcessor.

This module contains unit tests for the acknowledgement processor,
verifying batching, ordering, error handling, and immediate acknowledgement.
"""

import time
from unittest.mock import MagicMock

from awskit.sqs.acknowledgement import AcknowledgementProcessor
from awskit.config import AcknowledgementConfig, AcknowledgementOrdering


class TestAcknowledgementProcessor:
    """Tests for AcknowledgementProcessor."""

    def test_immediate_acknowledgement(self):
        """Test immediate acknowledgement when interval=0 and threshold=0."""
        client = MagicMock()
        config = AcknowledgementConfig(interval_seconds=0, threshold=0)
        processor = AcknowledgementProcessor(client, config)

        processor.acknowledge("https://queue.url", "receipt-handle-1")

        # Should call delete_message immediately
        client.delete_message.assert_called_once_with(
            QueueUrl="https://queue.url", ReceiptHandle="receipt-handle-1"
        )

    def test_batched_acknowledgement_by_threshold(self):
        """Test batched acknowledgement triggered by threshold."""
        client = MagicMock()
        config = AcknowledgementConfig(interval_seconds=10.0, threshold=3)
        processor = AcknowledgementProcessor(client, config)

        # Queue 3 messages (should trigger batch)
        processor.acknowledge("https://queue.url", "receipt-1")
        processor.acknowledge("https://queue.url", "receipt-2")
        processor.acknowledge("https://queue.url", "receipt-3")

        # Give worker thread time to process
        time.sleep(0.5)

        # Should call delete_message_batch
        assert client.delete_message_batch.call_count >= 1

    def test_batched_acknowledgement_by_interval(self):
        """Test batched acknowledgement triggered by interval."""
        client = MagicMock()
        config = AcknowledgementConfig(interval_seconds=0.5, threshold=100)
        processor = AcknowledgementProcessor(client, config)

        # Queue 2 messages (below threshold)
        processor.acknowledge("https://queue.url", "receipt-1")
        processor.acknowledge("https://queue.url", "receipt-2")

        # Wait for interval to trigger
        time.sleep(1.0)

        # Should call delete_message_batch
        assert client.delete_message_batch.call_count >= 1

    def test_acknowledge_batch_immediate(self):
        """Test acknowledge_batch bypasses batching."""
        client = MagicMock()
        config = AcknowledgementConfig(interval_seconds=10.0, threshold=10)
        processor = AcknowledgementProcessor(client, config)

        processor.acknowledge_batch(
            "https://queue.url", ["receipt-1", "receipt-2", "receipt-3"]
        )

        # Should call delete_message_batch immediately
        client.delete_message_batch.assert_called_once()

    def test_flush_pending_acknowledgements(self):
        """Test flush processes all pending acknowledgements."""
        client = MagicMock()
        config = AcknowledgementConfig(interval_seconds=100.0, threshold=100)
        processor = AcknowledgementProcessor(client, config)

        # Queue messages
        processor.acknowledge("https://queue.url", "receipt-1")
        processor.acknowledge("https://queue.url", "receipt-2")

        # Flush should process them immediately
        processor.flush()

        # Should call delete_message_batch
        assert client.delete_message_batch.call_count >= 1

    def test_ordered_acknowledgement_fifo(self):
        """Test ordered acknowledgement for FIFO queues."""
        client = MagicMock()
        config = AcknowledgementConfig(
            interval_seconds=0.5,
            threshold=10,
            ordering=AcknowledgementOrdering.ORDERED,
        )
        processor = AcknowledgementProcessor(client, config)

        # Queue messages in order
        processor.acknowledge("https://queue.url.fifo", "receipt-1")
        processor.acknowledge("https://queue.url.fifo", "receipt-2")
        processor.acknowledge("https://queue.url.fifo", "receipt-3")

        # Wait for interval
        time.sleep(1.0)

        # Should call delete_message_batch with messages in order
        assert client.delete_message_batch.call_count >= 1

    def test_error_handling_single_message(self):
        """Test error handling for single message deletion."""
        client = MagicMock()
        client.delete_message.side_effect = Exception("SQS error")
        config = AcknowledgementConfig(interval_seconds=0, threshold=0)
        processor = AcknowledgementProcessor(client, config)

        # Should not raise exception
        processor.acknowledge("https://queue.url", "receipt-1")

        # Should have attempted to delete
        client.delete_message.assert_called_once()

    def test_error_handling_batch(self):
        """Test error handling for batch deletion."""
        client = MagicMock()
        client.delete_message_batch.side_effect = Exception("SQS error")
        config = AcknowledgementConfig(interval_seconds=0, threshold=0)
        processor = AcknowledgementProcessor(client, config)

        # Should not raise exception
        processor.acknowledge_batch("https://queue.url", ["receipt-1", "receipt-2"])

        # Should have attempted to delete
        client.delete_message_batch.assert_called_once()

    def test_shutdown_flushes_pending(self):
        """Test shutdown flushes all pending acknowledgements."""
        client = MagicMock()
        config = AcknowledgementConfig(interval_seconds=100.0, threshold=100)
        processor = AcknowledgementProcessor(client, config)

        # Queue messages
        processor.acknowledge("https://queue.url", "receipt-1")
        processor.acknowledge("https://queue.url", "receipt-2")

        # Shutdown should flush
        processor.shutdown(timeout_seconds=5)

        # Should call delete_message_batch
        assert client.delete_message_batch.call_count >= 1

    def test_batch_size_limit(self):
        """Test that batches are split when exceeding SQS limit of 10."""
        client = MagicMock()
        config = AcknowledgementConfig(interval_seconds=0, threshold=0)
        processor = AcknowledgementProcessor(client, config)

        # Send 15 messages (should be split into 2 batches)
        handles = [f"receipt-{i}" for i in range(15)]
        processor.acknowledge_batch("https://queue.url", handles)

        # Should call delete_message_batch twice (10 + 5)
        assert client.delete_message_batch.call_count == 2

    def test_empty_batch_does_nothing(self):
        """Test that empty batch doesn't make API calls."""
        client = MagicMock()
        config = AcknowledgementConfig(interval_seconds=0, threshold=0)
        processor = AcknowledgementProcessor(client, config)

        processor.acknowledge_batch("https://queue.url", [])

        # Should not call delete_message_batch
        client.delete_message_batch.assert_not_called()

    def test_multiple_queues_batching(self):
        """Test batching works correctly with multiple queues."""
        client = MagicMock()
        config = AcknowledgementConfig(interval_seconds=0.5, threshold=10)
        processor = AcknowledgementProcessor(client, config)

        # Queue messages to different queues
        processor.acknowledge("https://queue1.url", "receipt-1")
        processor.acknowledge("https://queue2.url", "receipt-2")
        processor.acknowledge("https://queue1.url", "receipt-3")

        # Wait for interval
        time.sleep(1.0)

        # Should call delete_message_batch for each queue
        assert client.delete_message_batch.call_count >= 2
