from __future__ import annotations

import csv
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

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


def normalize_cover_url(metadata: MovieMetadata) -> str | None:
    if not metadata.cover_url:
        return None
    url = metadata.cover_url
    if len(url) % 2 == 0:
        half = len(url) // 2
        if url[:half] == url[half:] and url.startswith(("http://", "https://")):
            url = url[:half]
            metadata.cover_url = url
    return url


def download_cover(client: HttpClient, metadata: MovieMetadata, folder: Path, filename: str, on_log=None) -> Path | None:
    url = normalize_cover_url(metadata)
    if not url:
        return None
    parsed = urlparse(url)
    target = folder / filename
    if on_log:
        on_log(f"[{metadata.code}] 下载资源: {filename} <- {url}")
    client.download(url, target, headers={"referer": f"{parsed.scheme}://{parsed.netloc}/"})
    if on_log:
        on_log(f"[{metadata.code}] 已保存资源: {target}")
    return target


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
        except Exception:
            if on_log:
                on_log(f"[{metadata.code}] 预览图下载失败 {index}: {url}")
            continue
    return saved


def build_movie_folder(output_root: Path, metadata: MovieMetadata) -> Path:
    folder = output_root / "#整理完成" / actress_folder_name(metadata) / output_folder_name(metadata)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def save_result(client: HttpClient, output_root: Path, entry: ScanEntry, metadata: MovieMetadata, on_log=None) -> dict:
    folder = build_movie_folder(output_root, metadata)
    move_video_files(entry, folder, metadata.code, on_log)
    if on_log:
        on_log(f"[{entry.code}] 写入 NFO: {folder / 'movie.nfo'}")
    write_nfo(metadata, folder)
    fanart_path = download_cover(client, metadata, folder, "fanart.jpg", on_log)
    poster_path = None
    if fanart_path and fanart_path.exists():
        poster_path = folder / "poster.jpg"
        shutil.copy2(fanart_path, poster_path)
        if on_log:
            on_log(f"[{entry.code}] 生成 poster: {poster_path}")
    extrafanart_paths = download_preview_images(client, metadata, folder, on_log)

    return {
        "code": entry.code,
        "source_file": str(entry.primary_file),
        "file_count": str(entry.file_count),
        "title": metadata.title or "",
        "providers": "|".join(metadata.providers),
        "output_folder": str(folder),
        "cover_file": str(fanart_path) if fanart_path else "",
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
        "cover_file",
        "poster_file",
        "preview_count",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path
