from collections.abc import Awaitable, Callable
from typing import Protocol

from onboarding.domain.events.envelope import DomainEvent

EventHandler = Callable[[DomainEvent], Awaitable[None]]


class IEventBus(Protocol):
    async def publish(self, event: DomainEvent) -> None: ...

    def subscribe(self, pattern: str, handler: EventHandler) -> None: ...

    async def dispatch(self, event: DomainEvent) -> None: ...
