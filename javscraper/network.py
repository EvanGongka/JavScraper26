from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import threading
import time
from typing import Any, Iterator

import requests
from lxml import html

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None

from javscraper.runtime_logging import (
    LogSettings,
    RUNTIME_METRICS,
    get_runtime_log_writer,
    redact_text,
    redact_url,
    traceback_text,
)


DEFAULT_HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    ),
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
}
RETRYABLE_STATUS_CODES = {502, 503, 504}


class UpstreamBusyError(TimeoutError):
    """Raised when all upstream request slots remain occupied until the wait timeout."""


class UpstreamRequestLimiter:
    def __init__(self, max_concurrent: int, wait_timeout: float = 30.0) -> None:
        self.max_concurrent = max(1, int(max_concurrent))
        self.wait_timeout = max(0.0, float(wait_timeout))
        self._semaphore = threading.BoundedSemaphore(self.max_concurrent)

    @contextmanager
    def slot(self, timeout: float | None = None) -> Iterator[None]:
        wait_timeout = self.wait_timeout if timeout is None else max(0.0, float(timeout))
        acquired = self._semaphore.acquire(timeout=wait_timeout)
        if not acquired:
            raise UpstreamBusyError(f"上游请求并发已达到上限，等待 {wait_timeout:g} 秒后仍未获得请求槽位")
        try:
            yield
        finally:
            self._semaphore.release()


_global_limiter: UpstreamRequestLimiter | None = None
_global_limiter_limit: int | None = None
_global_limiter_lock = threading.Lock()


def _get_global_limiter() -> UpstreamRequestLimiter:
    global _global_limiter, _global_limiter_limit
    limit = LogSettings.from_env().max_concurrent_upstream
    with _global_limiter_lock:
        if _global_limiter is None or _global_limiter_limit != limit:
            _global_limiter = UpstreamRequestLimiter(limit)
            _global_limiter_limit = limit
        return _global_limiter


def build_proxy_url(protocol: str, host: str, port: int | str) -> str:
    return f"{protocol}://{host}:{port}"


