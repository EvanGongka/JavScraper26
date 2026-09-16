from __future__ import annotations

import os
from collections import deque
import re
import socket
import sys
import threading
import time
import traceback as traceback_module
import uuid
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from javscraper.emby_service import (
    EmbyMovieService,
    ProxyConfig,
    default_proxy_from_env,
    proxy_from_query,
)
from javscraper.images import (
    crop_to_poster,
    download_image_bytes,
    is_portrait_image,
    landscape_image_candidates,
    select_best_regular_poster_for_metadata,
    should_crop_poster_from_fanart,
)
from javscraper.network import HttpClient
from javscraper.pipeline import ScrapePipeline
from javscraper.provider_catalog import (
    DEFAULT_SITES,
    PROVIDER_GROUP_BY_NAME,
    PROVIDER_GROUP_LABELS,
    SITE_CONNECTIVITY_TARGETS,
    connectivity_provider_names_for_codes,
    normalize_provider_names,
)
from javscraper.scanner import scan_directory
from javscraper.service_logging import ServiceLogStore
from javscraper.runtime_logging import (
    LogSettings,
    RUNTIME_METRICS,
    RuntimeMonitor,
    configure_bootstrap_logging,
    get_runtime_log_writer,
    redact_text,
    redact_url,
    request_context,
    traceback_text,
)
from javscraper.utils.browser import get_javdb_cookie_status
from javscraper.utils.dialogs import pick_directory

if getattr(sys, "frozen", False):
    BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

WEB_DIR = BASE_DIR / "webui"
IGNORED_SERVICE_LOG_PATHS = {
    "/emby-api/v1/health",
    "/emby-api/v1/logs/recent",
}


def _write_console_log(entry) -> None:
    get_runtime_log_writer().emit(
        entry.level,
        entry.source,
        entry.message,
        timestamp=entry.timestamp,
        event=entry.event or "service.log",
        request_id=entry.request_id,
        task_id=entry.task_id,
        code=entry.code,
        provider=entry.provider,
        duration_ms=entry.duration_ms,
        exception_type=entry.exception_type,
        traceback=entry.traceback,
        details=entry.details,
    )


@dataclass
class TaskState:
    task_id: str
    source_path: str
    output_path: str
    providers: list[str]
    proxy_url: str | None = None
    status: str = "running"
    logs: deque[str] = field(default_factory=lambda: deque(maxlen=LogSettings.from_env().task_log_max_entries))
    entries: dict[str, str] = field(default_factory=dict)
    manifest_path: str | None = None
    error: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    created_monotonic: float = field(default_factory=time.monotonic, repr=False)
    updated_monotonic: float = field(default_factory=time.monotonic, repr=False)
    finished_monotonic: float | None = field(default=None, repr=False)

    def append_log(self, text: str) -> None:
        with self.lock:
            self.logs.append(redact_text(text))
            self.updated_monotonic = time.monotonic()

    def set_entry_status(self, code: str, status: str) -> None:
        with self.lock:
            self.entries[code] = status
            self.updated_monotonic = time.monotonic()

    def finish(self, manifest_path: str | None = None, error: str | None = None) -> None:
        with self.lock:
            self.status = "failed" if error else "completed"
            self.manifest_path = manifest_path
            self.error = redact_text(error) if error else None
            self.updated_monotonic = time.monotonic()
            self.finished_monotonic = self.updated_monotonic

    def to_dict(self) -> dict[str, Any]:
        with self.lock:
            return {
                "taskId": self.task_id,
                "sourcePath": self.source_path,
                "outputPath": self.output_path,
                "providers": self.providers,
                "status": self.status,
                "logs": list(self.logs),
                "entries": dict(self.entries),
                "manifestPath": self.manifest_path,
                "error": self.error,
            }


TASKS: dict[str, TaskState] = {}
TASKS_LOCK = threading.Lock()
SERVICE_LOGS = ServiceLogStore(on_entry=_write_console_log)
EMBY_SERVICE = EmbyMovieService(
    provider_names=DEFAULT_SITES,
    log_store=SERVICE_LOGS,
    default_proxy=default_proxy_from_env(),
)


