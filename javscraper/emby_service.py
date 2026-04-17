from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from threading import Lock
from typing import Iterable

from fastapi import HTTPException

from javscraper.images import ImageSources, select_image_sources
from javscraper.metadata_resolution import resolve_metadata_from_providers
from javscraper.models import MovieMetadata
from javscraper.network import HttpClient, build_proxy_url
from javscraper.provider_catalog import provider_names_for_code
from javscraper.providers import PROVIDER_CLASSES
from javscraper.providers.base import ProviderError
from javscraper.scanner import extract_code_from_text
from javscraper.service_logging import ServiceLogStore
from javscraper.utils.browser import get_javdb_cookie_status


@dataclass
class ProxyConfig:
    enabled: bool = False
    protocol: str = ""
    host: str = ""
    port: str = ""

    @property
    def url(self) -> str | None:
        if not self.enabled or not self.protocol or not self.host or not self.port:
            return None
        return build_proxy_url(self.protocol, self.host, self.port)

    def to_query_params(self) -> dict[str, str]:
        return {
            "proxyEnabled": "true" if self.enabled else "false",
            "proxyProtocol": self.protocol,
            "proxyHost": self.host,
            "proxyPort": self.port,
        }


def proxy_from_query(
    proxy_enabled: str | None,
    proxy_protocol: str | None,
    proxy_host: str | None,
    proxy_port: str | None,
) -> ProxyConfig:
    enabled = str(proxy_enabled or "").strip().lower() in {"1", "true", "yes", "on"}
    return ProxyConfig(
        enabled=enabled,
        protocol=(proxy_protocol or "").strip(),
        host=(proxy_host or "").strip(),
        port=(proxy_port or "").strip(),
    )


def default_proxy_from_env() -> ProxyConfig:
    return ProxyConfig(
        enabled=str(os.getenv("JAVSCRAPER_PROXY_ENABLED", "")).lower() in {"1", "true", "yes", "on"},
        protocol=os.getenv("JAVSCRAPER_PROXY_PROTOCOL", "").strip(),
        host=os.getenv("JAVSCRAPER_PROXY_HOST", "").strip(),
        port=os.getenv("JAVSCRAPER_PROXY_PORT", "").strip(),
    )


@dataclass
class ResolvedMovie:
    provider: str
    provider_item_id: str
    code: str
    metadata: MovieMetadata


@dataclass(frozen=True)
class ResolvedImage:
    image_type: str
    url: str
    metadata: MovieMetadata
    sources: ImageSources


def _path_candidates(raw_path: str | None) -> list[str]:
    if not raw_path:
        return []
    candidates: list[str] = []
    for path_cls in (PureWindowsPath, PurePosixPath):
        pure = path_cls(raw_path)
        parts = [part for part in pure.parts if part not in {"/", "\\"}]
        if pure.name:
            candidates.append(pure.stem or pure.name)
        if len(parts) >= 2:
            candidates.append(parts[-2])
    fallback_parts = [part for part in re.split(r"[\\/]+", raw_path) if part]
    if fallback_parts:
        candidates.append(Path(fallback_parts[-1]).stem)
    if len(fallback_parts) >= 2:
        candidates.append(fallback_parts[-2])
    deduped: list[str] = []
    for candidate in candidates:
        text = candidate.strip()
        if text and text not in deduped:
            deduped.append(text)
    return deduped


def extract_emby_code(name: str | None, path: str | None) -> str | None:
    for candidate in _path_candidates(path) + [name or ""]:
        code = extract_code_from_text(candidate)
        if code:
            return code
    return None


