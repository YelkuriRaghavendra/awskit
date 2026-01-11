"""
Message converters for serialization and deserialization.

This module provides the MessageConverter abstract base class and concrete
implementations for converting between Python objects and SQS message formats.
"""

import json
import structlog
from abc import ABC, abstractmethod
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Tuple, Type

from awskit.exceptions import DeserializationError, SerializationError

logger = structlog.get_logger(__name__)


class MessageConverter(ABC):
    """
    Abstract base class for message converters.

    Message converters handle serialization of Python objects to string format
    for sending to SQS, and deserialization of message bodies back to Python
    objects when receiving from SQS.
    """

    @abstractmethod
    def serialize(self, payload: Any) -> Tuple[str, Dict[str, Any]]:
        """
        Serialize a payload to string and return type metadata.

        Args:
            payload: The Python object to serialize

        Returns:
            Tuple of (serialized_body, type_attributes) where:
            - serialized_body is the string representation of the payload
            - type_attributes is a dict of metadata for deserialization

        Raises:
            SerializationError: If serialization fails
        """
        pass

    @abstractmethod
    def deserialize(self, body: str, type_info: Dict[str, Any], target_type: Type[Any]) -> Any:
        """
        Deserialize a message body to the target type.

        Args:
            body: The message body string
            type_info: Type metadata from message attributes
            target_type: The target Python type to deserialize to

        Returns:
            Deserialized Python object of the target type

        Raises:
            DeserializationError: If deserialization fails
        """
        pass


class JsonMessageConverter(MessageConverter):
    """
    Default converter using JSON serialization.

    This converter serializes Python objects to JSON format and includes
    type information in message attributes. It supports:
    - Dataclasses
    - Pydantic models (if pydantic is installed)
    - Standard Python types (dict, list, str, int, float, bool, None)
    - Empty collections and None values
    """

    def serialize(self, payload: Any) -> Tuple[str, Dict[str, Any]]:
        """
        Serialize using JSON with type information.

        Args:
            payload: The Python object to serialize

        Returns:
            Tuple of (json_body, type_attributes)

        Raises:
            SerializationError: If JSON serialization fails
        """
        try:
            # Get type information
            type_name = f"{payload.__class__.__module__}.{payload.__class__.__name__}"
            type_attrs = {"__type__": type_name}

            # Serialize to JSON
            body = json.dumps(payload, default=self._json_encoder)

            return body, type_attrs

        except (TypeError, ValueError) as e:
            logger.error(
                "Failed to serialize payload",
                payload_type=type(payload).__name__,
                error=str(e),
                exc_info=True,
            )
            raise SerializationError(
                f"Failed to serialize payload of type {type(payload).__name__}: {e}"
            ) from e

    def deserialize(self, body: str, type_info: Dict[str, Any], target_type: Type[Any]) -> Any:
        """
        Deserialize from JSON to target type.

        Args:
            body: The JSON message body
            type_info: Type metadata from message attributes
            target_type: The target Python type

        Returns:
            Deserialized Python object

        Raises:
            DeserializationError: If deserialization fails
        """
        try:
            # Parse JSON
            data = json.loads(body)

            # Handle None
            if data is None:
                return None

            # If target type has __annotations__, it's likely a dataclass or Pydantic model
            if hasattr(target_type, "__annotations__"):
                # Check if it's a dataclass
                if is_dataclass(target_type):
                    if isinstance(data, dict):
                        result = target_type(**data)
                        return result
                    else:
                        raise DeserializationError(
                            f"Expected dict for dataclass {target_type.__name__}, got {type(data).__name__}"
                        )

                # Check if it's a Pydantic model
                try:
                    # Try to import pydantic
                    from pydantic import BaseModel

                    if issubclass(target_type, BaseModel):
                        if isinstance(data, dict):
                            result = target_type(**data)
                            return result
                        else:
                            raise DeserializationError(
                                f"Expected dict for Pydantic model {target_type.__name__}, got {type(data).__name__}"
                            )
                except ImportError:
                    # Pydantic not installed, skip this check
                    pass

            # For standard types, return the parsed data directly
            return data

        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse JSON body",
                error=str(e),
                body_preview=body[:100],
                exc_info=True,
            )
            raise DeserializationError(
                f"Failed to parse JSON body: {e}. Body: {body[:100]}"
            ) from e
        except (TypeError, ValueError) as e:
            logger.error(
                "Failed to deserialize",
                target_type=target_type.__name__,
                error=str(e),
                body_preview=body[:100],
                exc_info=True,
            )
            raise DeserializationError(
                f"Failed to deserialize to {target_type.__name__}: {e}. Body: {body[:100]}"
            ) from e

    def _json_encoder(self, obj: Any) -> Any:
        """
        Custom JSON encoder for non-standard types.

        Args:
            obj: Object to encode

        Returns:
            JSON-serializable representation

        Raises:
            TypeError: If object cannot be serialized
        """
        # Handle dataclasses
        if is_dataclass(obj) and not isinstance(obj, type):
            return asdict(obj)

        # Handle Pydantic models
        try:
            from pydantic import BaseModel

            if isinstance(obj, BaseModel):
                return obj.model_dump()
        except ImportError:
            pass

        # Handle sets
        if isinstance(obj, set):
            return list(obj)

        # Cannot serialize this type
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