def _runtime_snapshot() -> dict[str, Any]:
    _cleanup_tasks()
    snapshot = RUNTIME_METRICS.snapshot()
    with TASKS_LOCK:
        task_count = len(TASKS)
        running_task_count = sum(1 for task in TASKS.values() if task.status == "running")
    cache = EMBY_SERVICE.cache_stats()
    snapshot.update({
        "taskCount": task_count,
        "runningTaskCount": running_task_count,
        "metadataCacheEntries": cache["entries"],
        "metadataCacheMaxEntries": cache["maxEntries"],
        "metadataCacheTtlSeconds": cache["ttlSeconds"],
        "metadataCacheHits": cache["hits"],
        "metadataCacheMisses": cache["misses"],
        "metadataCacheEvictions": cache["evictions"],
    })
    return snapshot


RUNTIME_MONITOR = RuntimeMonitor(_runtime_snapshot)


def _cleanup_tasks(now: float | None = None) -> int:
    now = time.monotonic() if now is None else now
    settings = LogSettings.from_env()
    removed = 0
    with TASKS_LOCK:
        expired_ids = [
            task_id
            for task_id, task in TASKS.items()
            if task.status != "running"
            and task.finished_monotonic is not None
            and now - task.finished_monotonic >= settings.task_retention_seconds
        ]
        for task_id in expired_ids:
            TASKS.pop(task_id, None)
            removed += 1

        completed_tasks = sorted(
            (
                task
                for task in TASKS.values()
                if task.status != "running" and task.finished_monotonic is not None
            ),
            key=lambda task: task.finished_monotonic or task.updated_monotonic,
        )
        overflow = max(0, len(TASKS) - settings.task_max_count)
        for task in completed_tasks[:overflow]:
            if TASKS.pop(task.task_id, None) is not None:
                removed += 1
    return removed


class ScanRequest(BaseModel):
    sourcePath: str


class PickRequest(BaseModel):
    title: str


class StartRequest(BaseModel):
    sourcePath: str
    outputPath: str
    providers: Optional[list[str]] = None
    proxy: Optional[dict[str, Any]] = None


class ConnectivityRequest(BaseModel):
    proxy: Optional[dict[str, Any]] = None
    codes: Optional[list[str]] = None
    sites: Optional[list[str]] = None


app = FastAPI(title="javScraper26")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


def _mode_override() -> str | None:
    mode = os.getenv("JAVSCRAPER_MODE", "").strip().lower()
    return mode if mode in {"webui", "service"} else None


def _proxy_from_payload(proxy: dict[str, Any] | None) -> ProxyConfig:
    if not proxy:
        return ProxyConfig()
    protocol = str(proxy.get("protocol", "")).strip()
    host = str(proxy.get("host", "")).strip()
    port = str(proxy.get("port", "")).strip()
    enabled = bool(proxy.get("enabled", False))
    return ProxyConfig(
        enabled=enabled,
        protocol=protocol,
        host=host,
        port=port,
    )


def _proxy_url_from_payload(proxy: dict[str, Any] | None) -> str | None:
    return _proxy_from_payload(proxy).url


def _log_service(level: str, source: str, message: str, **kwargs: Any) -> None:
    if level.upper() in {"ERROR", "CRITICAL"}:
        RUNTIME_METRICS.error_recorded()
    SERVICE_LOGS.add(level, source, message, **kwargs)


def _should_log_http_request(path: str) -> bool:
    if path in IGNORED_SERVICE_LOG_PATHS or path.startswith("/static"):
        return False
    if path in {"/", "/webui", "/service"}:
        return True
    return path.startswith("/api/") or path.startswith("/emby-api/")


def _request_log_source(path: str) -> str:
    if path.startswith("/emby-api/"):
        return "emby-http"
    return "http"


def _masked_proxy_url(proxy_url: str | None) -> str:
    return redact_url(proxy_url) if proxy_url else "disabled"


def _log_launch_summary(host: str, port: int, browser_host: str) -> None:
    browser_enabled = _should_open_browser()
    _log_service(
        "INFO",
        "startup",
        (
            f"启动服务: mode={_mode_override() or 'auto'} host={host} port={port} "
            f"browser={'enabled' if browser_enabled else 'disabled'}"
        ),
    )
    _log_service(
        "INFO",
        "startup",
        f"访问地址: root=http://{browser_host}:{port}/ service=http://{browser_host}:{port}/service",
    )
    _log_service(
        "INFO",
        "startup",
        f"健康检查: http://127.0.0.1:{port}/emby-api/v1/health 默认代理={_masked_proxy_url(EMBY_SERVICE.default_proxy.url)}",
    )


