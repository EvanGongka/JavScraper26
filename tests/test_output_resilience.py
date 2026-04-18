from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import Mock

from javscraper.models import MovieMetadata
from javscraper.output import download_cover, download_preview_images, format_nfo_title, is_downloadable_url, write_nfo


class DummyClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Path, dict | None]] = []

    def request(self, method: str, url: str, *, headers: dict | None = None, raise_for_status: bool = True, **kwargs):
        destination = Mock()
        destination.content = b"ok"
        destination.headers = {"content-type": "image/jpeg"}
        destination.status_code = 200
        destination.raise_for_status = Mock()
        if "fail" in url:
            def _raise() -> None:
                raise ValueError("boom")
            destination.raise_for_status.side_effect = _raise
        self.calls.append((url, Path("memory"), headers))
        if raise_for_status:
            destination.raise_for_status()
        return destination

    def download(self, url: str, destination: Path, *, headers: dict | None = None) -> None:
        self.calls.append((url, destination, headers))
        if "fail" in url:
            raise ValueError("boom")
        destination.write_bytes(b"ok")


class OutputResilienceTests(unittest.TestCase):
    def test_format_nfo_title_prefixes_code(self) -> None:
        metadata = MovieMetadata(code="MIDA-574", title="sample title")
        self.assertEqual(format_nfo_title(metadata), "【MIDA-574】sample title")

    def test_format_nfo_title_does_not_duplicate_prefix(self) -> None:
        metadata = MovieMetadata(code="MIDA-574", title="【MIDA-574】sample title")
        self.assertEqual(format_nfo_title(metadata), "【MIDA-574】sample title")

    def test_write_nfo_uses_prefixed_title_and_preserves_original_title(self) -> None:
        metadata = MovieMetadata(
            code="MIDA-574",
            title="「もうこれで最後…ねッ？」",
            original_title="Original Title",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_nfo(metadata, Path(temp_dir))
            root = ET.fromstring(path.read_bytes())

        self.assertEqual(root.findtext("title"), "【MIDA-574】「もうこれで最後…ねッ？」")
        self.assertEqual(root.findtext("originaltitle"), "Original Title")
        self.assertEqual(root.findtext("sorttitle"), "MIDA-574")

    def test_is_downloadable_url_accepts_http_and_https_only(self) -> None:
        self.assertTrue(is_downloadable_url("https://example.com/a.jpg"))
        self.assertTrue(is_downloadable_url("http://example.com/a.jpg"))
        self.assertFalse(is_downloadable_url("//example.com/a.jpg"))
        self.assertFalse(is_downloadable_url("example.com/a.jpg"))
        self.assertFalse(is_downloadable_url(""))

    def test_download_cover_skips_invalid_url_without_raising(self) -> None:
        client = DummyClient()
        metadata = MovieMetadata(code="HEYZO-0805", title="test", cover_url="//example.com/a.jpg")
        logs: list[str] = []
        with tempfile.TemporaryDirectory() as temp_dir:
            result = download_cover(client, metadata, Path(temp_dir), "fanart.jpg", logs.append)
        self.assertIsNone(result)
        self.assertEqual(client.calls, [])
        self.assertTrue(any("跳过无效图片地址" in line for line in logs))

    def test_download_cover_swallow_download_error(self) -> None:
        client = DummyClient()
        metadata = MovieMetadata(code="HEYZO-0805", title="test", cover_url="https://example.com/fail.jpg")
        logs: list[str] = []
        with tempfile.TemporaryDirectory() as temp_dir:
            result = download_cover(client, metadata, Path(temp_dir), "fanart.jpg", logs.append)
        self.assertIsNone(result)
        self.assertEqual(len(client.calls), 1)
        self.assertTrue(any("资源下载失败" in line for line in logs))

    def test_download_preview_images_skips_invalid_and_failed_urls(self) -> None:
        client = DummyClient()
        metadata = MovieMetadata(
            code="HEYZO-0805",
            title="test",
            preview_images=[
                "//example.com/bad.jpg",
                "https://example.com/fail.jpg",
                "https://example.com/ok.jpg",
            ],
        )
        logs: list[str] = []
        with tempfile.TemporaryDirectory() as temp_dir:
            saved = download_preview_images(client, metadata, Path(temp_dir), logs.append)
        self.assertEqual(len(saved), 1)
        self.assertTrue(saved[0].name.endswith(".jpg"))
        self.assertEqual(len(client.calls), 2)
        self.assertTrue(any("跳过无效预览图" in line for line in logs))
        self.assertTrue(any("预览图下载失败" in line for line in logs))


if __name__ == "__main__":
    unittest.main()
