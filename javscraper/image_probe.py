from __future__ import annotations

from dataclasses import dataclass

from javscraper.images import classify_image_orientation, download_image_bytes, image_size, normalize_image_url
from javscraper.network import HttpClient


@dataclass(frozen=True)
class ProbedImage:
    url: str
    width: int
    height: int
    orientation: str


def probe_image(client: HttpClient, url: str | None) -> ProbedImage | None:
    normalized = normalize_image_url(url)
    if not normalized:
        return None
    image_bytes, _ = download_image_bytes(client, normalized)
    width, height = image_size(image_bytes)
    return ProbedImage(
        url=normalized,
        width=width,
        height=height,
        orientation=classify_image_orientation(image_bytes),
    )
