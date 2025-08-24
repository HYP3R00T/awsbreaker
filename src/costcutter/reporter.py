from __future__ import annotations

import csv
import threading
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


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
        # Tracks how many events have been flushed to CSV for append mode logic
        self._flushed_count = 0

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

    def write_csv(self, path: str | Path, overwrite: bool = True) -> Path:
        """Write recorded events to a CSV file.

        If overwrite is False subsequent calls will append only new events that
        haven't already been flushed (tracked via an internal counter).
        """
        p = Path(path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)

        mode = "w" if overwrite or not p.exists() else "a"
        write_header = mode == "w" or not p.exists()

        events = self.snapshot()
        events_to_write = events if mode == "w" else events[self._flushed_count :]

        fieldnames = ["timestamp", "region", "service", "resource", "action", "arn", "meta"]
        with p.open(mode, newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            for e in events_to_write:
                row = asdict(e)
                meta_val = row.get("meta") or {}
                if isinstance(meta_val, dict):
                    row["meta"] = ";".join(f"{k}={v}" for k, v in meta_val.items())
                else:
                    row["meta"] = str(meta_val)
                writer.writerow(row)
        self._flushed_count = len(events)
        return p


# Lazy singleton
_reporter: Reporter | None = None


def get_reporter() -> Reporter:
    global _reporter
    if _reporter is None:
        _reporter = Reporter()
    return _reporter
