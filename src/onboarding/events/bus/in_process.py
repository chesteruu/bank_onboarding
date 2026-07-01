from __future__ import annotations

import fnmatch
from collections import OrderedDict, defaultdict
from uuid import UUID

from onboarding.domain.events.envelope import DomainEvent
from onboarding.interfaces.event_bus import EventHandler


class InProcessEventBus:
    """Dev/test event bus: synchronous handler dispatch by routing-key pattern.

    Delivery is idempotent: each envelope carries a unique ``event_id`` and is
    dispatched at most once, even if published multiple times (at-least-once
    redelivery). A bounded LRU of recent ids keeps memory flat. A real broker
    consumer would back this with a persistent dedup store instead.
    """

    def __init__(self, *, dedup_capacity: int = 4096) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._processed: OrderedDict[UUID, None] = OrderedDict()
        self._dedup_capacity = dedup_capacity

    async def publish(self, event: DomainEvent) -> None:
        await self.dispatch(event)

    def subscribe(self, pattern: str, handler: EventHandler) -> None:
        self._handlers[pattern].append(handler)

    def _already_processed(self, event_id: UUID) -> bool:
        if event_id in self._processed:
            self._processed.move_to_end(event_id)
            return True
        self._processed[event_id] = None
        while len(self._processed) > self._dedup_capacity:
            self._processed.popitem(last=False)
        return False

    async def dispatch(self, event: DomainEvent) -> None:
        if self._already_processed(event.envelope.event_id):
            return
        routing_key = event.envelope.routing_key
        for pattern, handlers in self._handlers.items():
            if fnmatch.fnmatch(routing_key, pattern) or fnmatch.fnmatch(
                event.envelope.event_type.value, pattern
            ):
                for handler in handlers:
                    await handler(event)
