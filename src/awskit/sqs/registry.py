"""
Listener registry for storing and managing message listener functions.

This module provides a singleton registry that stores listener functions
and their associated configurations, enabling the MessageListenerContainer
to discover and invoke registered listeners.
"""

from typing import Any, Callable, Dict, List, Tuple

from awskit.config import ListenerConfig


class ListenerRegistry:
    """
    Singleton registry for storing listener functions and configurations.

    This registry maintains a mapping of listener functions to their
    configurations, allowing the MessageListenerContainer to discover
    all registered listeners at runtime.

    The registry is implemented as a class with class-level storage,
    providing a simple singleton pattern without requiring explicit
    instance management.
    """

    _listeners: Dict[Callable[..., Any], ListenerConfig] = {}
    _registration_disabled: bool = False

    @classmethod
    def register(cls, func: Callable[..., Any], config: ListenerConfig) -> None:
        """
        Register a listener function with its configuration.

        Args:
            func: The listener function to register
            config: Configuration for the listener
        """
        if cls._registration_disabled:
            return
        cls._listeners[func] = config

    @classmethod
    def get_listeners(cls) -> List[Tuple[Callable[..., Any], ListenerConfig]]:
        """
        Get all registered listeners and their configurations.

        Returns:
            List of tuples containing (listener_function, listener_config)
        """
        return list(cls._listeners.items())

    @classmethod
    def clear(cls) -> None:
        """
        Clear all registered listeners.

        This method is primarily useful for testing to ensure a clean
        state between test runs.
        """
        cls._listeners.clear()

    @classmethod
    def get_listener_config(cls, func: Callable[..., Any]) -> ListenerConfig:
        """
        Get the configuration for a specific listener function.

        Args:
            func: The listener function to look up

        Returns:
            The ListenerConfig for the function

        Raises:
            KeyError: If the function is not registered
        """
        return cls._listeners[func]
