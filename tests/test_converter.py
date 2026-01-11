"""
Unit tests for message converters.
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest

from awskit.converter import JsonMessageConverter
from awskit.exceptions import DeserializationError


@dataclass
class TestMessage:
    """Test dataclass for serialization."""

    id: int
    name: str
    tags: List[str]
    metadata: Optional[Dict[str, Any]] = None


class TestJsonMessageConverter:
    """Tests for JsonMessageConverter."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.converter = JsonMessageConverter()

    def test_serialize_dict(self) -> None:
        """Test serializing a dictionary."""
        payload = {"key": "value", "number": 42}
        body, type_attrs = self.converter.serialize(payload)

        assert isinstance(body, str)
        assert json.loads(body) == payload
        assert "__type__" in type_attrs
        assert "builtins.dict" in type_attrs["__type__"]

    def test_serialize_list(self) -> None:
        """Test serializing a list."""
        payload = [1, 2, 3, "four"]
        body, type_attrs = self.converter.serialize(payload)

        assert isinstance(body, str)
        assert json.loads(body) == payload
        assert "__type__" in type_attrs

    def test_serialize_dataclass(self) -> None:
        """Test serializing a dataclass."""
        payload = TestMessage(id=1, name="test", tags=["a", "b"])
        body, type_attrs = self.converter.serialize(payload)

        assert isinstance(body, str)
        data = json.loads(body)
        assert data["id"] == 1
        assert data["name"] == "test"
        assert data["tags"] == ["a", "b"]
        assert "__type__" in type_attrs

    def test_serialize_none(self) -> None:
        """Test serializing None."""
        payload = None
        body, type_attrs = self.converter.serialize(payload)

        assert body == "null"
        assert "__type__" in type_attrs

    def test_serialize_empty_list(self) -> None:
        """Test serializing an empty list."""
        payload: List[str] = []
        body, type_attrs = self.converter.serialize(payload)

        assert json.loads(body) == []
        assert "__type__" in type_attrs

    def test_serialize_empty_dict(self) -> None:
        """Test serializing an empty dictionary."""
        payload: Dict[str, Any] = {}
        body, type_attrs = self.converter.serialize(payload)

        assert json.loads(body) == {}
        assert "__type__" in type_attrs

    def test_deserialize_dict(self) -> None:
        """Test deserializing to a dictionary."""
        body = '{"key": "value", "number": 42}'
        type_info = {"__type__": "builtins.dict"}
        result = self.converter.deserialize(body, type_info, dict)

        assert result == {"key": "value", "number": 42}

    def test_deserialize_list(self) -> None:
        """Test deserializing to a list."""
        body = '[1, 2, 3, "four"]'
        type_info = {"__type__": "builtins.list"}
        result = self.converter.deserialize(body, type_info, list)

        assert result == [1, 2, 3, "four"]

    def test_deserialize_dataclass(self) -> None:
        """Test deserializing to a dataclass."""
        body = '{"id": 1, "name": "test", "tags": ["a", "b"], "metadata": null}'
        type_info = {"__type__": "test_converter.TestMessage"}
        result = self.converter.deserialize(body, type_info, TestMessage)

        assert isinstance(result, TestMessage)
        assert result.id == 1
        assert result.name == "test"
        assert result.tags == ["a", "b"]
        assert result.metadata is None

    def test_deserialize_none(self) -> None:
        """Test deserializing None."""
        body = "null"
        type_info = {"__type__": "builtins.NoneType"}
        result = self.converter.deserialize(body, type_info, type(None))

        assert result is None

    def test_deserialize_empty_list(self) -> None:
        """Test deserializing an empty list."""
        body = "[]"
        type_info = {"__type__": "builtins.list"}
        result = self.converter.deserialize(body, type_info, list)

        assert result == []

    def test_deserialize_empty_dict(self) -> None:
        """Test deserializing an empty dictionary."""
        body = "{}"
        type_info = {"__type__": "builtins.dict"}
        result = self.converter.deserialize(body, type_info, dict)

        assert result == {}

    def test_deserialize_invalid_json(self) -> None:
        """Test deserializing invalid JSON raises error."""
        body = "{invalid json"
        type_info = {"__type__": "builtins.dict"}

        with pytest.raises(DeserializationError) as exc_info:
            self.converter.deserialize(body, type_info, dict)

        assert "Failed to parse JSON" in str(exc_info.value)

    def test_round_trip_dict(self) -> None:
        """Test round-trip serialization and deserialization of dict."""
        original = {"key": "value", "number": 42, "nested": {"a": 1}}
        body, type_attrs = self.converter.serialize(original)
        result = self.converter.deserialize(body, type_attrs, dict)

        assert result == original

    def test_round_trip_dataclass(self) -> None:
        """Test round-trip serialization and deserialization of dataclass."""
        original = TestMessage(
            id=123, name="test message", tags=["tag1", "tag2"], metadata={"key": "value"}
        )
        body, type_attrs = self.converter.serialize(original)
        result = self.converter.deserialize(body, type_attrs, TestMessage)

        assert result == original

    def test_round_trip_none(self) -> None:
        """Test round-trip serialization and deserialization of None."""
        original = None
        body, type_attrs = self.converter.serialize(original)
        result = self.converter.deserialize(body, type_attrs, type(None))

        assert result is original

    def test_round_trip_empty_collections(self) -> None:
        """Test round-trip serialization of empty collections."""
        # Empty list
        empty_list: List[str] = []
        body, type_attrs = self.converter.serialize(empty_list)
        result = self.converter.deserialize(body, type_attrs, list)
        assert result == []

        # Empty dict
        empty_dict: Dict[str, Any] = {}
        body, type_attrs = self.converter.serialize(empty_dict)
        result = self.converter.deserialize(body, type_attrs, dict)
        assert result == {}
