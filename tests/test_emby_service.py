from __future__ import annotations

import unittest
from unittest.mock import patch

from javscraper.emby_service import EmbyMovieService, ProxyConfig, ResolvedMovie, extract_emby_code
from javscraper.images import SelectedRegularPoster
from javscraper.models import MovieMetadata
from javscraper.service_logging import ServiceLogStore


class FailingProvider:
    site_name = "Failing"

    def __init__(self, client):
        self.client = client

    def fetch(self, code: str):
        raise Exception(f"boom {code}")


class SuccessProvider:
    site_name = "Success"

    def __init__(self, client):
        self.client = client

    def fetch(self, code: str):
        return MovieMetadata(
            code=code.upper(),
            title=f"{code.upper()} title",
            cover_url="https://example.com/poster.jpg",
            thumb_url="https://example.com/thumb.jpg",
            release_date="2024-04-01",
            duration_minutes="120",
            director="Director",
            maker="Maker",
            publisher="Publisher",
            series="Series",
            score="4.1",
            description="Summary",
            actresses=["Actor A", "Actor B"],
            genres=["Drama"],
            preview_images=["https://example.com/fanart.jpg"],
        )


class LowPosterProvider:
    site_name = "LowPoster"

    def __init__(self, client):
        self.client = client

    def fetch(self, code: str):
        return MovieMetadata(
            code=code.upper(),
            title="Primary title",
            description="Primary summary",
            actresses=["Actor A"],
            cover_url="https://example.com/low.jpg",
            thumb_url="https://example.com/low.jpg",
        )


class HighPosterProvider:
    site_name = "HighPoster"

    def __init__(self, client):
        self.client = client

    def fetch(self, code: str):
        return MovieMetadata(
            code=code.upper(),
            title="Secondary title",
            description="Secondary summary",
            actresses=["Actor B"],
            cover_url="https://example.com/high.jpg",
            thumb_url="https://example.com/high.jpg",
        )


class JavBusStyleProvider:
    site_name = "JavBus"
    stop_after_fanart_crop = True

    def __init__(self, client):
        self.client = client

    def fetch(self, code: str):
        return MovieMetadata(
            code=code.upper(),
            title="JavBus title",
            description="JavBus summary",
            cover_url="https://example.com/javbus-cover.jpg",
        )


class HeyzoSuccessProvider:
    site_name = "HEYZO"

    def __init__(self, client):
        self.client = client

    def fetch(self, code: str):
        return MovieMetadata(
            code=code.upper(),
            title=f"{code.upper()} title",
            cover_url="https://example.com/heyzo-cover.jpg",
        )


