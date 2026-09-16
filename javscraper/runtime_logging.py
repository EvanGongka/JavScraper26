from __future__ import annotations

import contextvars
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import socket
import sys
import threading
import time
import traceback as traceback_module
from typing import Any, Callable, Iterator
from urllib.parse import SplitResult, urlsplit, urlunsplit

try:
    import resource
except ImportError:  # pragma: no cover - resource is unavailable on Windows
    resource = None


_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARN": logging.WARNING,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}
_SENSITIVE_KEY_RE = re.compile(
    r"(?i)(cookie|authorization|proxy-?authorization|token|password|passwd|secret|api[_-]?key)"
)
_KEY_VALUE_RE = re.compile(
    r"(?i)(\b(?:cookie|authorization|proxy-?authorization|token|password|passwd|secret|api[_-]?key)\b\s*[:=]\s*)([^\s,;]+)"
)
_URL_RE = re.compile(r"(?i)(?:https?|socks5?)://[^\s<>\"']+")

request_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "javscraper_request_id", default=None
)
task_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "javscraper_task_id", default=None
)


def current_request_id() -> str | None:
    return request_id_context.get()


def current_task_id() -> str | None:
    return task_id_context.get()


class _Context:
    def __init__(self, request_id: str | None = None, task_id: str | None = None) -> None:
        self.request_id = request_id
        self.task_id = task_id
        self._request_token = None
        self._task_token = None

    def __enter__(self) -> "_Context":
        if self.request_id is not None:
            self._request_token = request_id_context.set(self.request_id)
        if self.task_id is not None:
            self._task_token = task_id_context.set(self.task_id)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._task_token is not None:
            task_id_context.reset(self._task_token)
        if self._request_token is not None:
            request_id_context.reset(self._request_token)


def request_context(request_id: str | None = None, task_id: str | None = None) -> _Context:
    return _Context(request_id=request_id, task_id=task_id)


