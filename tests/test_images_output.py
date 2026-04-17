from __future__ import annotations

import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image

from javscraper.images import guess_dmm_poster_crop_url, image_size, select_image_sources, should_crop_poster_from_fanart
from javscraper.models import MovieMetadata, ScanEntry
from javscraper.output import save_result


def make_image_bytes(size: tuple[int, int], color: tuple[int, int, int]) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="JPEG")
    return buffer.getvalue()


class DummyResponse:
    def __init__(self, content: bytes, status_code: int = 200) -> None:
        self.content = content
        self.status_code = status_code
        self.headers = {"content-type": "image/jpeg"}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise ValueError(f"status={self.status_code}")


class ImageClient:
    def __init__(self, payloads: dict[str, bytes]) -> None:
        self.payloads = payloads

    def request(self, method: str, url: str, *, raise_for_status: bool = True, **kwargs) -> DummyResponse:
        response = DummyResponse(self.payloads[url])
        if raise_for_status:
            response.raise_for_status()
        return response

    def download(self, url: str, destination: Path, *, headers: dict | None = None) -> None:
        destination.write_bytes(self.payloads[url])


class ImageOutputTests(unittest.TestCase):
    def test_guess_dmm_poster_crop_url_uses_uniform_slug_rule(self) -> None:
        self.assertEqual(
            guess_dmm_poster_crop_url("MIKR-089"),
            "https://pics.dmm.co.jp/digital/video/mikr00089/mikr00089pl.jpg",
        )
        self.assertEqual(
            guess_dmm_poster_crop_url("PRED-861"),
            "https://pics.dmm.co.jp/digital/video/pred00861/pred00861pl.jpg",
        )
        self.assertEqual(
            guess_dmm_poster_crop_url("SNOS-186"),
            "https://pics.dmm.co.jp/digital/video/snos00186/snos00186pl.jpg",
        )

    def test_select_image_sources_prefers_thumb_then_preview_then_cover(self) -> None:
        metadata = MovieMetadata(
            code="ABP-310",
            title="title",
            cover_url="https://example.com/poster.jpg",
            thumb_url="https://example.com/thumb.jpg",
            preview_images=["https://example.com/fanart.jpg"],
        )
        sources = select_image_sources(metadata)
        self.assertEqual(sources.poster_url, "https://example.com/thumb.jpg")
        self.assertEqual(sources.thumb_url, "https://example.com/fanart.jpg")
        self.assertEqual(sources.fanart_url, "https://example.com/fanart.jpg")

        fallback = MovieMetadata(
            code="ABP-311",
            title="title",
            cover_url="https://example.com/poster.jpg",
            preview_images=["https://example.com/fanart.jpg"],
        )
        fallback_sources = select_image_sources(fallback)
        self.assertEqual(fallback_sources.fanart_url, "https://example.com/fanart.jpg")
        self.assertEqual(fallback_sources.thumb_url, "https://example.com/fanart.jpg")
        self.assertEqual(fallback_sources.poster_url, "https://example.com/poster.jpg")

    def test_regular_code_prefers_native_poster_when_it_meets_threshold(self) -> None:
        poster_bytes = make_image_bytes((600, 900), (220, 40, 40))
        thumb_bytes = make_image_bytes((1280, 720), (40, 40, 220))
        client = ImageClient(
            {
                "https://example.com/poster.jpg": poster_bytes,
                "https://example.com/thumb.jpg": thumb_bytes,
            }
        )
        metadata = MovieMetadata(
            code="ABP-310",
            title="Movie",
            cover_url="https://example.com/poster.jpg",
            thumb_url="https://example.com/thumb.jpg",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "ABP-310.mp4"
            source.write_bytes(b"video")
            result = save_result(
                client,
                Path(temp_dir),
                ScanEntry(code="ABP-310", files=[source]),
                metadata,
            )
            fanart_path = Path(result["fanart_file"])
            thumb_path = Path(result["thumb_file"])
            poster_path = Path(result["poster_file"])

            self.assertTrue(fanart_path.exists())
            self.assertTrue(thumb_path.exists())
            self.assertTrue(poster_path.exists())
            self.assertEqual(fanart_path.read_bytes(), thumb_bytes)
            self.assertEqual(thumb_path.read_bytes(), thumb_bytes)
            self.assertEqual(poster_path.read_bytes(), poster_bytes)
            self.assertEqual(image_size(poster_path.read_bytes()), (600, 900))

    def test_save_result_prefers_dmm_crop_source_for_regular_codes(self) -> None:
        dmm_crop_bytes = make_image_bytes((1200, 800), (220, 40, 40))
        fanart_bytes = make_image_bytes((1280, 720), (40, 220, 40))
        client = ImageClient(
            {
                "https://pics.dmm.co.jp/digital/video/abp00311/abp00311pl.jpg": dmm_crop_bytes,
                "https://example.com/fanart.jpg": fanart_bytes,
            }
        )
        metadata = MovieMetadata(
            code="ABP-311",
            title="Movie",
            locked_regular_poster_url="https://pics.dmm.co.jp/digital/video/abp00311/abp00311pl.jpg",
            preview_images=["https://example.com/fanart.jpg"],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "ABP-311.mp4"
            source.write_bytes(b"video")
            result = save_result(
                client,
                Path(temp_dir),
                ScanEntry(code="ABP-311", files=[source]),
                metadata,
            )
            fanart_path = Path(result["fanart_file"])
            thumb_path = Path(result["thumb_file"])
            poster_path = Path(result["poster_file"])

            self.assertEqual(fanart_path.read_bytes(), fanart_bytes)
            self.assertEqual(thumb_path.read_bytes(), fanart_bytes)
            self.assertNotEqual(poster_path.read_bytes(), fanart_bytes)
            self.assertEqual(image_size(poster_path.read_bytes()), (533, 800))

    def test_save_result_skips_portrait_thumb_and_uses_preview_for_fanart(self) -> None:
        portrait_thumb = make_image_bytes((533, 800), (220, 40, 40))
        landscape_preview = make_image_bytes((1280, 720), (40, 220, 40))
        client = ImageClient(
            {
                "https://example.com/thumb.jpg": portrait_thumb,
                "https://example.com/preview.jpg": landscape_preview,
                "https://example.com/poster.jpg": portrait_thumb,
            }
        )
        metadata = MovieMetadata(
            code="ABP-313",
            title="Movie",
            cover_url="https://example.com/poster.jpg",
            thumb_url="https://example.com/thumb.jpg",
            preview_images=["https://example.com/preview.jpg"],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "ABP-313.mp4"
            source.write_bytes(b"video")
            result = save_result(
                client,
                Path(temp_dir),
                ScanEntry(code="ABP-313", files=[source]),
                metadata,
            )
            self.assertEqual(Path(result["fanart_file"]).read_bytes(), landscape_preview)
            self.assertEqual(Path(result["thumb_file"]).read_bytes(), landscape_preview)
            self.assertEqual(Path(result["poster_file"]).read_bytes(), portrait_thumb)
            self.assertEqual(image_size(Path(result["poster_file"]).read_bytes()), (533, 800))

    def test_save_result_generates_all_three_files_with_only_cover(self) -> None:
        cover_bytes = make_image_bytes((1200, 800), (120, 120, 120))
        client = ImageClient({"https://example.com/cover.jpg": cover_bytes})
        metadata = MovieMetadata(
            code="ABP-312",
            title="Movie",
            cover_url="https://example.com/cover.jpg",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "ABP-312.mp4"
            source.write_bytes(b"video")
            result = save_result(
                client,
                Path(temp_dir),
                ScanEntry(code="ABP-312", files=[source]),
                metadata,
            )
            self.assertTrue(Path(result["fanart_file"]).exists())
            self.assertTrue(Path(result["thumb_file"]).exists())
            self.assertTrue(Path(result["poster_file"]).exists())
            self.assertEqual(Path(result["poster_file"]).read_bytes(), cover_bytes)

    def test_save_result_uses_later_provider_native_poster_when_first_is_below_threshold(self) -> None:
        low_poster = make_image_bytes((147, 200), (220, 40, 40))
        high_poster = make_image_bytes((600, 900), (40, 220, 40))
        fanart_bytes = make_image_bytes((1280, 720), (40, 40, 220))
        client = ImageClient(
            {
                "https://example.com/low.jpg": low_poster,
                "https://example.com/high.jpg": high_poster,
                "https://example.com/fanart.jpg": fanart_bytes,
            }
        )
        metadata = MovieMetadata(
            code="ABP-318",
            title="Movie",
            thumb_url="https://example.com/fanart.jpg",
            native_poster_urls=[
                "https://example.com/low.jpg",
                "https://example.com/high.jpg",
            ],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "ABP-318.mp4"
            source.write_bytes(b"video")
            result = save_result(
                client,
                Path(temp_dir),
                ScanEntry(code="ABP-318", files=[source]),
                metadata,
            )
            self.assertEqual(Path(result["poster_file"]).read_bytes(), high_poster)
            self.assertEqual(image_size(Path(result["poster_file"]).read_bytes()), (600, 900))

    def test_save_result_uses_highest_resolution_native_poster_when_all_are_below_threshold(self) -> None:
        low_poster = make_image_bytes((147, 200), (220, 40, 40))
        better_low_poster = make_image_bytes((320, 470), (40, 220, 40))
        fanart_bytes = make_image_bytes((1280, 720), (40, 40, 220))
        client = ImageClient(
            {
                "https://example.com/low.jpg": low_poster,
                "https://example.com/better-low.jpg": better_low_poster,
                "https://example.com/fanart.jpg": fanart_bytes,
            }
        )
        metadata = MovieMetadata(
            code="ABP-319",
            title="Movie",
            thumb_url="https://example.com/fanart.jpg",
            native_poster_urls=[
                "https://example.com/low.jpg",
                "https://example.com/better-low.jpg",
            ],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "ABP-319.mp4"
            source.write_bytes(b"video")
            result = save_result(
                client,
                Path(temp_dir),
                ScanEntry(code="ABP-319", files=[source]),
                metadata,
            )
            self.assertEqual(Path(result["poster_file"]).read_bytes(), better_low_poster)
            self.assertEqual(image_size(Path(result["poster_file"]).read_bytes()), (320, 470))

    def test_save_result_falls_back_to_shared_images_when_no_regular_poster_source_exists(self) -> None:
        fanart_bytes = make_image_bytes((1280, 720), (40, 220, 40))
        client = ImageClient({"https://example.com/fanart.jpg": fanart_bytes})
        metadata = MovieMetadata(
            code="ABP-320",
            title="Movie",
            thumb_url="https://example.com/fanart.jpg",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "ABP-320.mp4"
            source.write_bytes(b"video")
            result = save_result(
                client,
                Path(temp_dir),
                ScanEntry(code="ABP-320", files=[source]),
                metadata,
            )
            self.assertEqual(Path(result["poster_file"]).read_bytes(), fanart_bytes)

    def test_special_code_uses_same_wide_image_for_all_three_outputs(self) -> None:
        wide_bytes = make_image_bytes((1280, 720), (80, 120, 180))
        portrait_bytes = make_image_bytes((600, 900), (180, 80, 120))
        client = ImageClient(
            {
                "https://example.com/thumb.jpg": wide_bytes,
                "https://example.com/poster.jpg": portrait_bytes,
            }
        )
        metadata = MovieMetadata(
            code="HEYZO-0841",
            title="Movie",
            cover_url="https://example.com/poster.jpg",
            thumb_url="https://example.com/thumb.jpg",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "HEYZO-0841.mp4"
            source.write_bytes(b"video")
            result = save_result(
                client,
                Path(temp_dir),
                ScanEntry(code="HEYZO-0841", files=[source]),
                metadata,
            )
            fanart = Path(result["fanart_file"]).read_bytes()
            thumb = Path(result["thumb_file"]).read_bytes()
            poster = Path(result["poster_file"]).read_bytes()
            self.assertEqual(fanart, wide_bytes)
            self.assertEqual(thumb, wide_bytes)
            self.assertEqual(poster, wide_bytes)

    def test_should_crop_poster_from_fanart_only_for_regular_codes(self) -> None:
        self.assertTrue(should_crop_poster_from_fanart("ABP-310"))
        self.assertTrue(should_crop_poster_from_fanart("START-222"))
        self.assertFalse(should_crop_poster_from_fanart("FC2-4546392"))
        self.assertFalse(should_crop_poster_from_fanart("HEYZO-2949"))
        self.assertFalse(should_crop_poster_from_fanart("HEYDOUGA-4037-479"))
        self.assertFalse(should_crop_poster_from_fanart("050422-001"))


if __name__ == "__main__":
    unittest.main()