def _close_response(response: Any) -> None:
    close = getattr(response, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def _is_retryable_exception(exc: BaseException) -> bool:
    if isinstance(exc, (requests.exceptions.RequestException, TimeoutError, OSError)):
        return True
    name = type(exc).__name__.lower()
    return "timeout" in name or "connection" in name or "network" in name


class HttpClient:
    def __init__(
        self,
        timeout: int | float | tuple[float, float] | None = None,
        proxy_url: str | None = None,
        *,
        connect_timeout: float | None = None,
        read_timeout: float | None = None,
        retries: int | None = None,
        limiter: UpstreamRequestLimiter | None = None,
        upstream_wait_timeout: float | None = None,
        proxy_source: str = "unknown",
    ) -> None:
        settings = LogSettings.from_env()
        self.timeout = timeout
        self.connect_timeout = connect_timeout if connect_timeout is not None else settings.http_connect_timeout
        self.read_timeout = read_timeout if read_timeout is not None else settings.http_read_timeout
        self.retries = max(0, retries if retries is not None else settings.http_retries)
        self.proxy_url = proxy_url
        self.proxy_source = proxy_source
        self.upstream_wait_timeout = upstream_wait_timeout
        self.limiter = limiter or _get_global_limiter()
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self._closed = False

    def _proxies(self) -> dict[str, str] | None:
        if not self.proxy_url:
            return None
        return {
            "http": self.proxy_url,
            "https": self.proxy_url,
        }

    def _request_timeout(self) -> float | tuple[float, float]:
        if isinstance(self.timeout, tuple):
            return self.timeout
        if self.timeout is not None:
            return self.timeout
        return (self.connect_timeout, self.read_timeout)

    def _log(self, level: str, message: str, *, event: str, details: dict[str, Any], exc=None) -> None:
        get_runtime_log_writer().emit(
            level,
            "network",
            message,
            event=event,
            exception_type=type(exc).__name__ if exc is not None else None,
            traceback=traceback_text(exc) if exc is not None else None,
            details=details,
        )

    def _request_once(self, method: str, url: str, kwargs: dict[str, Any]):
        if kwargs.get("impersonate") and curl_requests is not None:
            impersonate = kwargs.pop("impersonate")
            return getattr(curl_requests, method.lower())(
                url,
                impersonate=impersonate,
                **kwargs,
            )
        kwargs.pop("impersonate", None)
        return self.session.request(method.upper(), url, **kwargs)

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict | None = None,
        cookies: dict | None = None,
        data: dict | None = None,
        impersonate: str | None = None,
        allow_redirects: bool = True,
        raise_for_status: bool = True,
        stream: bool = False,
    ):
        method_upper = method.upper()
        safe_retry = method_upper == "GET"
        merged_headers = dict(self.session.headers)
        if headers:
            merged_headers.update(headers)

        kwargs: dict[str, Any] = {
            "headers": merged_headers,
            "cookies": cookies,
            "data": data,
            "timeout": self._request_timeout(),
            "allow_redirects": allow_redirects,
            "stream": stream,
        }
        if impersonate:
            kwargs["impersonate"] = impersonate
        proxies = self._proxies()
        if proxies:
            kwargs["proxies"] = proxies

        safe_url = redact_url(url)
        details = {
            "method": method_upper,
            "url": safe_url,
            "proxyConfigured": bool(self.proxy_url),
            "proxySource": self.proxy_source,
            "retries": self.retries if safe_retry else 0,
        }
        RUNTIME_METRICS.upstream_started()
        started = time.perf_counter()
        try:
            with self.limiter.slot(self.upstream_wait_timeout):
                for attempt in range(self.retries + 1 if safe_retry else 1):
                    response = None
                    try:
                        response = self._request_once(method_upper, url, dict(kwargs))
                        status_code = getattr(response, "status_code", None)
                        if (
                            safe_retry
                            and status_code in RETRYABLE_STATUS_CODES
                            and attempt < self.retries
                        ):
                            _close_response(response)
                            self._log(
                                "WARN",
                                f"上游返回 {status_code}，准备重试 ({attempt + 1}/{self.retries})",
                                event="upstream.request.retry",
                                details={**details, "statusCode": status_code, "attempt": attempt + 1},
                            )
                            time.sleep(min(2.0, 0.2 * (2**attempt)))
                            continue

                        if raise_for_status:
                            response.raise_for_status()
                        if not stream:
                            # Materialize before closing so callers can still read text/json/content.
                            getattr(response, "content", b"")
                            _close_response(response)
                        elapsed_ms = (time.perf_counter() - started) * 1000
                        self._log(
                            "INFO",
                            f"上游请求完成: {method_upper} {safe_url} -> {status_code} ({elapsed_ms:.1f}ms)",
                            event="upstream.request.completed",
                            details={
                                **details,
                                "attempt": attempt + 1,
                                "statusCode": status_code,
                                "responseBytes": len(getattr(response, "content", b"") or b"") if not stream else None,
                            },
                        )
                        return response
                    except Exception as exc:
                        if response is not None:
                            _close_response(response)
                        if safe_retry and _is_retryable_exception(exc) and attempt < self.retries:
                            self._log(
                                "WARN",
                                f"上游请求失败，准备重试 ({attempt + 1}/{self.retries}): {exc}",
                                event="upstream.request.retry",
                                details={**details, "attempt": attempt + 1},
                                exc=exc,
                            )
                            time.sleep(min(2.0, 0.2 * (2**attempt)))
                            continue
                        RUNTIME_METRICS.upstream_failed()
                        elapsed_ms = (time.perf_counter() - started) * 1000
                        self._log(
                            "ERROR",
                            f"上游请求失败: {method_upper} {safe_url} ({elapsed_ms:.1f}ms): {exc}",
                            event="upstream.request.failed",
                            details={**details, "attempt": attempt + 1},
                            exc=exc,
                        )
                        raise
        except UpstreamBusyError as exc:
            RUNTIME_METRICS.upstream_failed()
            elapsed_ms = (time.perf_counter() - started) * 1000
            self._log(
                "ERROR",
                f"上游请求并发等待超时: {method_upper} {safe_url} ({elapsed_ms:.1f}ms)",
                event="upstream.request.busy",
                details=details,
                exc=exc,
            )
            raise

    def get_document(self, url: str, **kwargs):
        response = self.request("GET", url, **kwargs)
        document = html.fromstring(response.text)
        resolved_url = str(getattr(response, "url", url))
        document.make_links_absolute(resolved_url, resolve_base_href=True)
        return document, resolved_url, response

    def post_document(self, url: str, *, data: dict | None = None, **kwargs):
        response = self.request("POST", url, data=data, **kwargs)
        document = html.fromstring(response.text)
        resolved_url = str(getattr(response, "url", url))
        document.make_links_absolute(resolved_url, resolve_base_href=True)
        return document, resolved_url, response

    def download(self, url: str, destination: Path, *, headers: dict | None = None) -> None:
        response = self.request("GET", url, headers=headers, raise_for_status=True, stream=True)
        limit = LogSettings.from_env().max_image_bytes
        try:
            response_headers = getattr(response, "headers", {}) or {}
            content_length = response_headers.get("content-length")
            if content_length:
                try:
                    declared_size = int(content_length)
                except (TypeError, ValueError):
                    declared_size = 0
                if declared_size > limit:
                    raise ValueError(f"下载资源大小超过上限 {limit} 字节")

            iter_content = getattr(response, "iter_content", None)
            if callable(iter_content):
                try:
                    chunks = []
                    total = 0
                    for chunk in iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        total += len(chunk)
                        if total > limit:
                            raise ValueError(f"下载资源大小超过上限 {limit} 字节")
                        chunks.append(bytes(chunk))
                    content = b"".join(chunks)
                except TypeError:
                    content = bytes(getattr(response, "content", b"") or b"")
            else:
                content = bytes(getattr(response, "content", b"") or b"")
            if len(content) > limit:
                raise ValueError(f"下载资源大小超过上限 {limit} 字节")
            destination.write_bytes(content)
        finally:
            _close_response(response)

    def connectivity_check(self, url: str, *, accept_statuses: set[int] | None = None) -> dict[str, Any]:
        accept_statuses = accept_statuses or {200, 301, 302, 303, 307, 308, 401, 403}
        try:
            response = self.request("GET", url, allow_redirects=True, raise_for_status=False)
            status = response.status_code
            final_url = str(getattr(response, "url", url))
            ok = status in accept_statuses
            return {
                "ok": ok,
                "status": status,
                "finalUrl": final_url,
                "detail": "可访问" if ok else f"返回状态码 {status}",
            }
        except Exception as exc:
            return {
                "ok": False,
                "status": None,
                "finalUrl": url,
                "detail": redact_text(exc),
            }

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.session.close()
        except Exception:
            pass

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


__all__ = [
    "HttpClient",
    "RETRYABLE_STATUS_CODES",
    "UpstreamBusyError",
    "UpstreamRequestLimiter",
    "build_proxy_url",
]
