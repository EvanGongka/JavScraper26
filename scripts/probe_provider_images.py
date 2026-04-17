from __future__ import annotations

import csv
import sys
from pathlib import Path

from javscraper.image_probe import probe_image
from javscraper.images import select_image_sources
from javscraper.network import HttpClient
from javscraper.providers import PROVIDER_CLASSES

EARLY_PROVIDERS = ["JavBus", "JavBooks", "AVMOO", "FreeJavBT", "JavDB"]
SAMPLE_CODES = {
    "AVBASE": ["ABP-310"],
    "JAV321": ["ABP-310"],
    "FC2": ["FC2-1375071"],
    "Caribbeancom": ["050422-001"],
    "CaribbeancomPR": ["052121-002"],
    "HEYZO": ["0841"],
    "HeyDouga": ["4037-479"],
    "1Pondo": ["071319-870"],
    "10musume": ["042922-01"],
    "PACOPACOMAMA": ["032622-623"],
    "MURAMURA": ["091522-959"],
}


def _early_samples() -> list[str]:
    sample_dir = Path("test/input copy 3")
    return sorted({path.stem for path in sample_dir.glob("*.mp4")})


def _classify_capability(poster, thumb, fanart) -> str:
    if poster and poster.orientation == "portrait" and thumb and thumb.orientation == "landscape":
        return "原生 poster + 原生 thumb"
    if poster and poster.orientation == "portrait":
        return "原生 poster"
    if thumb and thumb.orientation == "landscape":
        return "原生 thumb"
    if fanart:
        return "仅单图源"
    return "无可用图片"


def main() -> None:
    rows: list[dict[str, str]] = []

    provider_samples = {name: _early_samples() for name in EARLY_PROVIDERS}
    provider_samples.update(SAMPLE_CODES)

    for provider_name, samples in provider_samples.items():
        provider_cls = PROVIDER_CLASSES[provider_name]
        for code in samples:
            metadata = None
            error = ""
            try:
                metadata = provider_cls(HttpClient()).fetch(code)
                sources = select_image_sources(metadata)
                poster = probe_image(HttpClient(), sources.poster_url)
                thumb = probe_image(HttpClient(), sources.thumb_url)
                fanart = probe_image(HttpClient(), sources.fanart_url)
                rows.append(
                    {
                        "provider": provider_name,
                        "code": code,
                        "cover_url": metadata.cover_url or "",
                        "thumb_url": metadata.thumb_url or "",
                        "fanart_url": sources.fanart_url or "",
                        "poster_shape": poster.orientation if poster else "",
                        "poster_size": f"{poster.width}x{poster.height}" if poster else "",
                        "thumb_shape": thumb.orientation if thumb else "",
                        "thumb_size": f"{thumb.width}x{thumb.height}" if thumb else "",
                        "fanart_shape": fanart.orientation if fanart else "",
                        "fanart_size": f"{fanart.width}x{fanart.height}" if fanart else "",
                        "capability": _classify_capability(poster, thumb, fanart),
                        "error": "",
                    }
                )
            except Exception as exc:
                error = str(exc)
                rows.append(
                    {
                        "provider": provider_name,
                        "code": code,
                        "cover_url": metadata.cover_url if metadata else "",
                        "thumb_url": metadata.thumb_url if metadata else "",
                        "fanart_url": "",
                        "poster_shape": "",
                        "poster_size": "",
                        "thumb_shape": "",
                        "thumb_size": "",
                        "fanart_shape": "",
                        "fanart_size": "",
                        "capability": "抓取失败",
                        "error": error,
                    }
                )

    writer = csv.DictWriter(
        sys.stdout,
        fieldnames=[
            "provider",
            "code",
            "cover_url",
            "thumb_url",
            "fanart_url",
            "poster_shape",
            "poster_size",
            "thumb_shape",
            "thumb_size",
            "fanart_shape",
            "fanart_size",
            "capability",
            "error",
        ],
    )
    writer.writeheader()
    writer.writerows(rows)


if __name__ == "__main__":
    main()
