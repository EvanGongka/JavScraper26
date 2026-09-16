from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import sys
from threading import Lock
from typing import Any, Iterable

from javscraper.runtime_logging import current_request_id, current_task_id, redact_text, redact_value


@dataclass
class ServiceLogEntry:
    timestamp: str
    level: str
    source: str
    message: str
    event: str | None = None
    request_id: str | None = None
    task_id: str | None = None
    code: str | None = None
    provider: str | None = None
    duration_ms: float | None = None
    exception_type: str | None = None
    traceback: str | None = None
    details: dict[str, Any] | list[Any] | None = None

    def to_dict(self, *, include_traceback: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "timestamp": self.timestamp,
            "level": self.level,
            "source": self.source,
            "message": self.message,
        }
        optional = {
            "event": self.event,
            "request_id": self.request_id,
            "task_id": self.task_id,
            "code": self.code,
            "provider": self.provider,
            "duration_ms": self.duration_ms,
            "exception_type": self.exception_type,
            "details": self.details,
        }
        if include_traceback:
            optional["traceback"] = self.traceback
        for key, value in optional.items():
            if value is not None:
                result[key] = value
        return result


class ServiceLogStore:
    def __init__(
        self,
        max_entries: int = 400,
        on_entry: Callable[[ServiceLogEntry], None] | None = None,
    ) -> None:
        self._entries: deque[ServiceLogEntry] = deque(maxlen=max_entries)
        self._lock = Lock()
        self._on_entry = on_entry

    def add(
        self,
        level: str,
        source: str,
        message: str,
        *,
        event: str | None = None,
        request_id: str | None = None,
        task_id: str | None = None,
        code: str | None = None,
        provider: str | None = None,
        duration_ms: float | None = None,
        exception_type: str | None = None,
        traceback: str | None = None,
        details: Any = None,
    ) -> None:
        entry = ServiceLogEntry(
            timestamp=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            level=level.upper(),
            source=source,
            message=redact_text(message),
            event=event,
            request_id=request_id if request_id is not None else current_request_id(),
            task_id=task_id if task_id is not None else current_task_id(),
            code=redact_text(code) if code is not None else None,
            provider=redact_text(provider) if provider is not None else None,
            duration_ms=round(duration_ms, 1) if duration_ms is not None else None,
            exception_type=exception_type,
            traceback=redact_text(traceback) if traceback else None,
            details=redact_value(details) if details is not None else None,
        )
        with self._lock:
            self._entries.append(entry)
        if self._on_entry is not None:
            try:
                self._on_entry(entry)
            except Exception as exc:  # pragma: no cover - defensive logging fallback
                print(f"[javscraper] 日志回调失败: {exc}", file=sys.stderr, flush=True)

    def extend(self, level: str, source: str, messages: Iterable[str]) -> None:
        for message in messages:
            self.add(level, source, message)

    def recent(self, limit: int = 200) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        with self._lock:
            return [entry.to_dict() for entry in list(self._entries)[-min(limit, self._entries.maxlen or limit):]]