class EmbyServiceTests(unittest.TestCase):
    def setUp(self):
        self.log_store = ServiceLogStore()
        self.service = EmbyMovieService(
            provider_names=["Failing", "Success"],
            log_store=self.log_store,
            default_proxy=ProxyConfig(enabled=True, protocol="http", host="127.0.0.1", port="7890"),
        )

    def test_extract_emby_code_from_path_or_name(self):
        self.assertEqual(
            extract_emby_code(
                name="Random Title",
                path=r"D:\Media\ABP-123\ABP-123.mp4",
            ),
            "ABP-123",
        )
        self.assertEqual(
            extract_emby_code(
                name="fc2 ppv 1234567",
                path="",
            ),
            "FC2-1234567",
        )
        self.assertIsNone(extract_emby_code(name="hello world", path="/tmp/no-match.txt"))

    def test_fetch_from_providers_falls_back_to_second_provider(self):
        with patch.dict("javscraper.emby_service.PROVIDER_CLASSES", {"Failing": FailingProvider, "Success": SuccessProvider}, clear=False), patch(
            "javscraper.metadata_resolution.select_dmm_regular_poster_for_code",
            return_value=None,
        ), patch(
            "javscraper.metadata_resolution.select_best_regular_poster_for_metadata",
            return_value=None,
        ):
            resolved = self.service.fetch_from_providers("abp-123", requested_proxy=None)

        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(resolved.provider, "Success")
        self.assertEqual(resolved.provider_item_id, "ABP-123")
        self.assertTrue(any(entry["source"] == "emby-resolve" for entry in self.log_store.recent()))

    def test_fetch_from_providers_continues_for_regular_code_until_poster_meets_threshold(self):
        service = EmbyMovieService(
            provider_names=["LowPoster", "HighPoster"],
            log_store=self.log_store,
        )
        low_selection = SelectedRegularPoster(
            url="https://example.com/low.jpg",
            image_bytes=b"low",
            media_type="image/jpeg",
            width=147,
            height=200,
            mode="native",
            meets_threshold=False,
        )
        high_selection = SelectedRegularPoster(
            url="https://example.com/high.jpg",
            image_bytes=b"high",
            media_type="image/jpeg",
            width=600,
            height=900,
            mode="native",
            meets_threshold=True,
        )
        with patch.dict(
            "javscraper.emby_service.PROVIDER_CLASSES",
            {"LowPoster": LowPosterProvider, "HighPoster": HighPosterProvider},
            clear=False,
        ), patch(
            "javscraper.metadata_resolution.select_dmm_regular_poster_for_code",
            return_value=None,
        ), patch(
            "javscraper.metadata_resolution.select_best_regular_poster_for_metadata",
            side_effect=[low_selection, high_selection],
        ):
            resolved = service.fetch_from_providers("abp-123", requested_proxy=None)

        assert resolved is not None
        self.assertEqual(resolved.provider, "LowPoster")
        self.assertEqual(resolved.metadata.title, "Primary title")
        self.assertEqual(resolved.metadata.description, "Primary summary")
        self.assertEqual(resolved.metadata.actresses, ["Actor A"])
        self.assertEqual(
            resolved.metadata.native_poster_urls,
            ["https://example.com/low.jpg", "https://example.com/high.jpg"],
        )

    def test_fetch_from_providers_stops_on_javbus_when_fanart_crop_is_supported(self):
        service = EmbyMovieService(
            provider_names=["JavBus", "HighPoster"],
            log_store=self.log_store,
        )
        with patch.dict(
            "javscraper.emby_service.PROVIDER_CLASSES",
            {"JavBus": JavBusStyleProvider, "HighPoster": HighPosterProvider},
            clear=False,
        ), patch(
            "javscraper.metadata_resolution.select_dmm_regular_poster_for_code",
            return_value=None,
        ), patch(
            "javscraper.metadata_resolution.select_best_regular_poster_for_metadata",
            return_value=SelectedRegularPoster(
                url="https://example.com/javbus-cover.jpg",
                image_bytes=b"wide",
                media_type="image/jpeg",
                width=1200,
                height=800,
                mode="regular_crop",
            ),
        ):
            resolved = service.fetch_from_providers("abp-123", requested_proxy=None)

        assert resolved is not None
        self.assertEqual(resolved.provider, "JavBus")
        self.assertEqual(resolved.metadata.title, "JavBus title")
        self.assertEqual(resolved.metadata.description, "JavBus summary")
        self.assertEqual(resolved.metadata.native_poster_urls, [])

    def test_fetch_from_providers_locks_dmm_poster_before_provider_scrape(self):
        service = EmbyMovieService(
            provider_names=["Success", "HighPoster"],
            log_store=self.log_store,
        )
        dmm_selection = SelectedRegularPoster(
            url="https://pics.dmm.co.jp/digital/video/abp00123/abp00123pl.jpg",
            image_bytes=b"wide",
            media_type="image/jpeg",
            width=1200,
            height=800,
            mode="regular_crop",
        )
        with patch.dict(
            "javscraper.emby_service.PROVIDER_CLASSES",
            {"Success": SuccessProvider, "HighPoster": HighPosterProvider},
            clear=False,
        ), patch(
            "javscraper.metadata_resolution.select_dmm_regular_poster_for_code",
            return_value=dmm_selection,
        ), patch(
            "javscraper.metadata_resolution.select_best_regular_poster_for_metadata",
            side_effect=AssertionError("DMM 预检命中后不应再进入后续 poster 决策"),
        ):
            resolved = service.fetch_from_providers("abp-123", requested_proxy=None)

        assert resolved is not None
        self.assertEqual(resolved.provider, "Success")
        self.assertEqual(
            resolved.metadata.locked_regular_poster_url,
            "https://pics.dmm.co.jp/digital/video/abp00123/abp00123pl.jpg",
        )

    def test_fetch_from_providers_routes_special_code_to_special_sites_only(self):
        service = EmbyMovieService(
            provider_names=["JavBus", "HEYZO"],
            log_store=self.log_store,
        )

        class RegularShouldNotRunProvider:
            site_name = "JavBus"

            def __init__(self, client):
                self.client = client

            def fetch(self, code: str):
                raise AssertionError("特殊番号不应尝试普通番号站点")

        with patch.dict(
            "javscraper.emby_service.PROVIDER_CLASSES",
            {"JavBus": RegularShouldNotRunProvider, "HEYZO": HeyzoSuccessProvider},
            clear=False,
        ), patch(
            "javscraper.emby_service.get_javdb_cookie_status",
            return_value={"available": False, "reason": "not logged in"},
        ), patch(
            "javscraper.metadata_resolution.select_dmm_regular_poster_for_code",
            return_value=None,
        ), patch(
            "javscraper.metadata_resolution.select_best_regular_poster_for_metadata",
            return_value=None,
        ):
            resolved = service.fetch_from_providers("HEYZO-0841", requested_proxy=None)

        assert resolved is not None
        self.assertEqual(resolved.provider, "HEYZO")
        self.assertEqual(resolved.metadata.title, "HEYZO-0841 title")

    def test_plugin_proxy_overrides_default_proxy(self):
        requested = ProxyConfig(enabled=True, protocol="socks5", host="10.0.0.2", port="1080")
        effective = self.service.effective_proxy(requested)
        self.assertEqual(effective.url, "socks5://10.0.0.2:1080")

        fallback = self.service.effective_proxy(ProxyConfig())
        self.assertEqual(fallback.url, "http://127.0.0.1:7890")

    def test_serialize_movie_uses_cover_thumb_and_fanart_semantics(self):
        resolved = ResolvedMovie(
            provider="Success",
            provider_item_id="ABP-123",
            code="ABP-123",
            metadata=MovieMetadata(
                code="ABP-123",
                title="Movie title",
                cover_url="https://example.com/poster.jpg",
                thumb_url="https://example.com/thumb.jpg",
                preview_images=["https://example.com/fanart.jpg"],
            ),
        )
        payload = self.service.serialize_movie(resolved)
        self.assertEqual(payload["coverUrl"], "https://example.com/thumb.jpg")
        self.assertEqual(payload["thumbUrl"], "https://example.com/fanart.jpg")
        self.assertEqual(payload["fanartUrl"], "https://example.com/fanart.jpg")

    def test_serialize_movie_prefixes_title_for_emby_api(self):
        resolved = ResolvedMovie(
            provider="Success",
            provider_item_id="ABP-310",
            code="ABP-310",
            metadata=MovieMetadata(
                code="ABP-310",
                title="天然成分由来 輝月あんり汁120％",
                original_title="Original title",
                cover_url="https://example.com/poster.jpg",
            ),
        )

        payload = self.service.serialize_movie(resolved)

        self.assertEqual(payload["title"], "【ABP-310】天然成分由来 輝月あんり汁120％")
        self.assertEqual(payload["originalTitle"], "Original title")

    def test_serialize_movie_does_not_duplicate_prefixed_title(self):
        resolved = ResolvedMovie(
            provider="Success",
            provider_item_id="ABP-310",
            code="ABP-310",
            metadata=MovieMetadata(
                code="ABP-310",
                title="【ABP-310】天然成分由来 輝月あんり汁120％",
                cover_url="https://example.com/poster.jpg",
            ),
        )

        payload = self.service.serialize_movie(resolved)

        self.assertEqual(payload["title"], "【ABP-310】天然成分由来 輝月あんり汁120％")
        self.assertEqual(payload["originalTitle"], "【ABP-310】天然成分由来 輝月あんり汁120％")

    def test_serialize_movie_uses_prefixed_code_when_title_is_missing(self):
        resolved = ResolvedMovie(
            provider="Success",
            provider_item_id="ABP-310",
            code="ABP-310",
            metadata=MovieMetadata(
                code="ABP-310",
                cover_url="https://example.com/poster.jpg",
            ),
        )

        payload = self.service.serialize_movie(resolved)

        self.assertEqual(payload["title"], "【ABP-310】")
        self.assertEqual(payload["originalTitle"], "ABP-310")

    def test_get_image_uses_semantic_sources(self):
        with patch.dict("javscraper.emby_service.PROVIDER_CLASSES", {"Success": SuccessProvider}, clear=False):
            primary = self.service.get_image("primary", "Success", "ABP-123", requested_proxy=None)
            thumb = self.service.get_image("thumb", "Success", "ABP-123", requested_proxy=None)
            backdrop = self.service.get_image("backdrop", "Success", "ABP-123", requested_proxy=None)

        self.assertEqual(primary.url, "https://example.com/thumb.jpg")
        self.assertEqual(thumb.url, "https://example.com/fanart.jpg")
        self.assertEqual(backdrop.url, "https://example.com/fanart.jpg")


if __name__ == "__main__":
    unittest.main()