def _connectivity_result_for(client: HttpClient, name: str, url: str) -> dict[str, Any]:
    check = client.connectivity_check(url)
    return {
        "name": name,
        "url": url,
        "ok": check["ok"],
        "status": check["status"],
        "detail": check["detail"],
        "finalUrl": check["finalUrl"],
    }


def _provider_metadata() -> list[dict[str, Any]]:
    javdb_status = _javdb_status()
    return [
        {
            "name": name,
            "group": PROVIDER_GROUP_BY_NAME[name],
            "groupLabel": PROVIDER_GROUP_LABELS[PROVIDER_GROUP_BY_NAME[name]],
            "sortOrder": index,
            "requiresLogin": name == "JavDB",
            "hint": javdb_status["reason"] if name == "JavDB" else "",
        }
        for index, name in enumerate(DEFAULT_SITES, start=1)
    ]


def _javdb_status() -> dict[str, str | bool]:
    return get_javdb_cookie_status()


def _javdb_available() -> bool:
    return bool(_javdb_status()["available"])


def _connectivity_sites_for_payload(payload: ConnectivityRequest) -> list[str]:
    if payload.sites:
        unknown_sites = [name for name in payload.sites if name not in SITE_CONNECTIVITY_TARGETS]
        if unknown_sites:
            raise HTTPException(status_code=400, detail=f"未知站点: {', '.join(unknown_sites)}")
        return normalize_provider_names(payload.sites)
    if payload.codes:
        return connectivity_provider_names_for_codes(
            payload.codes,
            DEFAULT_SITES,
            javdb_available=_javdb_available(),
        )
    return connectivity_provider_names_for_codes(
        [],
        DEFAULT_SITES,
        javdb_available=_javdb_available(),
    )


def _connectivity_result_for_unavailable_provider(name: str, detail: str) -> dict[str, Any]:
    url = SITE_CONNECTIVITY_TARGETS[name]
    return {
        "name": name,
        "url": url,
        "ok": False,
        "status": None,
        "detail": detail,
        "finalUrl": url,
    }


def _run_task(task: TaskState) -> None:
    failed = False
    with request_context(task_id=task.task_id):
        _log_service(
            "INFO",
            "task",
            f"任务开始: source={task.source_path} output={task.output_path}",
            event="task.started",
            task_id=task.task_id,
            details={"sourcePath": task.source_path, "outputPath": task.output_path},
        )
        try:
            entries, skipped = scan_directory(task.source_path)
            javdb_available = _javdb_available()
            task.providers = connectivity_provider_names_for_codes(
                [entry.code for entry in entries],
                task.providers,
                javdb_available=javdb_available,
            )
            for entry in entries:
                task.set_entry_status(entry.code, "待处理")
            task.append_log(f"扫描完成: 识别 {len(entries)} 个条目，跳过 {len(skipped)} 个文件")
            _log_service(
                "INFO",
                "task",
                f"扫描完成: entries={len(entries)} skipped={len(skipped)}",
                event="task.scan_completed",
                task_id=task.task_id,
                details={"entryCount": len(entries), "skippedCount": len(skipped)},
            )

            def on_entry_error(code: str, exc: Exception) -> None:
                _log_service(
                    "ERROR",
                    "task",
                    f"[{code}] 单条目异常，已跳过并继续: {exc}",
                    event="task.entry_failed",
                    task_id=task.task_id,
                    code=code,
                    exception_type=type(exc).__name__,
                    traceback=traceback_text(exc),
                    details={"sourcePath": task.source_path, "outputPath": task.output_path},
                )

            pipeline = ScrapePipeline(
                output_root=task.output_path,
                provider_names=task.providers,
                on_log=task.append_log,
                on_status=task.set_entry_status,
                proxy_url=task.proxy_url,
                javdb_available=javdb_available,
                on_error=on_entry_error,
            )
            manifest = pipeline.run(entries)
            task.finish(str(manifest))
            _log_service(
                "INFO",
                "task",
                f"任务完成: manifest={manifest}",
                event="task.completed",
                task_id=task.task_id,
                details={"manifestPath": str(manifest)},
            )
        except Exception as exc:  # pragma: no cover - defensive task boundary
            failed = True
            task.append_log(f"任务异常: {exc}")
            task.finish(error=str(exc))
            _log_service(
                "ERROR",
                "task",
                f"任务异常，任务已结束: {exc}",
                event="task.failed",
                task_id=task.task_id,
                exception_type=type(exc).__name__,
                traceback=traceback_text(exc),
                details={"sourcePath": task.source_path, "outputPath": task.output_path},
            )
        finally:
            RUNTIME_METRICS.task_finished(failed=failed or task.status == "failed")
            _cleanup_tasks()


