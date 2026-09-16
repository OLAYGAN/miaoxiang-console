"""Small in-process event bus for logs and task snapshots."""

import inspect
from collections import deque
from collections.abc import Callable
from typing import Any


EventSubscriber = Callable[[dict[str, Any]], None]


class EventBus:
    def __init__(self, history_limit: int = 1000) -> None:
        self._subscribers: set[EventSubscriber] = set()
        self._history: deque[dict[str, Any]] = deque(maxlen=history_limit)

    def subscribe(self, subscriber: EventSubscriber) -> Callable[[], None]:
        self._subscribers.add(subscriber)

        def unsubscribe() -> None:
            self._subscribers.discard(subscriber)

        return unsubscribe

    async def publish(self, event: dict[str, Any]) -> None:
        self._history.append(event)
        for subscriber in list(self._subscribers):
            try:
                result = subscriber(event)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                continue

    def recent(self) -> list[dict[str, Any]]:
        return list(self._history)