def _env_int(name: str, default: int, *, minimum: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if minimum is not None and value < minimum:
        return default
    return value


def _env_float(name: str, default: float, *, minimum: float | None = None) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if minimum is not None and value < minimum:
        return default
    return value


@dataclass(frozen=True)
class LogSettings:
    level: str = "INFO"
    file_path: str = "/var/log/javscraper/javscraper.log"
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5
    heartbeat_interval: float = 60.0
    slow_request_ms: float = 3000.0
    metadata_cache_max_entries: int = 512
    metadata_cache_ttl_seconds: float = 86400.0
    max_image_bytes: int = 25 * 1024 * 1024
    max_concurrent_upstream: int = 8
    http_connect_timeout: float = 10.0
    http_read_timeout: float = 30.0
    http_retries: int = 2
    task_retention_seconds: float = 3600.0
    task_max_count: int = 100
    task_log_max_entries: int = 400

    @classmethod
    def from_env(cls) -> "LogSettings":
        level = os.getenv("JAVSCRAPER_LOG_LEVEL", cls.level).strip().upper() or cls.level
        if level not in _LEVELS:
            level = cls.level
        return cls(
            level=level,
            file_path=os.getenv("JAVSCRAPER_LOG_FILE", cls.file_path).strip() or cls.file_path,
            max_bytes=_env_int("JAVSCRAPER_LOG_MAX_BYTES", cls.max_bytes, minimum=1024),
            backup_count=_env_int("JAVSCRAPER_LOG_BACKUP_COUNT", cls.backup_count, minimum=0),
            heartbeat_interval=_env_float("JAVSCRAPER_HEARTBEAT_INTERVAL", cls.heartbeat_interval, minimum=0.1),
            slow_request_ms=_env_float("JAVSCRAPER_SLOW_REQUEST_MS", cls.slow_request_ms, minimum=0),
            metadata_cache_max_entries=_env_int(
                "JAVSCRAPER_METADATA_CACHE_MAX_ENTRIES", cls.metadata_cache_max_entries, minimum=1
            ),
            metadata_cache_ttl_seconds=_env_float(
                "JAVSCRAPER_METADATA_CACHE_TTL_SECONDS", cls.metadata_cache_ttl_seconds, minimum=1
            ),
            max_image_bytes=_env_int("JAVSCRAPER_MAX_IMAGE_BYTES", cls.max_image_bytes, minimum=1),
            max_concurrent_upstream=_env_int(
                "JAVSCRAPER_MAX_CONCURRENT_UPSTREAM", cls.max_concurrent_upstream, minimum=1
            ),
            http_connect_timeout=_env_float("JAVSCRAPER_HTTP_CONNECT_TIMEOUT", cls.http_connect_timeout, minimum=0.1),
            http_read_timeout=_env_float("JAVSCRAPER_HTTP_READ_TIMEOUT", cls.http_read_timeout, minimum=0.1),
            http_retries=_env_int("JAVSCRAPER_HTTP_RETRIES", cls.http_retries, minimum=0),
            task_retention_seconds=_env_float(
                "JAVSCRAPER_TASK_RETENTION_SECONDS", cls.task_retention_seconds, minimum=1
            ),
            task_max_count=_env_int("JAVSCRAPER_TASK_MAX_COUNT", cls.task_max_count, minimum=1),
            task_log_max_entries=_env_int(
                "JAVSCRAPER_TASK_LOG_MAX_ENTRIES", cls.task_log_max_entries, minimum=1
            ),
        )


def _redact_split_url(parsed: SplitResult) -> str:
    netloc = parsed.netloc
    if "@" in netloc:
        netloc = "[REDACTED]@" + netloc.rsplit("@", 1)[1]
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def redact_url(value: str) -> str:
    text = str(value)
    try:
        parsed = urlsplit(text)
    except ValueError:
        return "[REDACTED_URL]"
    if not parsed.scheme or not parsed.netloc:
        return text
    return _redact_split_url(parsed)


def redact_text(value: Any) -> str:
    text = str(value)

    def replace_url(match: re.Match[str]) -> str:
        raw_url = match.group(0)
        clean_url = raw_url.rstrip(".,)];")
        return redact_url(clean_url) + raw_url[len(clean_url) :]

    text = _URL_RE.sub(replace_url, text)
    text = _KEY_VALUE_RE.sub(r"\1[REDACTED]", text)
    return text


def redact_value(value: Any, *, key: str | None = None) -> Any:
    if key and _SENSITIVE_KEY_RE.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(item_key): redact_value(item_value, key=str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return redact_text(value)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


class RuntimeLogWriter:
    """Writes readable stdout logs and best-effort rotating JSONL diagnostics."""

    def __init__(self, settings: LogSettings | None = None, *, stream=None) -> None:
        self.settings = settings or LogSettings.from_env()
        self.stream = stream or sys.stdout
        self._lock = threading.RLock()
        self._file_failure_reported = False
        self._closed = False

    @property
    def file_configured(self) -> bool:
        return bool(self.settings.file_path)

    def _should_log(self, level: str) -> bool:
        return _LEVELS.get(level.upper(), logging.INFO) >= _LEVELS.get(self.settings.level, logging.INFO)

    def _rotate_if_needed(self, incoming_bytes: int) -> None:
        path = Path(self.settings.file_path)
        if not path.exists() or self.settings.backup_count <= 0:
            return
        try:
            if path.stat().st_size + incoming_bytes <= self.settings.max_bytes:
                return
        except OSError:
            return
        for index in range(self.settings.backup_count, 0, -1):
            source = path.with_name(f"{path.name}.{index}") if index > 1 else path
            target = path.with_name(f"{path.name}.{index + 1}") if index > 1 else path.with_name(f"{path.name}.1")
            if index == self.settings.backup_count:
                target.unlink(missing_ok=True)
            if source.exists():
                source.replace(target)

    def _write_file(self, line: str) -> None:
        if not self.file_configured:
            return
        path = Path(self.settings.file_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            encoded = (line + "\n").encode("utf-8")
            self._rotate_if_needed(len(encoded))
            with path.open("ab") as file:
                file.write(encoded)
        except OSError as exc:
            if not self._file_failure_reported:
                self._file_failure_reported = True
                print(
                    f"[javscraper] 日志文件写入失败，已继续使用 stdout/stderr: {path} ({exc})",
                    file=sys.stderr,
                    flush=True,
                )

    def emit(
        self,
        level: str,
        source: str,
        message: Any,
        *,
        timestamp: str | None = None,
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
        normalized_level = level.upper()
        if not self._should_log(normalized_level):
            return
        safe_message = redact_text(message)
        safe_details = redact_value(details) if details is not None else None
        request_id = request_id if request_id is not None else current_request_id()
        task_id = task_id if task_id is not None else current_task_id()
        record = {
            "timestamp": timestamp or _now_iso(),
            "level": normalized_level,
            "logger": "javscraper",
            "event": event or "service.log",
            "source": source,
            "message": safe_message,
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "thread": threading.current_thread().name,
            "request_id": request_id,
            "task_id": task_id,
            "code": redact_text(code) if code is not None else None,
            "provider": redact_text(provider) if provider is not None else None,
            "duration_ms": round(duration_ms, 1) if duration_ms is not None else None,
            "exception_type": exception_type,
            "traceback": redact_text(traceback) if traceback else None,
            "details": safe_details,
        }
        json_line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        fields = []
        for key, label in (
            ("event", "event"),
            ("request_id", "request_id"),
            ("task_id", "task_id"),
            ("code", "code"),
            ("provider", "provider"),
            ("duration_ms", "duration_ms"),
        ):
            if record[key] is not None:
                fields.append(f"{label}={record[key]}")
        suffix = f" {' '.join(fields)}" if fields else ""
        text_line = f"[javscraper] {record['timestamp']} {normalized_level} {source}{suffix}: {safe_message}"
        with self._lock:
            if self._closed:
                return
            try:
                print(text_line, file=self.stream, flush=True)
            except Exception:
                print(text_line, file=sys.stderr, flush=True)
            self._write_file(json_line)

    def close(self) -> None:
        with self._lock:
            self._closed = True


class RuntimeLogHandler(logging.Handler):
    def __init__(self, writer: RuntimeLogWriter) -> None:
        super().__init__()
        self.writer = writer

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
            tb = None
            if record.exc_info:
                tb = "".join(traceback_module.format_exception(*record.exc_info))
            self.writer.emit(
                record.levelname,
                record.name,
                message,
                event="python.log",
                exception_type=(record.exc_info[0].__name__ if record.exc_info and record.exc_info[0] else None),
                traceback=tb,
            )
        except Exception:
            self.handleError(record)


_writer: RuntimeLogWriter | None = None
_logging_configured = False
_logging_lock = threading.Lock()


def get_runtime_log_writer() -> RuntimeLogWriter:
    global _writer
    with _logging_lock:
        if _writer is None:
            _writer = RuntimeLogWriter()
        return _writer


def configure_bootstrap_logging() -> RuntimeLogWriter:
    global _logging_configured
    writer = get_runtime_log_writer()
    with _logging_lock:
        if not _logging_configured:
            root = logging.getLogger()
            root.addHandler(RuntimeLogHandler(writer))
            root.setLevel(_LEVELS.get(writer.settings.level, logging.INFO))
            for name in ("uvicorn", "uvicorn.error"):
                logger = logging.getLogger(name)
                logger.setLevel(_LEVELS.get(writer.settings.level, logging.INFO))
                logger.propagate = True
            _logging_configured = True
    return writer


def _rss_bytes() -> int | None:
    try:
        status_path = Path("/proc/self/status")
        if status_path.exists():
            for line in status_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError):
        pass
    if resource is None:
        return None
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(usage * (1 if sys.platform == "darwin" else 1024))
    except (OSError, ValueError):
        return None


class RuntimeMetrics:
    def __init__(self) -> None:
        self.started_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        self.started_monotonic = time.monotonic()
        self._lock = threading.Lock()
        self._requests_total = 0
        self._active_requests = 0
        self._request_errors = 0
        self._slow_requests = 0
        self._upstream_total = 0
        self._upstream_errors = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._cache_evictions = 0
        self._tasks_active = 0
        self._tasks_completed = 0
        self._tasks_failed = 0
        self._last_request_at: str | None = None
        self._last_error_at: str | None = None

    def request_started(self) -> None:
        with self._lock:
            self._requests_total += 1
            self._active_requests += 1

    def request_finished(self, *, error: bool = False, slow: bool = False) -> None:
        now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        with self._lock:
            self._active_requests = max(0, self._active_requests - 1)
            self._last_request_at = now
            if error:
                self._request_errors += 1
                self._last_error_at = now
            if slow:
                self._slow_requests += 1

    def upstream_started(self) -> None:
        with self._lock:
            self._upstream_total += 1

    def upstream_failed(self) -> None:
        with self._lock:
            self._upstream_errors += 1
            self._last_error_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    def error_recorded(self) -> None:
        with self._lock:
            self._last_error_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    def cache_hit(self) -> None:
        with self._lock:
            self._cache_hits += 1

    def cache_miss(self) -> None:
        with self._lock:
            self._cache_misses += 1

    def cache_evicted(self, count: int = 1) -> None:
        with self._lock:
            self._cache_evictions += count

    def task_started(self) -> None:
        with self._lock:
            self._tasks_active += 1

    def task_finished(self, *, failed: bool = False) -> None:
        with self._lock:
            self._tasks_active = max(0, self._tasks_active - 1)
            if failed:
                self._tasks_failed += 1
            else:
                self._tasks_completed += 1

    def snapshot(self, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            snapshot = {
                "uptimeSeconds": round(max(0.0, time.monotonic() - self.started_monotonic), 1),
                "pid": os.getpid(),
                "memoryRssBytes": _rss_bytes(),
                "requestsTotal": self._requests_total,
                "activeRequests": self._active_requests,
                "requestErrors": self._request_errors,
                "slowRequests": self._slow_requests,
                "upstreamRequests": self._upstream_total,
                "upstreamErrors": self._upstream_errors,
                "cacheHits": self._cache_hits,
                "cacheMisses": self._cache_misses,
                "cacheEvictions": self._cache_evictions,
                "tasksActive": self._tasks_active,
                "tasksCompleted": self._tasks_completed,
                "tasksFailed": self._tasks_failed,
                "lastRequestAt": self._last_request_at,
                "lastErrorAt": self._last_error_at,
            }
        if extra:
            snapshot.update(extra)
        return snapshot


RUNTIME_METRICS = RuntimeMetrics()


class RuntimeMonitor:
    def __init__(
        self,
        snapshot_provider: Callable[[], dict[str, Any]],
        *,
        interval: float | None = None,
        writer: RuntimeLogWriter | None = None,
    ) -> None:
        self.snapshot_provider = snapshot_provider
        self.interval = interval if interval is not None else LogSettings.from_env().heartbeat_interval
        self.writer = writer or get_runtime_log_writer()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def emit_heartbeat(self) -> None:
        try:
            details = self.snapshot_provider()
            message = (
                "运行心跳: "
                f"uptime={details.get('uptimeSeconds', '?')}s "
                f"pid={details.get('pid', '?')} "
                f"rss={details.get('memoryRssBytes', '?')} "
                f"activeRequests={details.get('activeRequests', '?')} "
                f"taskCount={details.get('taskCount', '?')} "
                f"cacheEntries={details.get('metadataCacheEntries', '?')}"
            )
            self.writer.emit(
                "INFO",
                "heartbeat",
                message,
                event="runtime.heartbeat",
                details=details,
            )
        except Exception as exc:
            self.writer.emit(
                "ERROR",
                "heartbeat",
                f"心跳采集失败: {exc}",
                event="runtime.heartbeat.error",
                exception_type=type(exc).__name__,
                traceback=traceback_module.format_exc(),
            )

    def _run(self) -> None:
        while not self._stop_event.wait(self.interval):
            self.emit_heartbeat()

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, name="javscraper-heartbeat", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            self._stop_event.set()
        if thread and thread is not threading.current_thread():
            thread.join(timeout=max(1.0, min(self.interval + 1.0, 10.0)))
        with self._lock:
            self._thread = None


def traceback_text(exc: BaseException) -> str:
    return "".join(traceback_module.format_exception(type(exc), exc, exc.__traceback__))


__all__ = [
    "LogSettings",
    "RuntimeLogHandler",
    "RuntimeLogWriter",
    "RuntimeMetrics",
    "RuntimeMonitor",
    "RUNTIME_METRICS",
    "configure_bootstrap_logging",
    "current_request_id",
    "current_task_id",
    "get_runtime_log_writer",
    "redact_text",
    "redact_url",
    "redact_value",
    "request_context",
    "traceback_text",
]
