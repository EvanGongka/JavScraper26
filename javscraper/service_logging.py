from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Iterable


@dataclass
class ServiceLogEntry:
    timestamp: str
    level: str
    source: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "source": self.source,
            "message": self.message,
        }


class ServiceLogStore:
    def __init__(self, max_entries: int = 400) -> None:
        self._entries: deque[ServiceLogEntry] = deque(maxlen=max_entries)
        self._lock = Lock()

    def add(self, level: str, source: str, message: str) -> None:
        entry = ServiceLogEntry(
            timestamp=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            level=level.upper(),
            source=source,
            message=message,
        )
        with self._lock:
            self._entries.append(entry)

    def extend(self, level: str, source: str, messages: Iterable[str]) -> None:
        for message in messages:
            self.add(level, source, message)

    def recent(self, limit: int = 200) -> list[dict[str, str]]:
        with self._lock:
            return [entry.to_dict() for entry in list(self._entries)[-limit:]]