class EmbyMovieService:
    def __init__(
        self,
        provider_names: Iterable[str],
        log_store: ServiceLogStore,
        default_proxy: ProxyConfig | None = None,
    ) -> None:
        self.provider_names = list(provider_names)
        self.log_store = log_store
        self.default_proxy = default_proxy or ProxyConfig()
        self._metadata_cache: dict[tuple[str, str], MovieMetadata] = {}
        self._cache_lock = Lock()

    def javdb_available(self) -> bool:
        if "JavDB" not in self.provider_names:
            return False
        return bool(get_javdb_cookie_status()["available"])

    def effective_proxy(self, requested_proxy: ProxyConfig | None) -> ProxyConfig:
        if requested_proxy and requested_proxy.url:
            return requested_proxy
        return self.default_proxy

    def resolve_movie(
        self,
        *,
        name: str | None,
        path: str | None,
        year: int | None,
        requested_proxy: ProxyConfig | None,
    ) -> dict[str, object]:
        code = extract_emby_code(name, path)
        query_info = {
            "name": name or "",
            "path": path or "",
            "year": year,
            "code": code or "",
        }
        if not code:
            self.log_store.add("WARN", "emby-resolve", f"未能从 Emby 条目中识别番号: name={name!r} path={path!r}")
            return {"query": query_info, "results": []}

        resolved = self.fetch_from_providers(code, requested_proxy=requested_proxy)
        if resolved is None:
            self.log_store.add("WARN", "emby-resolve", f"[{code}] 所有站点都未返回可用元数据")
            return {"query": query_info, "results": []}

        return {"query": query_info, "results": [self.serialize_movie(resolved)]}

    def get_movie(self, provider: str, provider_item_id: str, requested_proxy: ProxyConfig | None) -> dict[str, object]:
        resolved = self.fetch_by_provider(provider, provider_item_id, requested_proxy=requested_proxy)
        return self.serialize_movie(resolved)

    def get_image(
        self,
        image_type: str,
        provider: str,
        provider_item_id: str,
        requested_proxy: ProxyConfig | None,
    ) -> ResolvedImage:
        resolved = self.fetch_by_provider(provider, provider_item_id, requested_proxy=requested_proxy)
        metadata = resolved.metadata
        sources = select_image_sources(metadata)
        if image_type == "primary":
            image_url = sources.poster_url or sources.fanart_url
        elif image_type == "thumb":
            image_url = sources.fanart_url
        elif image_type == "backdrop":
            image_url = sources.fanart_url
        else:
            raise HTTPException(status_code=400, detail="未知图片类型")
        if not image_url:
            raise HTTPException(status_code=404, detail="该条目没有可用图片")
        return ResolvedImage(
            image_type=image_type,
            url=image_url,
            metadata=metadata,
            sources=sources,
        )

    def fetch_by_provider(
        self,
        provider: str,
        provider_item_id: str,
        *,
        requested_proxy: ProxyConfig | None,
    ) -> ResolvedMovie:
        cache_key = (provider, provider_item_id)
        with self._cache_lock:
            cached = self._metadata_cache.get(cache_key)
        if cached is not None:
            return ResolvedMovie(
                provider=provider,
                provider_item_id=provider_item_id,
                code=cached.code,
                metadata=cached,
            )

        provider_cls = PROVIDER_CLASSES.get(provider)
        if provider_cls is None:
            raise HTTPException(status_code=404, detail=f"未知 provider: {provider}")

        proxy = self.effective_proxy(requested_proxy)
        client = HttpClient(proxy_url=proxy.url)
        provider_instance = provider_cls(client)
        self.log_store.add("INFO", "emby-fetch", f"[{provider_item_id}] 指定站点抓取: {provider}")
        try:
            metadata = provider_instance.fetch(provider_item_id)
        except ProviderError as exc:
            self.log_store.add("WARN", "emby-fetch", f"[{provider_item_id}] {provider} 失败: {exc}")
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive
            self.log_store.add("ERROR", "emby-fetch", f"[{provider_item_id}] {provider} 异常: {exc}")
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        if provider not in metadata.providers:
            metadata.providers.append(provider)
        with self._cache_lock:
            self._metadata_cache[cache_key] = metadata
        return ResolvedMovie(
            provider=provider,
            provider_item_id=provider_item_id,
            code=metadata.code,
            metadata=metadata,
        )

    def fetch_from_providers(self, code: str, *, requested_proxy: ProxyConfig | None) -> ResolvedMovie | None:
        proxy = self.effective_proxy(requested_proxy)
        client = HttpClient(proxy_url=proxy.url)
        provider_names = provider_names_for_code(
            code,
            self.provider_names,
            javdb_available=self.javdb_available(),
        )
        providers = [PROVIDER_CLASSES[name](client) for name in provider_names]
        self.log_store.add("INFO", "emby-resolve", f"[{code}] 站点顺序: {' -> '.join(provider_names)}")
        resolved_metadata = resolve_metadata_from_providers(
            code,
            providers,
            probe_client=client,
            on_info=lambda message: self.log_store.add("INFO", "emby-resolve", message),
            on_warn=lambda message: self.log_store.add("WARN", "emby-resolve", message),
            on_error=lambda message: self.log_store.add("ERROR", "emby-resolve", message),
        )
        if resolved_metadata is None:
            return None
        metadata = resolved_metadata.metadata
        resolved = ResolvedMovie(
            provider=resolved_metadata.provider,
            provider_item_id=metadata.code,
            code=metadata.code,
            metadata=metadata,
        )
        with self._cache_lock:
            self._metadata_cache[(resolved.provider, resolved.provider_item_id)] = metadata
        return resolved

    @staticmethod
    def serialize_movie(resolved: ResolvedMovie) -> dict[str, object]:
        metadata = resolved.metadata
        sources = select_image_sources(metadata)
        return {
            "provider": resolved.provider,
            "providerItemId": resolved.provider_item_id,
            "number": metadata.code,
            "title": metadata.title or metadata.code,
            "originalTitle": metadata.original_title or metadata.title or metadata.code,
            "summary": metadata.description or "",
            "releaseDate": metadata.release_date or "",
            "durationMinutes": metadata.duration_minutes or "",
            "director": metadata.director or "",
            "maker": metadata.maker or "",
            "publisher": metadata.publisher or "",
            "series": metadata.series or "",
            "score": metadata.score or "",
            "actors": list(metadata.actresses),
            "genres": list(metadata.genres),
            "coverUrl": sources.poster_url or sources.fanart_url or "",
            "thumbUrl": sources.fanart_url or "",
            "fanartUrl": sources.fanart_url or "",
            "previewImages": list(metadata.preview_images),
            "trailerUrl": metadata.trailer_url or "",
            "detailUrl": metadata.detail_url or "",
        }
