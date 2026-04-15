from __future__ import annotations

from pathlib import Path
from typing import Any

import requests
from lxml import html

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None


DEFAULT_HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    ),
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def build_proxy_url(protocol: str, host: str, port: int | str) -> str:
    return f"{protocol}://{host}:{port}"


class HttpClient:
    def __init__(self, timeout: int = 20, proxy_url: str | None = None) -> None:
        self.timeout = timeout
        self.proxy_url = proxy_url
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def _proxies(self) -> dict[str, str] | None:
        if not self.proxy_url:
            return None
        return {
            "http": self.proxy_url,
            "https": self.proxy_url,
        }

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
    ):
        merged_headers = dict(self.session.headers)
        if headers:
            merged_headers.update(headers)

        kwargs = {
            "headers": merged_headers,
            "cookies": cookies,
            "data": data,
            "timeout": self.timeout,
            "allow_redirects": allow_redirects,
        }
        proxies = self._proxies()
        if proxies:
            kwargs["proxies"] = proxies

        if impersonate and curl_requests is not None:
            response = getattr(curl_requests, method.lower())(
                url,
                impersonate=impersonate,
                **kwargs,
            )
        else:
            response = self.session.request(method.upper(), url, **kwargs)

        if raise_for_status:
            response.raise_for_status()
        return response

    def get_document(self, url: str, **kwargs):
        response = self.request("GET", url, **kwargs)
        document = html.fromstring(response.text)
        document.make_links_absolute(str(response.url), resolve_base_href=True)
        return document, str(response.url), response

    def post_document(self, url: str, *, data: dict | None = None, **kwargs):
        response = self.request("POST", url, data=data, **kwargs)
        document = html.fromstring(response.text)
        document.make_links_absolute(str(response.url), resolve_base_href=True)
        return document, str(response.url), response

    def download(self, url: str, destination: Path, *, headers: dict | None = None) -> None:
        response = self.request("GET", url, headers=headers, raise_for_status=True)
        destination.write_bytes(response.content)

    def connectivity_check(self, url: str, *, accept_statuses: set[int] | None = None) -> dict[str, Any]:
        accept_statuses = accept_statuses or {200, 301, 302, 303, 307, 308, 401, 403}
        try:
            response = self.request("GET", url, allow_redirects=True, raise_for_status=False)
            ok = response.status_code in accept_statuses
            return {
                "ok": ok,
                "status": response.status_code,
                "finalUrl": str(response.url),
                "detail": "可访问" if ok else f"返回状态码 {response.status_code}",
            }
        except Exception as exc:
            return {
                "ok": False,
                "status": None,
                "finalUrl": url,
                "detail": str(exc),
            }
