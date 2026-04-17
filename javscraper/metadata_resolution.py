from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from javscraper.images import POSTER_MIN_HEIGHT, poster_image_candidates, preferred_regular_crop_urls, select_best_regular_poster_for_metadata, select_dmm_regular_poster_for_code, should_crop_poster_from_fanart
from javscraper.models import MovieMetadata
from javscraper.network import HttpClient
from javscraper.providers.base import Provider, ProviderError

InfoLogger = Callable[[str], None]


@dataclass(frozen=True)
class ResolvedMetadata:
    metadata: MovieMetadata
    provider: str


def _emit(logger: InfoLogger | None, message: str) -> None:
    if logger:
        logger(message)


def resolve_metadata_from_providers(
    code: str,
    providers: Iterable[Provider],
    *,
    probe_client: HttpClient,
    on_info: InfoLogger | None = None,
    on_warn: InfoLogger | None = None,
    on_error: InfoLogger | None = None,
) -> ResolvedMetadata | None:
    metadata = MovieMetadata(code=code)
    matched_provider: str | None = None
    needs_poster_supplement = False
    dmm_locked_poster = None

    if should_crop_poster_from_fanart(code):
        dmm_locked_poster = select_dmm_regular_poster_for_code(
            probe_client,
            code,
            on_log=on_info,
        )
        if dmm_locked_poster is not None:
            metadata.locked_regular_poster_url = dmm_locked_poster.url
            _emit(
                on_info,
                f"[{code}] 预检命中 DMM poster 横图 {dmm_locked_poster.width}x{dmm_locked_poster.height}，后续将直接使用该图裁切 poster",
            )

    for provider in providers:
        _emit(on_info, f"[{code}] 尝试站点: {provider.site_name}")
        try:
            fetched = provider.fetch(code)
        except ProviderError as exc:
            _emit(on_warn, f"[{code}] {provider.site_name} 失败: {exc}")
            continue
        except Exception as exc:
            _emit(on_error, f"[{code}] {provider.site_name} 异常: {exc}")
            continue

        if not fetched.is_usable:
            _emit(on_warn, f"[{code}] {provider.site_name} 命中但字段不完整")
            continue

        provider_candidates: list[str] = []
        regular_code = should_crop_poster_from_fanart(fetched.code or code)
        if regular_code:
            provider_candidates = poster_image_candidates(fetched)

        if matched_provider is None:
            metadata.code = fetched.code or metadata.code
            metadata.merge_missing(fetched, provider.site_name)
            matched_provider = provider.site_name
            metadata.add_regular_poster_crop_urls(preferred_regular_crop_urls(fetched))

            if not regular_code:
                _emit(on_info, f"[{code}] 命中站点: {provider.site_name}")
                return ResolvedMetadata(metadata=metadata, provider=matched_provider)

            if metadata.locked_regular_poster_url:
                _emit(
                    on_info,
                    f"[{code}] 命中站点: {provider.site_name}，poster 已在预检阶段锁定为 DMM 图源，停止继续尝试后续站点",
                )
                return ResolvedMetadata(metadata=metadata, provider=matched_provider)

            selected = select_best_regular_poster_for_metadata(
                probe_client,
                fetched,
                min_height=POSTER_MIN_HEIGHT,
                on_log=on_info,
            )
            if selected and selected.mode == "regular_crop":
                _emit(
                    on_info,
                    f"[{code}] 命中站点: {provider.site_name}，已找到可直接裁切的横图 {selected.width}x{selected.height}",
                )
                return ResolvedMetadata(metadata=metadata, provider=matched_provider)
            if provider_candidates:
                metadata.add_native_poster_urls(provider_candidates)
            if selected and selected.mode == "native" and selected.meets_threshold:
                _emit(
                    on_info,
                    f"[{code}] 命中站点: {provider.site_name}，原生 poster 达标 {selected.width}x{selected.height}",
                )
                return ResolvedMetadata(metadata=metadata, provider=matched_provider)

            _emit(on_info, f"[{code}] 命中主站点: {provider.site_name}")
            if selected and selected.mode == "native":
                _emit(
                    on_info,
                    f"[{code}] {provider.site_name} 原生 poster 低于阈值 {selected.width}x{selected.height}，继续补充后续站点",
                )
            else:
                _emit(on_info, f"[{code}] {provider.site_name} 未找到可直接裁切横图或可用原生竖图，继续补充后续站点")
            needs_poster_supplement = True
            continue

        if not needs_poster_supplement:
            break

        _emit(on_info, f"[{code}] {provider.site_name} 仅用于补充原生 poster 候选")
        metadata.add_regular_poster_crop_urls(preferred_regular_crop_urls(fetched))

        selected = select_best_regular_poster_for_metadata(
            probe_client,
            fetched,
            min_height=POSTER_MIN_HEIGHT,
            on_log=on_info,
        )
        if selected and selected.mode == "regular_crop":
            _emit(
                on_info,
                f"[{code}] {provider.site_name} 提供可直接裁切横图 {selected.width}x{selected.height}，停止继续尝试后续站点",
            )
            return ResolvedMetadata(metadata=metadata, provider=matched_provider)
        if provider_candidates:
            metadata.add_native_poster_urls(provider_candidates)
        if selected and selected.mode == "native" and selected.meets_threshold:
            _emit(
                on_info,
                f"[{code}] {provider.site_name} 提供达标原生 poster {selected.width}x{selected.height}，停止继续尝试后续站点",
            )
            return ResolvedMetadata(metadata=metadata, provider=matched_provider)
        if selected and selected.mode == "native":
            _emit(
                on_info,
                f"[{code}] {provider.site_name} 原生 poster 未达阈值 {selected.width}x{selected.height}，继续尝试后续站点",
            )
        else:
            _emit(on_info, f"[{code}] {provider.site_name} 未提供可直接裁切横图或可用原生竖图，继续尝试后续站点")

    if matched_provider is None:
        return None
    return ResolvedMetadata(metadata=metadata, provider=matched_provider)
