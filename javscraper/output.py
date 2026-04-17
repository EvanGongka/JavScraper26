from __future__ import annotations

import csv
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

from javscraper.images import (
    crop_to_poster,
    download_image_bytes,
    is_portrait_image,
    landscape_image_candidates,
    select_best_regular_poster_for_metadata,
    select_image_sources,
    should_crop_poster_from_fanart,
)
from javscraper.models import MovieMetadata, ScanEntry
from javscraper.network import HttpClient

LogCallback = callable


def safe_name(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*]+', " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or "unknown"


def output_folder_name(metadata: MovieMetadata) -> str:
    title = safe_name(metadata.title or "untitled")
    return f"[{metadata.code}] {title}"


def actress_folder_name(metadata: MovieMetadata) -> str:
    if metadata.actresses:
        return safe_name(",".join(metadata.actresses))
    return "#未知女优"


def write_nfo(metadata: MovieMetadata, folder: Path) -> Path:
    root = ET.Element("movie")
    ET.SubElement(root, "title").text = metadata.title or metadata.code
    ET.SubElement(root, "originaltitle").text = metadata.original_title or metadata.title or metadata.code
    ET.SubElement(root, "sorttitle").text = metadata.code
    ET.SubElement(root, "uniqueid", attrib={"type": "jav", "default": "true"}).text = metadata.code
    ET.SubElement(root, "id").text = metadata.code
    ET.SubElement(root, "premiered").text = metadata.release_date or ""
    ET.SubElement(root, "releasedate").text = metadata.release_date or ""
    ET.SubElement(root, "runtime").text = metadata.duration_minutes or ""
    ET.SubElement(root, "director").text = metadata.director or ""
    ET.SubElement(root, "studio").text = metadata.maker or ""
    ET.SubElement(root, "set").text = metadata.series or ""
    ET.SubElement(root, "plot").text = metadata.description or ""
    ET.SubElement(root, "trailer").text = metadata.trailer_url or ""
    ET.SubElement(root, "rating").text = metadata.score or ""
    ET.SubElement(root, "website").text = metadata.detail_url or ""

    for genre in metadata.genres:
        ET.SubElement(root, "genre").text = genre
        ET.SubElement(root, "tag").text = genre

    for actress in metadata.actresses:
        actor = ET.SubElement(root, "actor")
        ET.SubElement(actor, "name").text = actress

    xml_data = ET.tostring(root, encoding="utf-8")
    path = folder / "movie.nfo"
    path.write_bytes(xml_data)
    return path


def is_downloadable_url(url: str | None) -> bool:
    text = (url or "").strip()
    if not text:
        return False
    parsed = urlparse(text)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _download_image(client: HttpClient, code: str, url: str | None, folder: Path, filename: str, on_log=None) -> tuple[Path | None, bytes | None]:
    if not is_downloadable_url(url):
        if on_log and url:
            on_log(f"[{code}] 跳过无效图片地址 {filename}: {url}")
        return None, None
    target = folder / filename
    try:
        if on_log:
            on_log(f"[{code}] 下载资源: {filename} <- {url}")
        image_bytes, _ = download_image_bytes(client, url)
        target.write_bytes(image_bytes)
        if on_log:
            on_log(f"[{code}] 已保存资源: {target}")
        return target, image_bytes
    except Exception as exc:
        if on_log:
            on_log(f"[{code}] 资源下载失败 {filename}: {url} ({exc})")
        return None, None


def download_cover(client: HttpClient, metadata: MovieMetadata, folder: Path, filename: str, on_log=None) -> Path | None:
    path, _ = _download_image(client, metadata.code, metadata.cover_url, folder, filename, on_log)
    return path


def move_video_files(entry: ScanEntry, folder: Path, code: str, on_log=None) -> list[Path]:
    moved: list[Path] = []
    for index, source in enumerate(entry.files, start=1):
        suffix = source.suffix.lower()
        target_name = f"{code}{suffix}" if len(entry.files) == 1 else f"{code}-CD{index}{suffix}"
        target = folder / target_name
        if on_log:
            on_log(f"[{entry.code}] 移动视频文件: {source} -> {target}")
        shutil.move(str(source), str(target))
        moved.append(target)
    return moved


def download_preview_images(client: HttpClient, metadata: MovieMetadata, folder: Path, on_log=None) -> list[Path]:
    saved: list[Path] = []
    if not metadata.preview_images:
        return saved
    extra_dir = folder / "extrafanart"
    extra_dir.mkdir(exist_ok=True)
    for index, url in enumerate(metadata.preview_images):
        if not is_downloadable_url(url):
            if on_log:
                on_log(f"[{metadata.code}] 跳过无效预览图 {index}: {url}")
            continue
        parsed = urlparse(url)
        suffix = Path(parsed.path).suffix or ".jpg"
        target = extra_dir / f"{index}{suffix}"
        try:
            if on_log:
                on_log(f"[{metadata.code}] 下载预览图 {index}: {url}")
            client.download(url, target, headers={"referer": f"{parsed.scheme}://{parsed.netloc}/"})
            saved.append(target)
            if on_log:
                on_log(f"[{metadata.code}] 已保存预览图 {index}: {target}")
        except Exception as exc:
            if on_log:
                on_log(f"[{metadata.code}] 预览图下载失败 {index}: {url} ({exc})")
            continue
    return saved


