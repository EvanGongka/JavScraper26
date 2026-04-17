from __future__ import annotations

import os
import socket
import sys
import threading
import time
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
from javscraper.images import crop_to_poster, download_image_bytes, is_portrait_image, should_crop_poster_from_fanart
from javscraper.network import HttpClient
from javscraper.pipeline import ScrapePipeline
from javscraper.scanner import scan_directory
from javscraper.service_logging import ServiceLogStore
from javscraper.utils.browser import get_javdb_cookie_status
from javscraper.utils.dialogs import pick_directory


DEFAULT_SITES = [
    "JavBus",
    "JavBooks",
    "AVBASE",
    "JAV321",
    "FC2",
    "Caribbeancom",
    "CaribbeancomPR",
    "HEYZO",
    "HeyDouga",
    "1Pondo",
    "10musume",
    "PACOPACOMAMA",
    "MURAMURA",
    "AVMOO",
    "FreeJavBT",
    "JavDB",
]

if getattr(sys, "frozen", False):
    BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

WEB_DIR = BASE_DIR / "webui"
SITE_CONNECTIVITY_TARGETS = {
    "JavBus": "https://www.javbus.com",
    "JavBooks": "https://javbooks.com",
    "AVBASE": "https://www.avbase.net",
    "JAV321": "https://www.jav321.com",
    "FC2": "https://adult.contents.fc2.com",
    "Caribbeancom": "https://www.caribbeancom.com",
    "CaribbeancomPR": "https://www.caribbeancompr.com",
    "HEYZO": "https://www.heyzo.com",
    "HeyDouga": "https://www.heydouga.com",
    "1Pondo": "https://www.1pondo.tv",
    "10musume": "https://www.10musume.com",
    "PACOPACOMAMA": "https://www.pacopacomama.com",
    "MURAMURA": "https://www.muramura.tv",
    "AVMOO": "https://avmoo.website",
    "FreeJavBT": "https://freejavbt.com",
    "JavDB": "https://javdb.com",
}
IGNORED_SERVICE_LOG_PATHS = {
    "/emby-api/v1/health",
    "/emby-api/v1/logs/recent",
}


@dataclass
class TaskState:
    task_id: str
    source_path: str
    output_path: str
    providers: list[str]
    proxy_url: str | None = None
    status: str = "running"
    logs: list[str] = field(default_factory=list)
    entries: dict[str, str] = field(default_factory=dict)
    manifest_path: str | None = None
    error: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def append_log(self, text: str) -> None:
        with self.lock:
            self.logs.append(text)

    def set_entry_status(self, code: str, status: str) -> None:
        with self.lock:
            self.entries[code] = status

    def finish(self, manifest_path: str | None = None, error: str | None = None) -> None:
        with self.lock:
            self.status = "failed" if error else "completed"
            self.manifest_path = manifest_path
            self.error = error

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
SERVICE_LOGS = ServiceLogStore()
EMBY_SERVICE = EmbyMovieService(
    provider_names=DEFAULT_SITES,
    log_store=SERVICE_LOGS,
    default_proxy=default_proxy_from_env(),
)


class ScanRequest(BaseModel):
    sourcePath: str


class PickRequest(BaseModel):
    title: str


class StartRequest(BaseModel):
    sourcePath: str
    outputPath: str
    providers: list[str]
    proxy: Optional[dict[str, Any]] = None


class ConnectivityRequest(BaseModel):
    proxy: Optional[dict[str, Any]] = None
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


def _log_service(level: str, source: str, message: str) -> None:
    SERVICE_LOGS.add(level, source, message)


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
    javdb_status = get_javdb_cookie_status()
    return [
        {
            "name": name,
            "requiresLogin": name == "JavDB",
            "hint": javdb_status["reason"] if name == "JavDB" else "",
            "defaultEnabled": bool(javdb_status["available"]) if name == "JavDB" else True,
        }
        for name in DEFAULT_SITES
    ]


def _run_task(task: TaskState) -> None:
    try:
        entries, _ = scan_directory(task.source_path)
        for entry in entries:
            task.set_entry_status(entry.code, "待处理")

        pipeline = ScrapePipeline(
            output_root=task.output_path,
            provider_names=task.providers,
            on_log=task.append_log,
            on_status=task.set_entry_status,
            proxy_url=task.proxy_url,
        )
        manifest = pipeline.run(entries)
        task.finish(str(manifest))
    except Exception as exc:  # pragma: no cover - existing task mode safeguard
        task.append_log(f"任务异常: {exc}")
        task.finish(error=str(exc))


def _fetch_remote_image(url: str, proxy: ProxyConfig) -> tuple[bytes, str]:
    client = HttpClient(timeout=20, proxy_url=proxy.url)
    try:
        return download_image_bytes(client, url)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"图片下载失败: {exc}") from exc