def _fetch_remote_image(url: str, proxy: ProxyConfig) -> tuple[bytes, str]:
    client = HttpClient(proxy_url=proxy.url, proxy_source="emby_image")
    started = time.perf_counter()
    try:
        content, media_type = download_image_bytes(client, url)
        _log_service(
            "INFO",
            "emby-image",
            f"图片下载完成: {redact_url(url)} ({len(content)} bytes)",
            event="emby.image.download_completed",
            duration_ms=(time.perf_counter() - started) * 1000,
            details={
                "url": redact_url(url),
                "sizeBytes": len(content),
                "mediaType": media_type,
                "proxyConfigured": bool(proxy.url),
            },
        )
        return content, media_type
    except Exception as exc:
        error_details = {"url": redact_url(url), "proxyConfigured": bool(proxy.url)}
        if hasattr(exc, "size"):
            error_details["sizeBytes"] = getattr(exc, "size")
        if hasattr(exc, "limit"):
            error_details["maxBytes"] = getattr(exc, "limit")
        _log_service(
            "WARN",
            "emby-image",
            f"图片下载失败: {redact_url(url)} ({exc})",
            event="emby.image.download_failed",
            duration_ms=(time.perf_counter() - started) * 1000,
            exception_type=type(exc).__name__,
            traceback=traceback_text(exc),
            details=error_details,
        )
        raise HTTPException(status_code=404, detail=f"图片下载失败: {redact_text(exc)}") from exc
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def _stream_remote_image(url: str, proxy: ProxyConfig) -> Response:
    content, media_type = _fetch_remote_image(url, proxy)
    return Response(content=content, media_type=media_type)


def _fetch_best_landscape_image(urls: list[str | None], proxy: ProxyConfig) -> tuple[bytes, str]:
    fallback: tuple[bytes, str] | None = None
    last_error: Exception | None = None
    seen: set[str] = set()
    for url in urls:
        if not url or url in seen:
            continue
        seen.add(url)
        try:
            content, media_type = _fetch_remote_image(url, proxy)
        except Exception as exc:
            last_error = exc
            _log_service(
                "WARN",
                "emby-image",
                f"图片候选失败，继续尝试下一个: {redact_url(url)} ({exc})",
                event="emby.image.candidate_failed",
                exception_type=type(exc).__name__,
                details={"url": redact_url(url)},
            )
            continue
        try:
            is_portrait = is_portrait_image(content)
        except Exception as exc:
            last_error = exc
            _log_service(
                "WARN",
                "emby-image",
                f"图片候选损坏，继续尝试下一个: {redact_url(url)} ({exc})",
                event="emby.image.invalid",
                exception_type=type(exc).__name__,
                details={"url": redact_url(url), "sizeBytes": len(content)},
            )
            continue
        if fallback is None:
            fallback = (content, media_type)
        if not is_portrait:
            return content, media_type
    if fallback is not None:
        return fallback
    detail = "该条目没有可用图片"
    if last_error is not None:
        detail = f"图片候选全部失败: {redact_text(last_error)}"
    raise HTTPException(status_code=404, detail=detail)


