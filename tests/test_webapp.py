from __future__ import annotations

import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi.responses import Response
from PIL import Image

from javscraper.emby_service import ProxyConfig, ResolvedImage
from javscraper.images import ImageSources, SelectedRegularPoster, image_size
from javscraper.metadata_resolution import ResolvedMetadata
from javscraper.models import MovieMetadata, ScanEntry
from javscraper.pipeline import ScrapePipeline
from javscraper.provider_catalog import REGULAR_SITES, SPECIAL_SITES
from javscraper.webapp import (
    EMBY_SERVICE,
    SERVICE_LOGS,
    ConnectivityRequest,
    api_connectivity,
    emby_health,
    emby_movie_detail,
    emby_movie_image,
    emby_recent_logs,
    emby_resolve_movie,
    index,
    launch,
    service_page,
    webui_page,
)


def make_image_bytes(size: tuple[int, int]) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, (120, 120, 120)).save(buffer, format="JPEG")
    return buffer.getvalue()


class SuccessProvider:
    site_name = "Success"

    def __init__(self, client):
        self.client = client

    def fetch(self, code: str):
        return MovieMetadata(
            code=code.upper(),
            title="Movie title",
            cover_url="https://example.com/poster.jpg",
            thumb_url="https://example.com/thumb.jpg",
            release_date="2024-05-01",
            description="Summary",
            actresses=["Actor A"],
            genres=["Drama"],
            preview_images=["https://example.com/backdrop.jpg"],
        )


class JavBusProviderStub:
    site_name = "JavBus"

    def __init__(self, client):
        self.client = client


class HeyzoProviderStub:
    site_name = "HEYZO"

    def __init__(self, client):
        self.client = client


