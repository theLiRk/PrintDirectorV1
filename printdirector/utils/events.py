from collections import deque
from datetime import datetime, timezone


class EventHistory:
    def __init__(self, limit=100):
        self.limit = max(10, int(limit))
        self._items = deque(maxlen=self.limit)
        self._next_id = 1

    def add(self, event_type, message, severity="info", printer_id=None, details=None):
        item = {
            "id": self._next_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": str(event_type),
            "severity": severity,
            "message": message,
            "printer_id": printer_id,
            "details": details or {},
        }
        self._next_id += 1
        self._items.append(item)
        return item

    def list(self, limit=None):
        items = list(self._items)
        if limit is not None:
            items = items[-max(0, int(limit)):]
        return list(reversed(items))

    def resize(self, limit):
        limit = max(10, int(limit))
        if limit == self.limit:
            return
        existing = list(self._items)[-limit:]
        self.limit = limit
        self._items = deque(existing, maxlen=limit)
