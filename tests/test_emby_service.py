from __future__ import annotations

import unittest
from unittest.mock import patch

from javscraper.emby_service import EmbyMovieService, ProxyConfig, ResolvedMovie, extract_emby_code
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
        with patch.dict("javscraper.emby_service.PROVIDER_CLASSES", {"Failing": FailingProvider, "Success": SuccessProvider}, clear=False):
            resolved = self.service.fetch_from_providers("abp-123", requested_proxy=None)

        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(resolved.provider, "Success")
        self.assertEqual(resolved.provider_item_id, "ABP-123")
        self.assertTrue(any(entry["source"] == "emby-resolve" for entry in self.log_store.recent()))

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
        self.assertEqual(payload["thumbUrl"], "https://example.com/thumb.jpg")
        self.assertEqual(payload["fanartUrl"], "https://example.com/thumb.jpg")

    def test_get_image_uses_semantic_sources(self):
        with patch.dict("javscraper.emby_service.PROVIDER_CLASSES", {"Success": SuccessProvider}, clear=False):
            primary = self.service.get_image("primary", "Success", "ABP-123", requested_proxy=None)
            thumb = self.service.get_image("thumb", "Success", "ABP-123", requested_proxy=None)
            backdrop = self.service.get_image("backdrop", "Success", "ABP-123", requested_proxy=None)

        self.assertEqual(primary.url, "https://example.com/thumb.jpg")
        self.assertEqual(thumb.url, "https://example.com/thumb.jpg")
        self.assertEqual(backdrop.url, "https://example.com/thumb.jpg")


if __name__ == "__main__":
    unittest.main()
