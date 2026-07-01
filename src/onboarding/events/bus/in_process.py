from __future__ import annotations

import fnmatch
from collections import defaultdict

from onboarding.domain.events.envelope import DomainEvent
from onboarding.interfaces.event_bus import EventHandler


class InProcessEventBus:
    """Dev/test event bus: synchronous handler dispatch by routing-key pattern."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    async def publish(self, event: DomainEvent) -> None:
        await self.dispatch(event)

    def subscribe(self, pattern: str, handler: EventHandler) -> None:
        self._handlers[pattern].append(handler)

    async def dispatch(self, event: DomainEvent) -> None:
        routing_key = event.envelope.routing_key
        for pattern, handlers in self._handlers.items():
            if fnmatch.fnmatch(routing_key, pattern) or fnmatch.fnmatch(
                event.envelope.event_type.value, pattern
            ):
                for handler in handlers:
                    await handler(event)