def build_movie_folder(output_root: Path, metadata: MovieMetadata) -> Path:
    folder = output_root / "#整理完成" / actress_folder_name(metadata) / output_folder_name(metadata)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _write_poster(entry: ScanEntry, folder: Path, fanart_bytes: bytes | None, on_log=None) -> Path | None:
    poster_target = folder / "poster.jpg"
    if not fanart_bytes:
        return None
    if should_crop_poster_from_fanart(entry.code):
        poster_target.write_bytes(fanart_bytes)
        if on_log:
            on_log(f"[{entry.code}] 已回退为 fanart/poster/thumb 三图同源: {poster_target}")
    else:
        poster_target.write_bytes(fanart_bytes)
        if on_log:
            on_log(f"[{entry.code}] 已复制 fanart 作为 poster: {poster_target}")
    return poster_target


def _download_best_landscape_image(
    client: HttpClient,
    entry: ScanEntry,
    folder: Path,
    filename: str,
    candidates: list[str | None],
    on_log=None,
) -> tuple[Path | None, bytes | None, str | None]:
    fallback: tuple[Path, bytes, str] | None = None
    seen: set[str] = set()
    for url in candidates:
        if not is_downloadable_url(url) or url in seen:
            continue
        seen.add(url)
        path, image_bytes = _download_image(client, entry.code, url, folder, filename, on_log)
        if path is None or image_bytes is None:
            continue
        if fallback is None:
            fallback = (path, image_bytes, url)
        if not is_portrait_image(image_bytes):
            return path, image_bytes, url
        if on_log:
            on_log(f"[{entry.code}] {filename} 候选为竖图，继续尝试下一候选: {url}")
    if fallback is not None:
        return fallback
    return None, None, None


def _write_best_poster(
    client: HttpClient,
    entry: ScanEntry,
    metadata: MovieMetadata,
    folder: Path,
    fanart_bytes: bytes | None,
    on_log=None,
) -> Path | None:
    if should_crop_poster_from_fanart(entry.code):
        selected = select_best_regular_poster_for_metadata(client, metadata, on_log=on_log)
        if selected is not None:
            poster_path = folder / "poster.jpg"
            if selected.mode == "regular_crop":
                poster_path.write_bytes(crop_to_poster(selected.image_bytes))
            else:
                poster_path.write_bytes(selected.image_bytes)
            if on_log:
                if selected.mode == "regular_crop":
                    on_log(
                        f"[{entry.code}] 已使用可直接裁切横图生成 poster: {selected.url} ({selected.width}x{selected.height})"
                    )
                elif selected.meets_threshold:
                    on_log(
                        f"[{entry.code}] 已使用达标原生竖图作为 poster: {selected.url} ({selected.width}x{selected.height})"
                    )
                else:
                    on_log(
                        f"[{entry.code}] 所有原生竖图均低于阈值，已使用最高分辨率原生竖图作为 poster: "
                        f"{selected.url} ({selected.width}x{selected.height})"
                    )
            return poster_path
        if on_log:
            on_log(f"[{entry.code}] 未找到可直接裁切横图或原生竖图，回退为 fanart/poster/thumb 三图同源")
    return _write_poster(entry, folder, fanart_bytes, on_log)


def save_result(client: HttpClient, output_root: Path, entry: ScanEntry, metadata: MovieMetadata, on_log=None) -> dict:
    folder = build_movie_folder(output_root, metadata)
    move_video_files(entry, folder, metadata.code, on_log)
    if on_log:
        on_log(f"[{entry.code}] 写入 NFO: {folder / 'movie.nfo'}")
    write_nfo(metadata, folder)
    select_image_sources(metadata)

    fanart_path, fanart_bytes, fanart_url = _download_best_landscape_image(
        client,
        entry,
        folder,
        "fanart.jpg",
        landscape_image_candidates(metadata),
        on_log,
    )

    thumb_path = None
    if fanart_path and fanart_url:
        thumb_path = folder / "thumb.jpg"
        shutil.copy2(fanart_path, thumb_path)
        if on_log:
            on_log(f"[{entry.code}] 复制 thumb: {thumb_path}")

    poster_path = _write_best_poster(client, entry, metadata, folder, fanart_bytes, on_log)
    extrafanart_paths = download_preview_images(client, metadata, folder, on_log)

    return {
        "code": entry.code,
        "source_file": str(entry.primary_file),
        "file_count": str(entry.file_count),
        "title": metadata.title or "",
        "providers": "|".join(metadata.providers),
        "output_folder": str(folder),
        "fanart_file": str(fanart_path) if fanart_path else "",
        "thumb_file": str(thumb_path) if thumb_path else "",
        "poster_file": str(poster_path) if poster_path else "",
        "actress_folder": actress_folder_name(metadata),
        "preview_count": str(len(extrafanart_paths)),
    }


def write_manifest(rows: list[dict], output_root: Path) -> Path:
    path = output_root / "manifest.csv"
    fieldnames = [
        "code",
        "source_file",
        "file_count",
        "title",
        "providers",
        "actress_folder",
        "output_folder",
        "fanart_file",
        "thumb_file",
        "poster_file",
        "preview_count",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path