@app.middleware("http")
async def service_request_logger(request: Request, call_next):
    path = request.url.path
    should_log = _should_log_http_request(path)
    source = _request_log_source(path)
    supplied_request_id = request.headers.get("x-request-id", "").strip()
    request_id = supplied_request_id if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", supplied_request_id) else uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    started = time.perf_counter()
    RUNTIME_METRICS.request_started()
    status_code = 500
    request_error = False
    try:
        with request_context(request_id=request_id):
            if should_log:
                _log_service(
                    "INFO",
                    source,
                    f"{request.method} {path} 开始处理",
                    event="http.request.started",
                    request_id=request_id,
                    details={"method": request.method, "path": path},
                )
            response = await call_next(request)
            status_code = response.status_code
    except Exception as exc:
        request_error = True
        elapsed_ms = (time.perf_counter() - started) * 1000
        if should_log:
            _log_service(
                "ERROR",
                source,
                f"{request.method} {path} -> 500 ({elapsed_ms:.1f}ms) {exc}",
                event="http.request.exception",
                request_id=request_id,
                duration_ms=elapsed_ms,
                exception_type=type(exc).__name__,
                traceback=traceback_module.format_exc(),
                details={"method": request.method, "path": path, "statusCode": 500},
            )
        raise
    else:
        elapsed_ms = (time.perf_counter() - started) * 1000
        slow = elapsed_ms >= LogSettings.from_env().slow_request_ms
        request_error = status_code >= 500
        if should_log:
            level = "ERROR" if status_code >= 500 else "WARN" if status_code >= 400 or slow else "INFO"
            event = "http.request.slow" if slow else "http.request.completed"
            _log_service(
                level,
                source,
                f"{request.method} {path} -> {status_code} ({elapsed_ms:.1f}ms)",
                event=event,
                request_id=request_id,
                duration_ms=elapsed_ms,
                details={"method": request.method, "path": path, "statusCode": status_code},
            )
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        RUNTIME_METRICS.request_finished(
            error=request_error,
            slow=elapsed_ms >= LogSettings.from_env().slow_request_ms,
        )


@app.on_event("startup")
def on_app_startup() -> None:
    configure_bootstrap_logging()
    _log_service(
        "INFO",
        "startup",
        "应用已启动，等待请求",
        event="application.ready",
        details={
            "mode": _mode_override() or "auto",
            "host": _launch_host(),
            "port": os.getenv("JAVSCRAPER_PORT", ""),
            "logFile": get_runtime_log_writer().settings.file_path,
        },
    )
    RUNTIME_MONITOR.start()


@app.on_event("shutdown")
def on_app_shutdown() -> None:
    _log_service("INFO", "shutdown", "收到停止信号，开始关闭服务", event="application.shutdown_started")
    RUNTIME_MONITOR.stop()
    _log_service("INFO", "shutdown", "服务已正常关闭", event="application.shutdown_completed")


@app.get("/")
def index():
    mode = _mode_override()
    if mode == "webui":
        return RedirectResponse("/webui", status_code=307)
    if mode == "service":
        return RedirectResponse("/service", status_code=307)
    return FileResponse(WEB_DIR / "index.html")


@app.get("/webui")
def webui_page():
    return FileResponse(WEB_DIR / "webui.html")


@app.get("/service")
def service_page():
    return FileResponse(WEB_DIR / "service.html")


@app.get("/api/providers")
def get_providers():
    return {"providers": _provider_metadata()}


@app.get("/api/runtime")
def get_runtime():
    return {
        "modeOverride": _mode_override() or "",
        "defaultProxyConfigured": bool(EMBY_SERVICE.default_proxy.url),
    }


@app.post("/api/pick-directory")
def api_pick_directory(payload: PickRequest):
    path = pick_directory(payload.title)
    if not path:
        raise HTTPException(status_code=400, detail="未选择目录")
    return {"path": path}


@app.post("/api/scan")
def api_scan(payload: ScanRequest):
    source = Path(payload.sourcePath).expanduser()
    if not source.is_dir():
        raise HTTPException(status_code=400, detail="扫描目录不存在")
    entries, skipped = scan_directory(source)
    return {
        "entries": [
            {
                "code": entry.code,
                "fileCount": entry.file_count,
                "primaryFile": str(entry.primary_file),
                "status": entry.status,
            }
            for entry in entries
        ],
        "skipped": [str(item) for item in skipped],
    }


