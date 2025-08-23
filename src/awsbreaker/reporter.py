import threading
from datetime import datetime


class Reporter:
    def __init__(self):
        self._events = []
        self._events_lock = threading.Lock()

    def record(self, service: str, resource: str, action: str, arn: str | None = None, meta: dict | None = None):
        event = {
            "timestamp": datetime.now(datetime.timezone.utc).isoformat(),
            "service": service,
            "resource": resource,
            "action": action,
            "id": arn,
            "meta": meta or {},
        }
        with self._events_lock:
            self._events.append(event)

    def get_events(self):
        return self._events


_reporter: Reporter | None = Reporter()


# instead of importing `_reporter` we can use the `get_reporter()` to fetch the only instance of reporter and then invoke `record` method to it
def get_reporter() -> Reporter:
    global _reporter
    if _reporter is not None:
        return _reporter
    ...
    return _reporter


class Sinks:
    def __init__(self):
        self.events = get_reporter().get_events()

    ...  # export events details in various outputs like print (stdout), logging (based on logging config), csv, etc.
