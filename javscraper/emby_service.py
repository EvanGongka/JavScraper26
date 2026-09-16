from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterable

from fastapi import HTTPException

from javscraper.images import ImageSources, select_image_sources
from javscraper.metadata_resolution import resolve_metadata_from_providers
from javscraper.models import MovieMetadata
from javscraper.network import HttpClient, build_proxy_url
from javscraper.output import format_nfo_title
from javscraper.provider_catalog import provider_names_for_code
from javscraper.providers import PROVIDER_CLASSES
from javscraper.providers.base import ProviderError
from javscraper.runtime_cache import TtlLruCache
from javscraper.runtime_logging import LogSettings, RUNTIME_METRICS, redact_text, traceback_text
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
        settings = LogSettings.from_env()
        self._metadata_cache: TtlLruCache[tuple[str, str], MovieMetadata] = TtlLruCache(
            settings.metadata_cache_max_entries,
            settings.metadata_cache_ttl_seconds,
        )

    def javdb_available(self) -> bool:
        if "JavDB" not in self.provider_names:
            return False
        try:
            return bool(get_javdb_cookie_status()["available"])
        except Exception as exc:  # pragma: no cover - browser integration varies by host
            self.log_store.add(
                "WARN",
                "emby-config",
                f"JavDB 登录态检查失败，已跳过: {exc}",
                event="emby.javdb.cookie_check_failed",
                exception_type=type(exc).__name__,
                traceback=traceback_text(exc),
            )
            return False

    def cache_stats(self) -> dict[str, int]:
        return self._metadata_cache.stats()

    def _cache_store(self, key: tuple[str, str], metadata: MovieMetadata, *, provider: str) -> None:
        evicted = self._metadata_cache.set(key, metadata)
        if evicted:
            RUNTIME_METRICS.cache_evicted(evicted)
            self.log_store.add(
                "INFO",
                "emby-cache",
                f"缓存淘汰 {evicted} 条元数据",
                event="emby.cache.evicted",
                provider=provider,
                code=metadata.code,
                details=self.cache_stats(),
            )

    def _proxy_source(self, requested_proxy: ProxyConfig | None) -> str:
        if requested_proxy and requested_proxy.url:
            return "plugin_request"
        if self.default_proxy.url:
            return "service_default"
        return "disabled"

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
        self.log_store.add(
            "INFO",
            "emby-image",
            f"[{provider_item_id}] 已解析图片地址: {image_type}",
            event="emby.image.resolved",
            code=metadata.code,
            provider=provider,
            details={"imageType": image_type, "url": image_url},
        )
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
        cached = self._metadata_cache.get(cache_key)
        if cached is not None:
            RUNTIME_METRICS.cache_hit()
            self.log_store.add(
                "INFO",
                "emby-cache",
                f"[{provider_item_id}] 命中元数据缓存",
                event="emby.cache.hit",
                code=cached.code,
                provider=provider,
                details=self.cache_stats(),
            )
            return ResolvedMovie(
                provider=provider,
                provider_item_id=provider_item_id,
                code=cached.code,
                metadata=cached,
            )
        RUNTIME_METRICS.cache_miss()
        self.log_store.add(
            "DEBUG",
            "emby-cache",
            f"[{provider_item_id}] 未命中元数据缓存",
            event="emby.cache.miss",
            code=provider_item_id,
            provider=provider,
            details=self.cache_stats(),
        )

        provider_cls = PROVIDER_CLASSES.get(provider)
        if provider_cls is None:
            raise HTTPException(status_code=404, detail=f"未知 provider: {provider}")

        proxy = self.effective_proxy(requested_proxy)
        client = HttpClient(proxy_url=proxy.url, proxy_source=self._proxy_source(requested_proxy))
        provider_instance = provider_cls(client)
        started = time.perf_counter()
        self.log_store.add(
            "INFO",
            "emby-fetch",
            f"[{provider_item_id}] 指定站点抓取: {provider}",
            event="emby.provider.fetch_started",
            code=provider_item_id,
            provider=provider,
            details={"proxySource": self._proxy_source(requested_proxy)},
        )
        try:
            metadata = provider_instance.fetch(provider_item_id)
        except ProviderError as exc:
            RUNTIME_METRICS.upstream_failed()
            self.log_store.add(
                "WARN",
                "emby-fetch",
                f"[{provider_item_id}] {provider} 失败: {exc}",
                event="emby.provider.fetch_failed",
                code=provider_item_id,
                provider=provider,
                duration_ms=(time.perf_counter() - started) * 1000,
                exception_type=type(exc).__name__,
            )
            raise HTTPException(status_code=404, detail=redact_text(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive
            RUNTIME_METRICS.upstream_failed()
            self.log_store.add(
                "ERROR",
                "emby-fetch",
                f"[{provider_item_id}] {provider} 异常: {exc}",
                event="emby.provider.fetch_exception",
                code=provider_item_id,
                provider=provider,
                duration_ms=(time.perf_counter() - started) * 1000,
                exception_type=type(exc).__name__,
                traceback=traceback_text(exc),
            )
            raise HTTPException(status_code=502, detail=redact_text(exc)) from exc
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

        if provider not in metadata.providers:
            metadata.providers.append(provider)
        self._cache_store(cache_key, metadata, provider=provider)
        self.log_store.add(
            "INFO",
            "emby-fetch",
            f"[{provider_item_id}] {provider} 抓取完成",
            event="emby.provider.fetch_completed",
            code=metadata.code,
            provider=provider,
            duration_ms=(time.perf_counter() - started) * 1000,
            details={"cache": self.cache_stats()},
        )
        return ResolvedMovie(
            provider=provider,
            provider_item_id=provider_item_id,
            code=metadata.code,
            metadata=metadata,
        )

    def fetch_from_providers(self, code: str, *, requested_proxy: ProxyConfig | None) -> ResolvedMovie | None:
        proxy = self.effective_proxy(requested_proxy)
        started = time.perf_counter()
        client = HttpClient(proxy_url=proxy.url, proxy_source=self._proxy_source(requested_proxy))
        try:
            provider_names = provider_names_for_code(
                code,
                self.provider_names,
                javdb_available=self.javdb_available(),
            )
            for provider_name in provider_names:
                for cache_code in dict.fromkeys((code, code.upper())):
                    cached = self._metadata_cache.get((provider_name, cache_code))
                    if cached is None:
                        continue
                    RUNTIME_METRICS.cache_hit()
                    self.log_store.add(
                        "INFO",
                        "emby-cache",
                        f"[{code}] 解析命中元数据缓存: {provider_name}",
                        event="emby.cache.resolve_hit",
                        code=cached.code,
                        provider=provider_name,
                        duration_ms=(time.perf_counter() - started) * 1000,
                        details=self.cache_stats(),
                    )
                    return ResolvedMovie(
                        provider=provider_name,
                        provider_item_id=cached.code,
                        code=cached.code,
                        metadata=cached,
                    )
            providers = [PROVIDER_CLASSES[name](client) for name in provider_names]
            self.log_store.add(
                "INFO",
                "emby-resolve",
                f"[{code}] 站点顺序: {' -> '.join(provider_names)}",
                event="emby.resolve.started",
                code=code,
                details={
                    "providerCount": len(provider_names),
                    "proxySource": self._proxy_source(requested_proxy),
                },
            )
            resolved_metadata = resolve_metadata_from_providers(
                code,
                providers,
                probe_client=client,
                on_info=lambda message: self.log_store.add("INFO", "emby-resolve", message, code=code),
                on_warn=lambda message: self.log_store.add("WARN", "emby-resolve", message, code=code),
                on_error=lambda message: self.log_store.add("ERROR", "emby-resolve", message, code=code),
                on_exception=lambda provider, exc: self.log_store.add(
                    "ERROR",
                    "emby-resolve",
                    f"[{code}] {provider} 异常堆栈已记录: {exc}",
                    event="emby.provider.fetch_exception",
                    code=code,
                    provider=provider,
                    exception_type=type(exc).__name__,
                    traceback=traceback_text(exc),
                ),
            )
            if resolved_metadata is None:
                self.log_store.add(
                    "WARN",
                    "emby-resolve",
                    f"[{code}] 所有站点都未返回可用元数据",
                    event="emby.resolve.empty",
                    code=code,
                    duration_ms=(time.perf_counter() - started) * 1000,
                )
                return None
            metadata = resolved_metadata.metadata
            resolved = ResolvedMovie(
                provider=resolved_metadata.provider,
                provider_item_id=metadata.code,
                code=metadata.code,
                metadata=metadata,
            )
            self._cache_store(
                (resolved.provider, resolved.provider_item_id),
                metadata,
                provider=resolved.provider,
            )
            self.log_store.add(
                "INFO",
                "emby-resolve",
                f"[{code}] 元数据解析完成: {resolved.provider}",
                event="emby.resolve.completed",
                code=metadata.code,
                provider=resolved.provider,
                duration_ms=(time.perf_counter() - started) * 1000,
                details={"cache": self.cache_stats()},
            )
            return resolved
        except Exception as exc:  # pragma: no cover - defensive boundary for provider integrations
            RUNTIME_METRICS.upstream_failed()
            self.log_store.add(
                "ERROR",
                "emby-resolve",
                f"[{code}] 解析异常，已保护服务进程: {exc}",
                event="emby.resolve.exception",
                code=code,
                duration_ms=(time.perf_counter() - started) * 1000,
                exception_type=type(exc).__name__,
                traceback=traceback_text(exc),
            )
            return None
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

    @staticmethod
    def serialize_movie(resolved: ResolvedMovie) -> dict[str, object]:
        metadata = resolved.metadata
        sources = select_image_sources(metadata)
        return {
            "provider": resolved.provider,
            "providerItemId": resolved.provider_item_id,
            "number": metadata.code,
            "title": format_nfo_title(metadata),
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