@app.post("/api/connectivity")
def api_connectivity(payload: ConnectivityRequest):
    proxy_url = _proxy_url_from_payload(payload.proxy)
    client = HttpClient(proxy_url=proxy_url, proxy_source="webui_request")
    try:
        site_names = _connectivity_sites_for_payload(payload)
        site_items = [(name, SITE_CONNECTIVITY_TARGETS[name]) for name in site_names]
        return {"results": [_connectivity_result_for(client, name, url) for name, url in site_items]}
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


@app.post("/api/connectivity/{site_name}")
def api_connectivity_single(site_name: str, payload: ConnectivityRequest):
    if site_name not in SITE_CONNECTIVITY_TARGETS:
        raise HTTPException(status_code=404, detail="未知站点")
    if site_name == "JavDB" and not _javdb_available():
        return _connectivity_result_for_unavailable_provider(site_name, str(_javdb_status()["reason"]))
    proxy_url = _proxy_url_from_payload(payload.proxy)
    client = HttpClient(proxy_url=proxy_url, proxy_source="webui_request")
    try:
        return _connectivity_result_for(client, site_name, SITE_CONNECTIVITY_TARGETS[site_name])
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


@app.post("/api/start")
def api_start(payload: StartRequest):
    source = Path(payload.sourcePath).expanduser()
    output = Path(payload.outputPath).expanduser()
    if not source.is_dir():
        raise HTTPException(status_code=400, detail="扫描目录不存在")
    if payload.providers:
        unknown_providers = [name for name in payload.providers if name not in SITE_CONNECTIVITY_TARGETS]
        if unknown_providers:
            raise HTTPException(status_code=400, detail=f"未知站点: {', '.join(unknown_providers)}")

    provider_order = normalize_provider_names(payload.providers or DEFAULT_SITES)
    if not provider_order:
        raise HTTPException(status_code=400, detail="没有可用站点")

    _cleanup_tasks()
    settings = LogSettings.from_env()
    with TASKS_LOCK:
        if len(TASKS) >= settings.task_max_count:
            raise HTTPException(status_code=429, detail="当前任务数量已达到上限，请稍后再试")
        task_id = uuid.uuid4().hex[:12]
        task = TaskState(
            task_id=task_id,
            source_path=str(source),
            output_path=str(output),
            providers=provider_order,
            proxy_url=_proxy_url_from_payload(payload.proxy),
        )
        TASKS[task_id] = task
    RUNTIME_METRICS.task_started()
    _log_service(
        "INFO",
        "task",
        f"已创建任务: source={source} output={output}",
        event="task.created",
        task_id=task_id,
        details={"sourcePath": str(source), "outputPath": str(output)},
    )
    threading.Thread(target=_run_task, args=(task,), daemon=True).start()
    return {"taskId": task_id}


@app.get("/api/tasks/{task_id}")
def api_task(task_id: str):
    with TASKS_LOCK:
        task = TASKS.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task.to_dict()


@app.get("/emby-api/v1/health")
def emby_health():
    runtime = RUNTIME_METRICS.snapshot(extra=_runtime_snapshot())
    return {
        "status": "ok",
        "mode": "service",
        "defaultProxyConfigured": bool(EMBY_SERVICE.default_proxy.url),
        "providerCount": len(DEFAULT_SITES),
        "logCount": len(SERVICE_LOGS.recent()),
        "uptimeSeconds": runtime["uptimeSeconds"],
        "pid": runtime["pid"],
        "memoryRssBytes": runtime["memoryRssBytes"],
        "activeRequests": runtime["activeRequests"],
        "taskCount": runtime["taskCount"],
        "runningTaskCount": runtime["runningTaskCount"],
        "metadataCacheEntries": runtime["metadataCacheEntries"],
        "metadataCacheMaxEntries": runtime["metadataCacheMaxEntries"],
        "metadataCacheTtlSeconds": runtime["metadataCacheTtlSeconds"],
        "metadataCacheHits": runtime["metadataCacheHits"],
        "metadataCacheMisses": runtime["metadataCacheMisses"],
        "metadataCacheEvictions": runtime["metadataCacheEvictions"],
        "lastRequestAt": runtime["lastRequestAt"],
        "lastErrorAt": runtime["lastErrorAt"],
        "logFileConfigured": get_runtime_log_writer().file_configured,
    }


