import logging
from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)


class EventBus:
    """Asyncio-based publish/subscribe event bus with per-handler error isolation."""

    def __init__(self) -> None:
        self._handlers: dict[type, list[Callable]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: Callable[..., Coroutine]) -> None:
        """Register an async handler for a given event type."""
        self._handlers[event_type].append(handler)

    async def publish(self, event: Any) -> None:
        """Publish an event to all subscribed handlers.

        Each handler is called independently; an exception in one handler
        does not prevent other handlers from running.
        """
        event_type = type(event)
        handlers = self._handlers.get(event_type, [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "Event handler %s raised an exception for event %s",
                    handler,
                    event_type.__name__,
                )
