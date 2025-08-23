from __future__ import annotations

import threading
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class Event:
    timestamp: str
    region: str
    service: str
    resource: str
    action: str
    arn: str | None
    meta: dict[str, object]


class Reporter:
    def __init__(self) -> None:
        self._events: list[Event] = []
        self._events_lock = threading.Lock()

    def record(
        self,
        region: str,
        service: str,
        resource: str,
        action: str,
        arn: str | None = None,
        meta: dict | None = None,
    ) -> None:
        evt = Event(
            timestamp=datetime.now(UTC).isoformat(),
            region=region,
            service=service,
            resource=resource,
            action=action,
            arn=arn,
            meta=meta or {},
        )
        with self._events_lock:
            self._events.append(evt)

    def snapshot(self) -> list[Event]:
        # Returns a thread-safe copy
        with self._events_lock:
            return list(self._events)

    def iter(self) -> Iterable[Event]:
        # Cheap iteration over a stable snapshot
        return iter(self.snapshot())

    def to_dicts(self) -> list[dict]:
        return [asdict(e) for e in self.iter()]

    def clear(self) -> None:
        with self._events_lock:
            self._events.clear()

    def count(self) -> int:
        with self._events_lock:
            return len(self._events)


# Lazy singleton
_reporter: Reporter | None = None


def get_reporter() -> Reporter:
    global _reporter
    if _reporter is None:
        _reporter = Reporter()
    return _reporter


class Sinks:
    def __init__(self):
        self.events = get_reporter()

    ...  # export events details in various outputs like print (stdout), logging (based on logging config), csv, etc.