@app.get("/emby-api/v1/logs/recent")
def emby_recent_logs(limit: int = 200):
    return {"entries": SERVICE_LOGS.recent(limit=limit)}


@app.get("/emby-api/v1/movies/resolve")
def emby_resolve_movie(
    name: Optional[str] = None,
    path: Optional[str] = None,
    year: Optional[int] = None,
    proxyEnabled: Optional[str] = None,
    proxyProtocol: Optional[str] = None,
    proxyHost: Optional[str] = None,
    proxyPort: Optional[str] = None,
):
    requested_proxy = proxy_from_query(proxyEnabled, proxyProtocol, proxyHost, proxyPort)
    return EMBY_SERVICE.resolve_movie(name=name, path=path, year=year, requested_proxy=requested_proxy)


@app.get("/emby-api/v1/movies/{provider}/{provider_item_id}")
def emby_movie_detail(
    provider: str,
    provider_item_id: str,
    proxyEnabled: Optional[str] = None,
    proxyProtocol: Optional[str] = None,
    proxyHost: Optional[str] = None,
    proxyPort: Optional[str] = None,
):
    requested_proxy = proxy_from_query(proxyEnabled, proxyProtocol, proxyHost, proxyPort)
    return EMBY_SERVICE.get_movie(provider, provider_item_id, requested_proxy=requested_proxy)


@app.get("/emby-api/v1/images/{image_type}/{provider}/{provider_item_id}")
def emby_movie_image(
    image_type: str,
    provider: str,
    provider_item_id: str,
    proxyEnabled: Optional[str] = None,
    proxyProtocol: Optional[str] = None,
    proxyHost: Optional[str] = None,
    proxyPort: Optional[str] = None,
):
    requested_proxy = proxy_from_query(proxyEnabled, proxyProtocol, proxyHost, proxyPort)
    effective_proxy = EMBY_SERVICE.effective_proxy(requested_proxy)
    resolved_image = EMBY_SERVICE.get_image(image_type, provider, provider_item_id, requested_proxy=requested_proxy)

    if image_type == "primary":
        if should_crop_poster_from_fanart(resolved_image.metadata.code):
            client = HttpClient(proxy_url=effective_proxy.url, proxy_source="emby_image")
            try:
                selected = select_best_regular_poster_for_metadata(client, resolved_image.metadata)
            finally:
                close = getattr(client, "close", None)
                if callable(close):
                    close()
            if selected is not None:
                if selected.mode == "regular_crop":
                    return Response(content=crop_to_poster(selected.image_bytes), media_type="image/jpeg")
                return Response(content=selected.image_bytes, media_type=selected.media_type)
        fanart_bytes, media_type = _fetch_best_landscape_image(
            landscape_image_candidates(resolved_image.metadata),
            effective_proxy,
        )
        return Response(content=fanart_bytes, media_type=media_type)

    if image_type in {"thumb", "backdrop"}:
        content, media_type = _fetch_best_landscape_image(landscape_image_candidates(resolved_image.metadata), effective_proxy)
        return Response(content=content, media_type=media_type)

    return _stream_remote_image(resolved_image.url, effective_proxy)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((_launch_host(), 0))
        return sock.getsockname()[1]


def _launch_port() -> int:
    configured_port = os.getenv("JAVSCRAPER_PORT")
    if configured_port is None:
        return _free_port()
    try:
        port = int(configured_port)
    except ValueError as exc:
        raise ValueError("JAVSCRAPER_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError("JAVSCRAPER_PORT must be between 1 and 65535")
    return port


def _should_open_browser() -> bool:
    return os.getenv("JAVSCRAPER_DISABLE_BROWSER", "").lower() not in {"1", "true", "yes", "on"}


def _launch_host() -> str:
    return os.getenv("JAVSCRAPER_HOST", "127.0.0.1").strip() or "127.0.0.1"


def launch() -> None:
    configure_bootstrap_logging()
    _log_service("INFO", "startup", "开始启动 HTTP 服务", event="application.starting")
    host = _launch_host()
    port = _launch_port()
    browser_host = "127.0.0.1" if host == "0.0.0.0" else host
    url = f"http://{browser_host}:{port}"
    _log_launch_summary(host, port, browser_host)
    if _should_open_browser():
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
        log_config=None,
        use_colors=False,
    )
