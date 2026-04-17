from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import re
from urllib.parse import urlparse

from PIL import Image, ImageOps

from javscraper.models import MovieMetadata
from javscraper.network import HttpClient

POSTER_RATIO = 2.0 / 3.0


@dataclass(frozen=True)
class ImageSources:
    poster_url: str | None
    fanart_url: str | None
    thumb_url: str | None


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


def select_image_sources(metadata: MovieMetadata) -> ImageSources:
    normalize_metadata_image_urls(metadata)
    poster_url = metadata.cover_url
    fanart_url = metadata.thumb_url or (metadata.preview_images[0] if metadata.preview_images else None) or metadata.cover_url
    thumb_url = metadata.thumb_url or fanart_url
    return ImageSources(
        poster_url=poster_url,
        fanart_url=fanart_url,
        thumb_url=thumb_url,
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
