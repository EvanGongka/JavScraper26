from __future__ import annotations

import os
import socket
import sys
import threading
import uuid
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from javscraper.network import HttpClient, build_proxy_url
from javscraper.pipeline import ScrapePipeline
from javscraper.scanner import scan_directory
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

    def to_dict(self) -> dict:
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


class ScanRequest(BaseModel):
    sourcePath: str


class PickRequest(BaseModel):
    title: str


class StartRequest(BaseModel):
    sourcePath: str
    outputPath: str
    providers: list[str]
    proxy: Optional[Dict[str, Any]] = None


class ConnectivityRequest(BaseModel):
    proxy: Optional[Dict[str, Any]] = None
    sites: Optional[list[str]] = None


app = FastAPI(title="javScraper26")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/providers")
def get_providers():
    javdb_status = get_javdb_cookie_status()
    return {
        "providers": [
            {
                "name": name,
                "requiresLogin": name == "JavDB",
                "hint": (
                    javdb_status["reason"]
                    if name == "JavDB"
                    else ""
                ),
                "defaultEnabled": (
                    bool(javdb_status["available"])
                    if name == "JavDB"
                    else True
                ),
            }
            for name in DEFAULT_SITES
        ]
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
    except Exception as exc:
        task.append_log(f"任务异常: {exc}")
        task.finish(error=str(exc))


def _proxy_url_from_payload(proxy: Optional[Dict[str, Any]]) -> Optional[str]:
    if not proxy:
        return None
    enabled = proxy.get("enabled", False)
    protocol = str(proxy.get("protocol", "")).strip()
    host = str(proxy.get("host", "")).strip()
    port = str(proxy.get("port", "")).strip()
    if not enabled or not protocol or not host or not port:
        return None
    return build_proxy_url(protocol, host, port)


def _connectivity_result_for(client: HttpClient, name: str, url: str) -> Dict[str, Any]:
    check = client.connectivity_check(url)
    return {
        "name": name,
        "url": url,
        "ok": check["ok"],
        "status": check["status"],
        "detail": check["detail"],
        "finalUrl": check["finalUrl"],
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
    results = [_connectivity_result_for(client, name, url) for name, url in site_items]
    return {"results": results}


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
    proxy_url = _proxy_url_from_payload(payload.proxy)

    task_id = uuid.uuid4().hex[:12]
    task = TaskState(
        task_id=task_id,
        source_path=str(source),
        output_path=str(output),
        providers=payload.providers,
    )
    task.proxy_url = proxy_url
    TASKS[task_id] = task
    threading.Thread(target=_run_task, args=(task,), daemon=True).start()
    return {"taskId": task_id}


@app.get("/api/tasks/{task_id}")
def api_task(task_id: str):
    task = TASKS.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task.to_dict()


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
