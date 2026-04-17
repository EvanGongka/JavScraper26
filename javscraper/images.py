from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import re
from urllib.parse import urlparse

from PIL import Image, ImageOps

from javscraper.models import MovieMetadata
from javscraper.network import HttpClient

POSTER_RATIO = 2.0 / 3.0
POSTER_MIN_HEIGHT = 480


@dataclass(frozen=True)
class ImageSources:
    poster_url: str | None
    fanart_url: str | None
    thumb_url: str | None


@dataclass(frozen=True)
class SelectedNativePoster:
    url: str
    image_bytes: bytes
    media_type: str
    width: int
    height: int
    meets_threshold: bool


@dataclass(frozen=True)
class SelectedRegularPoster:
    url: str
    image_bytes: bytes
    media_type: str
    width: int
    height: int
    mode: str
    meets_threshold: bool = False


_REGULAR_CODE_RE = re.compile(r"^[A-Z]{2,10}-\d{2,6}[A-Z]?$")
_DATE_CODE_RE = re.compile(r"^\d{6}-\d{2,3}$")
_SPECIAL_PREFIXES = {
    "FC2",
    "HEYZO",
    "HEYDOUGA",
}


def normalize_image_url(url: str | None) -> str | None:
    text = (url or "").strip()
    if not text:
        return None
    if len(text) % 2 == 0:
        half = len(text) // 2
        if text[:half] == text[half:] and text.startswith(("http://", "https://")):
            return text[:half]
    return text


def normalize_metadata_image_urls(metadata: MovieMetadata) -> None:
    metadata.cover_url = normalize_image_url(metadata.cover_url)
    metadata.thumb_url = normalize_image_url(metadata.thumb_url)
    normalized_previews: list[str] = []
    for url in metadata.preview_images:
        text = normalize_image_url(url)
        if text and text not in normalized_previews:
            normalized_previews.append(text)
    metadata.preview_images = normalized_previews


