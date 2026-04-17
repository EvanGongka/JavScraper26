from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import quote

from javscraper.providers.base import Provider, ProviderError


class AVBaseProvider(Provider):
    site_name = "AVBASE"
    base_url = "https://www.avbase.net"
    homepage_url = f"{base_url}/"

    def __init__(self, client=None) -> None:
        super().__init__(client)
        self._build_id: str | None = None

    def _request(self, url: str, *, referer: str | None = None, raise_for_status: bool = False):
        headers = {"referer": referer or self.homepage_url}
        return self.client.request(
            "GET",
            url,
            headers=headers,
            impersonate="chrome136",
            raise_for_status=raise_for_status,
        )

    def _get_build_id(self) -> str:
        if self._build_id:
            return self._build_id

        response = self._request(self.homepage_url)
        match = re.search(r'"buildId":"([^"]+)"', response.text)
        if not match:
            raise ProviderError(f"{self.site_name}: 无法获取 buildId")
        self._build_id = match.group(1)
        return self._build_id

    @staticmethod
    def _parse_date(value: str | None) -> str | None:
        text = (value or "").strip()
        if not text:
            return None
        text = re.sub(r"\s*\([^)]*\)\s*$", "", text)
        try:
            return datetime.strptime(text, "%a %b %d %Y %H:%M:%S GMT%z").strftime("%Y-%m-%d")
        except ValueError:
            return None

    def _search(self, code: str) -> dict:
        build_id = self._get_build_id()
        response = self._request(
            f"{self.base_url}/_next/data/{build_id}/works.json?q={quote(code)}"
        )
        payload = response.json()
        works = payload.get("pageProps", {}).get("works", [])
        if not works:
            raise ProviderError(f"{self.site_name}: 未找到 {code}")

        normalized = code.upper()
        for work in works:
            if str(work.get("work_id", "")).upper() == normalized:
                return work
        return works[0]

    def _fetch_detail(self, prefix: str, work_id: str) -> dict:
        build_id = self._get_build_id()
        compound_id = f"{prefix}:{work_id}"
        response = self._request(
            f"{self.base_url}/_next/data/{build_id}/works/{quote(compound_id)}.json?id={quote(compound_id)}"
        )
        payload = response.json()
        work = payload.get("pageProps", {}).get("work")
        if not work:
            raise ProviderError(f"{self.site_name}: 详情数据为空 {compound_id}")
        return work

    @staticmethod
    def _pick_primary_product(products: list[dict]) -> dict | None:
        if not products:
            return None
        source_priority = {"mgstage": 50, "fanza": 40, "duga": 30, "getchu": 20, "pcolle": 10}

        def sort_key(item: dict) -> tuple[int, int]:
            source = str(item.get("source", "")).lower()
            sample_count = len(item.get("sample_image_urls") or [])
            return (source_priority.get(source, 0), sample_count)

        return sorted(products, key=sort_key, reverse=True)[0]

    def fetch(self, code: str):
        search_work = self._search(code)
        prefix = str(search_work.get("prefix", "")).strip()
        work_id = str(search_work.get("work_id", "")).strip()
        if not prefix or not work_id:
            raise ProviderError(f"{self.site_name}: 缺少 prefix/work_id")

        detail_work = self._fetch_detail(prefix, work_id)
        metadata = self.create_metadata(code)

        products = detail_work.get("products") or search_work.get("products") or []
        primary_product = self._pick_primary_product(products) or {}
        iteminfo = primary_product.get("iteminfo") or {}

        metadata.code = work_id.upper()
        metadata.detail_url = f"{self.base_url}/works/{prefix}:{work_id}"
        metadata.title = self.clean_text(detail_work.get("title")) or self.clean_text(search_work.get("title")) or None
        metadata.cover_url = self.clean_url(primary_product.get("image_url")) or self.clean_url(
            primary_product.get("thumbnail_url")
        )
        metadata.thumb_url = self.clean_url(primary_product.get("thumbnail_url"))
        metadata.release_date = self._parse_date(detail_work.get("min_date")) or self._parse_date(
            primary_product.get("date")
        )
        metadata.duration_minutes = self.extract_duration(str(iteminfo.get("volume", "")))
        metadata.director = self.clean_text(iteminfo.get("director")) or None
        metadata.maker = self.clean_text((primary_product.get("maker") or {}).get("name")) or None
        metadata.publisher = self.clean_text((primary_product.get("label") or {}).get("name")) or None
        metadata.series = self.clean_text((primary_product.get("series") or {}).get("name")) or None
        metadata.description = self.clean_text(detail_work.get("note")) or None
        metadata.genres = self.unique(
            [self.clean_text(item.get("name")) for item in detail_work.get("genres") or [] if item.get("name")]
        )
        metadata.actresses = self.unique(
            [
                self.clean_text((item.get("actor") or {}).get("name"))
                for item in detail_work.get("casts") or []
                if (item.get("actor") or {}).get("name")
            ]
        )
        metadata.preview_images = self.unique(
            [
                self.clean_url(sample.get("l")) or self.clean_url(sample.get("s"))
                for sample in primary_product.get("sample_image_urls") or []
                if sample.get("l") or sample.get("s")
            ]
        )
        return metadata