def _stream_remote_image(url: str, proxy: ProxyConfig) -> Response:
    content, media_type = _fetch_remote_image(url, proxy)
    return Response(content=content, media_type=media_type)


def _fetch_best_landscape_image(urls: list[str | None], proxy: ProxyConfig) -> tuple[bytes, str]:
    fallback: tuple[bytes, str] | None = None
    seen: set[str] = set()
    for url in urls:
        if not url or url in seen:
            continue
        seen.add(url)
        content, media_type = _fetch_remote_image(url, proxy)
        if fallback is None:
            fallback = (content, media_type)
        if not is_portrait_image(content):
            return content, media_type
    if fallback is not None:
        return fallback
    raise HTTPException(status_code=404, detail="该条目没有可用图片")


@app.middleware("http")
async def service_request_logger(request: Request, call_next):
    should_log = request.url.path.startswith("/emby-api/") and request.url.path not in IGNORED_SERVICE_LOG_PATHS
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        if should_log:
            elapsed_ms = (time.perf_counter() - started) * 1000
            _log_service(
                "ERROR",
                "emby-http",
                f"{request.method} {request.url.path} -> 500 ({elapsed_ms:.1f}ms) {exc}",
            )
        raise
    if should_log:
        elapsed_ms = (time.perf_counter() - started) * 1000
        _log_service(
            "INFO",
            "emby-http",
            f"{request.method} {request.url.path} -> {response.status_code} ({elapsed_ms:.1f}ms)",
        )
    return response


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
    client = HttpClient(timeout=8, proxy_url=proxy_url)
    if payload.sites:
        unknown_sites = [name for name in payload.sites if name not in SITE_CONNECTIVITY_TARGETS]
        if unknown_sites:
            raise HTTPException(status_code=400, detail=f"未知站点: {', '.join(unknown_sites)}")
        site_items = [(name, SITE_CONNECTIVITY_TARGETS[name]) for name in payload.sites]
    else:
        site_items = list(SITE_CONNECTIVITY_TARGETS.items())
    return {"results": [_connectivity_result_for(client, name, url) for name, url in site_items]}


@app.post("/api/connectivity/{site_name}")
def api_connectivity_single(site_name: str, payload: ConnectivityRequest):
    if site_name not in SITE_CONNECTIVITY_TARGETS:
        raise HTTPException(status_code=404, detail="未知站点")
    proxy_url = _proxy_url_from_payload(payload.proxy)
    client = HttpClient(timeout=8, proxy_url=proxy_url)
    return _connectivity_result_for(client, site_name, SITE_CONNECTIVITY_TARGETS[site_name])


@app.post("/api/start")
def api_start(payload: StartRequest):
    source = Path(payload.sourcePath).expanduser()
    output = Path(payload.outputPath).expanduser()
    if not source.is_dir():
        raise HTTPException(status_code=400, detail="扫描目录不存在")
    if not payload.providers:
        raise HTTPException(status_code=400, detail="至少选择一个站点")

    task_id = uuid.uuid4().hex[:12]
    task = TaskState(
        task_id=task_id,
        source_path=str(source),
        output_path=str(output),
        providers=payload.providers,
        proxy_url=_proxy_url_from_payload(payload.proxy),
    )
    TASKS[task_id] = task
    threading.Thread(target=_run_task, args=(task,), daemon=True).start()
    return {"taskId": task_id}


@app.get("/api/tasks/{task_id}")
def api_task(task_id: str):
    task = TASKS.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task.to_dict()


@app.get("/emby-api/v1/health")
def emby_health():
    return {
        "status": "ok",
        "mode": "service",
        "defaultProxyConfigured": bool(EMBY_SERVICE.default_proxy.url),
        "providerCount": len(DEFAULT_SITES),
        "logCount": len(SERVICE_LOGS.recent()),
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
        fanart_url = resolved_image.sources.fanart_url
        if not fanart_url:
            raise HTTPException(status_code=404, detail="该条目没有可用图片")
        fanart_bytes, media_type = _fetch_remote_image(fanart_url, effective_proxy)
        if should_crop_poster_from_fanart(resolved_image.metadata.code):
            return Response(content=crop_to_poster(fanart_bytes), media_type="image/jpeg")
        return Response(content=fanart_bytes, media_type=media_type)

    if image_type in {"thumb", "backdrop"}:
        content, media_type = _fetch_best_landscape_image(
            [
                resolved_image.sources.thumb_url if image_type == "thumb" else resolved_image.sources.fanart_url,
                resolved_image.metadata.preview_images[0] if resolved_image.metadata.preview_images else None,
                resolved_image.metadata.cover_url,
            ],
            effective_proxy,
        )
        return Response(content=content, media_type=media_type)

    return _stream_remote_image(resolved_image.url, effective_proxy)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
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


def launch() -> None:
    port = _launch_port()
    url = f"http://127.0.0.1:{port}"
    if _should_open_browser():
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
        log_config=None,
        use_colors=False,
    )