class WebAppTests(unittest.TestCase):
    def setUp(self):
        EMBY_SERVICE.provider_names = ["Success"]
        EMBY_SERVICE.default_proxy = ProxyConfig()
        SERVICE_LOGS.add("INFO", "test", "ready")

    def test_root_page_and_mode_routes(self):
        response = index()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Path(response.path).name, "index.html")
        self.assertEqual(Path(response.path).parent.name, "webui")

        self.assertEqual(webui_page().status_code, 200)
        self.assertEqual(service_page().status_code, 200)

    def test_root_redirects_when_mode_overridden(self):
        with patch.dict("os.environ", {"JAVSCRAPER_MODE": "service"}):
            response = index()
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "/service")

    def test_launch_uses_configured_host(self):
        with patch.dict(
            "os.environ",
            {
                "JAVSCRAPER_HOST": "0.0.0.0",
                "JAVSCRAPER_PORT": "8765",
                "JAVSCRAPER_DISABLE_BROWSER": "1",
            },
            clear=False,
        ), patch("javscraper.webapp.uvicorn.run") as mock_run:
            launch()

        self.assertEqual(mock_run.call_args.kwargs["host"], "0.0.0.0")
        self.assertEqual(mock_run.call_args.kwargs["port"], 8765)

    def test_emby_api_routes(self):
        with patch.dict("javscraper.emby_service.PROVIDER_CLASSES", {"Success": SuccessProvider}, clear=False):
            resolve = emby_resolve_movie(
                path=r"D:\Media\ABP-123\ABP-123.mp4",
            )
            self.assertEqual(resolve["results"][0]["provider"], "Success")
            self.assertEqual(resolve["results"][0]["providerItemId"], "ABP-123")

            detail = emby_movie_detail("Success", "ABP-123")
            self.assertEqual(detail["title"], "Movie title")

        health = emby_health()
        self.assertEqual(health["status"], "ok")

        logs = emby_recent_logs()
        self.assertIn("entries", logs)

    def test_image_route_returns_bytes(self):
        resolved = ResolvedImage(
            image_type="thumb",
            url="https://example.com/thumb.jpg",
            metadata=MovieMetadata(code="ABP-123", title="Movie"),
            sources=ImageSources(
                poster_url="https://example.com/poster.jpg",
                fanart_url="https://example.com/thumb.jpg",
                thumb_url="https://example.com/thumb.jpg",
            ),
        )
        with patch("javscraper.webapp.EMBY_SERVICE.get_image", return_value=resolved), patch(
            "javscraper.webapp._fetch_best_landscape_image",
            return_value=(b"jpeg-bytes", "image/jpeg"),
        ):
            response = emby_movie_image("thumb", "Success", "ABP-123")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.media_type, "image/jpeg")
        self.assertEqual(response.body, b"jpeg-bytes")

    def test_primary_image_falls_back_to_shared_fanart_when_no_regular_poster_source_exists(self):
        resolved = ResolvedImage(
            image_type="primary",
            url="https://example.com/fanart.jpg",
            metadata=MovieMetadata(code="ABP-123", title="Movie"),
            sources=ImageSources(
                poster_url="https://example.com/poster.jpg",
                fanart_url="https://example.com/fanart.jpg",
                thumb_url="https://example.com/fanart.jpg",
            ),
        )
        with patch("javscraper.webapp.EMBY_SERVICE.get_image", return_value=resolved), patch(
            "javscraper.webapp.select_best_regular_poster_for_metadata",
            return_value=None,
        ), patch(
            "javscraper.webapp._fetch_best_landscape_image",
            return_value=(make_image_bytes((1280, 720)), "image/jpeg"),
        ):
            response = emby_movie_image("primary", "Success", "ABP-123")

        self.assertEqual(response.media_type, "image/jpeg")
        self.assertEqual(image_size(response.body), (1280, 720))

    def test_primary_image_crops_selected_regular_crop_source(self):
        selected = SelectedRegularPoster(
            url="https://pics.dmm.co.jp/digital/video/abp00123/abp00123pl.jpg",
            image_bytes=make_image_bytes((1200, 800)),
            media_type="image/jpeg",
            width=1200,
            height=800,
            mode="regular_crop",
        )
        resolved = ResolvedImage(
            image_type="primary",
            url="https://example.com/fanart.jpg",
            metadata=MovieMetadata(
                code="ABP-123",
                title="Movie",
            ),
            sources=ImageSources(
                poster_url="https://example.com/poster.jpg",
                fanart_url="https://example.com/fanart.jpg",
                thumb_url="https://example.com/fanart.jpg",
            ),
        )
        with patch("javscraper.webapp.EMBY_SERVICE.get_image", return_value=resolved), patch(
            "javscraper.webapp.select_best_regular_poster_for_metadata",
            return_value=selected,
        ):
            response = emby_movie_image("primary", "Success", "ABP-123")

        self.assertEqual(response.media_type, "image/jpeg")
        self.assertEqual(image_size(response.body), (533, 800))

    def test_primary_image_returns_highest_resolution_native_poster_when_all_are_below_threshold(self):
        selected = SelectedRegularPoster(
            url="https://example.com/better-low.jpg",
            image_bytes=make_image_bytes((320, 470)),
            media_type="image/jpeg",
            width=320,
            height=470,
            mode="native",
            meets_threshold=False,
        )
        resolved = ResolvedImage(
            image_type="primary",
            url="https://example.com/fanart.jpg",
            metadata=MovieMetadata(
                code="ABP-123",
                title="Movie",
                native_poster_urls=["https://example.com/low.jpg", "https://example.com/better-low.jpg"],
            ),
            sources=ImageSources(
                poster_url="https://example.com/low.jpg",
                fanart_url="https://example.com/fanart.jpg",
                thumb_url="https://example.com/fanart.jpg",
            ),
        )
        with patch("javscraper.webapp.EMBY_SERVICE.get_image", return_value=resolved), patch(
            "javscraper.webapp.select_best_regular_poster_for_metadata",
            return_value=selected,
        ):
            response = emby_movie_image("primary", "Success", "ABP-123")

        self.assertEqual(response.media_type, "image/jpeg")
        self.assertEqual(image_size(response.body), (320, 470))

    def test_primary_image_returns_same_wide_image_for_special_codes(self):
        wide = make_image_bytes((1280, 720))
        resolved = ResolvedImage(
            image_type="primary",
            url="https://example.com/fanart.jpg",
            metadata=MovieMetadata(code="HEYZO-0841", title="Movie"),
            sources=ImageSources(
                poster_url="https://example.com/poster.jpg",
                fanart_url="https://example.com/fanart.jpg",
                thumb_url="https://example.com/fanart.jpg",
            ),
        )
        with patch("javscraper.webapp.EMBY_SERVICE.get_image", return_value=resolved), patch(
            "javscraper.webapp._fetch_best_landscape_image",
            return_value=(wide, "image/jpeg"),
        ):
            response = emby_movie_image("primary", "Success", "HEYZO-0841")

        self.assertEqual(response.media_type, "image/jpeg")
        self.assertEqual(response.body, wide)

    def test_api_connectivity_uses_scanned_codes_to_select_sites(self):
        def fake_connectivity(client, name, url):
            return {"name": name, "url": url, "ok": True, "status": 200, "detail": "ok", "finalUrl": url}

        with patch("javscraper.webapp._javdb_available", return_value=False), patch(
            "javscraper.webapp._connectivity_result_for",
            side_effect=fake_connectivity,
        ):
            payload = ConnectivityRequest(codes=["ABP-123", "HEYZO-0841"])
            result = api_connectivity(payload)

        self.assertEqual(
            [item["name"] for item in result["results"]],
            [name for name in REGULAR_SITES if name != "JavDB"] + SPECIAL_SITES,
        )

    def test_pipeline_routes_each_entry_by_code_group(self):
        calls: list[tuple[str, list[str]]] = []
        entries = [
            ScanEntry(code="ABP-123", files=[Path("/tmp/abp-123.mp4")]),
            ScanEntry(code="HEYZO-0841", files=[Path("/tmp/heyzo-0841.mp4")]),
        ]

        def fake_resolve(code, providers, **kwargs):
            calls.append((code, [provider.site_name for provider in providers]))
            return ResolvedMetadata(
                metadata=MovieMetadata(
                    code=code,
                    title=f"{code} title",
                    cover_url="https://example.com/poster.jpg",
                ),
                provider=providers[0].site_name,
            )

        with patch.dict(
            "javscraper.pipeline.PROVIDER_CLASSES",
            {"JavBus": JavBusProviderStub, "HEYZO": HeyzoProviderStub},
            clear=False,
        ), patch(
            "javscraper.pipeline.resolve_metadata_from_providers",
            side_effect=fake_resolve,
        ), patch(
            "javscraper.pipeline.save_result",
            return_value={"output_folder": "/tmp/out"},
        ), patch(
            "javscraper.pipeline.write_manifest",
            return_value=Path("/tmp/manifest.csv"),
        ):
            pipeline = ScrapePipeline(
                output_root="/tmp/javscraper-test-output",
                provider_names=["JavBus", "HEYZO"],
                on_log=lambda text: None,
                on_status=lambda code, status: None,
                javdb_available=False,
            )
            manifest = pipeline.run(entries)

        self.assertEqual(manifest, Path("/tmp/manifest.csv"))
        self.assertEqual(
            calls,
            [
                ("ABP-123", ["JavBus"]),
                ("HEYZO-0841", ["HEYZO"]),
            ],
        )


if __name__ == "__main__":
    unittest.main()