def _ordered_unique(values: list[str | None]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = normalize_image_url(value)
        if text and text not in result:
            result.append(text)
    return result


def poster_image_candidates(metadata: MovieMetadata) -> list[str]:
    normalize_metadata_image_urls(metadata)
    preview = metadata.preview_images[0] if metadata.preview_images else None
    return _ordered_unique([metadata.thumb_url, metadata.cover_url, preview])


def guess_dmm_poster_crop_url(code: str | None) -> str | None:
    text = (code or "").strip().upper()
    match = re.fullmatch(r"([A-Z0-9]{2,10})-(\d{2,6})([A-Z]?)", text)
    if not match:
        return None
    prefix, digits, suffix = match.groups()
    slug = f"{prefix.lower()}{int(digits):05d}{suffix.lower()}"
    return f"https://pics.dmm.co.jp/digital/video/{slug}/{slug}pl.jpg"


def javbus_poster_crop_url(metadata: MovieMetadata) -> str | None:
    cover_url = normalize_image_url(metadata.cover_url)
    if not cover_url:
        return None
    if "javbus.com/pics/cover/" in cover_url or "seedmm.help/pics/cover/" in cover_url:
        return cover_url.replace("https://www.seedmm.help", "https://www.javbus.com")
    if metadata.filled_by.get("cover_url") == "JavBus":
        return cover_url
    return None


def native_poster_candidate_urls(metadata: MovieMetadata) -> list[str]:
    normalize_metadata_image_urls(metadata)
    metadata.add_native_poster_urls(_ordered_unique(metadata.native_poster_urls))
    if metadata.native_poster_urls:
        return _ordered_unique(metadata.native_poster_urls)
    return poster_image_candidates(metadata)


def landscape_image_candidates(metadata: MovieMetadata) -> list[str]:
    normalize_metadata_image_urls(metadata)
    preview = metadata.preview_images[0] if metadata.preview_images else None
    return _ordered_unique([preview, metadata.cover_url, metadata.thumb_url])


def preferred_regular_crop_urls(metadata: MovieMetadata) -> list[str]:
    return _ordered_unique(
        [
            metadata.locked_regular_poster_url,
            guess_dmm_poster_crop_url(metadata.code),
            *metadata.regular_poster_crop_urls,
            javbus_poster_crop_url(metadata),
        ]
    )


def should_crop_poster_from_fanart(code: str | None) -> bool:
    text = (code or "").strip().upper()
    if not text:
        return False
    if text.startswith(tuple(f"{prefix}-" for prefix in _SPECIAL_PREFIXES)):
        return False
    if _DATE_CODE_RE.fullmatch(text):
        return False
    if not _REGULAR_CODE_RE.fullmatch(text):
        return False
    prefix = text.split("-", 1)[0]
    if prefix in _SPECIAL_PREFIXES:
        return False
    return True


def select_image_sources(metadata: MovieMetadata) -> ImageSources:
    normalize_metadata_image_urls(metadata)
    landscape_candidates = landscape_image_candidates(metadata)
    fanart_url = landscape_candidates[0] if landscape_candidates else None
    if should_crop_poster_from_fanart(metadata.code):
        poster_candidates = native_poster_candidate_urls(metadata)
        poster_url = poster_candidates[0] if poster_candidates else fanart_url
        thumb_url = fanart_url
    else:
        poster_url = fanart_url
        thumb_url = fanart_url
    return ImageSources(
        poster_url=poster_url,
        fanart_url=fanart_url,
        thumb_url=thumb_url,
    )


def image_candidates_present(metadata: MovieMetadata) -> bool:
    sources = select_image_sources(metadata)
    return bool(sources.poster_url or sources.fanart_url or sources.thumb_url)


def download_image_bytes(client: HttpClient, url: str) -> tuple[bytes, str]:
    parsed = urlparse(url)
    referer = f"{parsed.scheme}://{parsed.netloc}/" if parsed.scheme and parsed.netloc else None
    response = client.request(
        "GET",
        url,
        headers={"referer": referer} if referer else None,
        raise_for_status=True,
    )
    return response.content, response.headers.get("content-type", "image/jpeg")


def image_size(image_bytes: bytes) -> tuple[int, int]:
    with Image.open(BytesIO(image_bytes)) as image:
        transposed = ImageOps.exif_transpose(image)
        return transposed.size


def is_portrait_image(image_bytes: bytes) -> bool:
    width, height = image_size(image_bytes)
    return height > width


def classify_image_orientation(image_bytes: bytes) -> str:
    width, height = image_size(image_bytes)
    if height > width:
        return "portrait"
    if width > height:
        return "landscape"
    return "square"


def select_best_native_poster(
    client: HttpClient,
    candidates: list[str | None],
    *,
    min_height: int = POSTER_MIN_HEIGHT,
    on_log=None,
    code: str | None = None,
) -> SelectedNativePoster | None:
    best_fallback: SelectedNativePoster | None = None
    seen: set[str] = set()
    for url in candidates:
        normalized = normalize_image_url(url)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        try:
            image_bytes, media_type = download_image_bytes(client, normalized)
        except Exception as exc:
            if on_log and code:
                on_log(f"[{code}] 原生 poster 候选下载失败: {normalized} ({exc})")
            continue
        width, height = image_size(image_bytes)
        if height <= width:
            continue
        selected = SelectedNativePoster(
            url=normalized,
            image_bytes=image_bytes,
            media_type=media_type,
            width=width,
            height=height,
            meets_threshold=height >= min_height,
        )
        if selected.meets_threshold:
            return selected
        if best_fallback is None:
            best_fallback = selected
            continue
        if (selected.height, selected.width) > (best_fallback.height, best_fallback.width):
            best_fallback = selected
    return best_fallback


def select_best_native_poster_for_metadata(
    client: HttpClient,
    metadata: MovieMetadata,
    *,
    min_height: int = POSTER_MIN_HEIGHT,
    on_log=None,
) -> SelectedNativePoster | None:
    return select_best_native_poster(
        client,
        native_poster_candidate_urls(metadata),
        min_height=min_height,
        on_log=on_log,
        code=metadata.code,
    )


def _select_landscape_crop_source(
    client: HttpClient,
    candidates: list[str | None],
    *,
    mode: str,
    on_log=None,
    code: str | None = None,
) -> SelectedRegularPoster | None:
    seen: set[str] = set()
    for url in candidates:
        normalized = normalize_image_url(url)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        try:
            image_bytes, media_type = download_image_bytes(client, normalized)
        except Exception as exc:
            if on_log and code:
                on_log(f"[{code}] {mode} 候选下载失败: {normalized} ({exc})")
            continue
        width, height = image_size(image_bytes)
        if width <= height:
            continue
        return SelectedRegularPoster(
            url=normalized,
            image_bytes=image_bytes,
            media_type=media_type,
            width=width,
            height=height,
            mode=mode,
        )
    return None


def select_best_regular_poster_for_metadata(
    client: HttpClient,
    metadata: MovieMetadata,
    *,
    min_height: int = POSTER_MIN_HEIGHT,
    on_log=None,
) -> SelectedRegularPoster | None:
    crop_source = _select_landscape_crop_source(
        client,
        preferred_regular_crop_urls(metadata),
        mode="regular_crop",
        on_log=on_log,
        code=metadata.code,
    )
    if crop_source is not None:
        return crop_source

    native = select_best_native_poster_for_metadata(
        client,
        metadata,
        min_height=min_height,
        on_log=on_log,
    )
    if native is None:
        return None
    return SelectedRegularPoster(
        url=native.url,
        image_bytes=native.image_bytes,
        media_type=native.media_type,
        width=native.width,
        height=native.height,
        mode="native",
        meets_threshold=native.meets_threshold,
    )


def select_dmm_regular_poster_for_code(
    client: HttpClient,
    code: str | None,
    *,
    on_log=None,
) -> SelectedRegularPoster | None:
    return _select_landscape_crop_source(
        client,
        [guess_dmm_poster_crop_url(code)],
        mode="regular_crop",
        on_log=on_log,
        code=code,
    )


def crop_to_poster(image_bytes: bytes, *, ratio: float = POSTER_RATIO, quality: int = 90) -> bytes:
    with Image.open(BytesIO(image_bytes)) as image:
        transposed = ImageOps.exif_transpose(image)
        width, height = transposed.size

        crop_width = int(height * ratio)
        crop_height = int(width / ratio)
        if crop_width < width:
            left = max(width - crop_width, 0)
            box = (left, 0, left + crop_width, height)
        elif crop_height < height:
            top = max((height - crop_height) // 2, 0)
            box = (0, top, width, top + crop_height)
        else:
            box = (0, 0, width, height)

        cropped = transposed.crop(box)
        if cropped.mode not in {"RGB", "L"}:
            cropped = cropped.convert("RGB")
        elif cropped.mode == "L":
            cropped = cropped.convert("RGB")

        buffer = BytesIO()
        cropped.save(buffer, format="JPEG", quality=quality)
        return buffer.getvalue()
