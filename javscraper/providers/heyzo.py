from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from javscraper.providers.base import Provider, ProviderError


class HEYZOProvider(Provider):
    site_name = "HEYZO"
    base_url = "https://www.heyzo.com"

    @staticmethod
    def _normalize_id(code: str) -> str:
        match = re.search(r"(?i)(?:HEYZO[-_ ]?)?(\d{3,4})", code.strip())
        if not match:
            raise ProviderError(f"HEYZO: 不支持的编号 {code}")
        return match.group(1).zfill(4)

    @staticmethod
    def _normalize_date(value: str | None) -> str | None:
        text = " ".join((value or "").split())
        if not text:
            return None
        match = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
        if not match:
            return None
        year, month, day = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"

    @staticmethod
    def _parse_iso_duration(value: str | None) -> str | None:
        text = (value or "").strip()
        if not text:
            return None
        match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", text)
        if not match:
            digits = re.search(r"(\d+)", text)
            return digits.group(1) if digits else None
        hours, minutes, seconds = (int(part or 0) for part in match.groups())
        total_seconds = hours * 3600 + minutes * 60 + seconds
        return str(max(1, total_seconds // 60))

    @staticmethod
    def _parse_runtime_text(value: str | None) -> str | None:
        text = " ".join((value or "").split())
        if not text:
            return None
        match = re.search(r"(\d+):(\d{2})(?::(\d{2}))?", text)
        if match:
            first, second, third = match.groups()
            if third is None:
                total_seconds = int(first) * 60 + int(second)
            else:
                total_seconds = int(first) * 3600 + int(second) * 60 + int(third)
            return str(max(1, total_seconds // 60))
        return Provider.extract_duration(text)

    def fetch(self, code: str):
        movie_id = self._normalize_id(code)
        detail_url = f"{self.base_url}/moviepages/{movie_id}/index.html"
        document, detail_url, _ = self.client.get_document(
            detail_url,
            headers={"referer": f"{self.base_url}/"},
            raise_for_status=False,
        )

        page_title = self.clean_text(document.xpath("string(//title)"))
        if not page_title or "ページが見つかりません" in page_title:
            raise ProviderError(f"{self.site_name}: 未找到 {code}")

        metadata = self.create_metadata(f"HEYZO-{movie_id}")
        metadata.detail_url = detail_url
        metadata.maker = "HEYZO"

        ld_json = document.xpath("//script[@type='application/ld+json']/text()")
        for raw in ld_json:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if data.get("name") and not metadata.title:
                metadata.title = self.clean_text(data.get("name")) or None
            if data.get("description") and not metadata.description:
                metadata.description = self.clean_text(data.get("description")) or None
            if data.get("image") and not metadata.cover_url:
                metadata.cover_url = self.clean_url(urljoin(detail_url, data.get("image")))
            released = ((data.get("releasedEvent") or {}).get("startDate")) if isinstance(data, dict) else None
            metadata.release_date = self._normalize_date(released) or metadata.release_date
            duration = ((data.get("video") or {}).get("duration")) if isinstance(data, dict) else None
            metadata.duration_minutes = self._parse_iso_duration(duration) or metadata.duration_minutes
            actor = ((data.get("video") or {}).get("actor")) if isinstance(data, dict) else None
            if actor and not metadata.actresses:
                metadata.actresses = [self.clean_text(actor)]
            provider_name = ((data.get("video") or {}).get("provider")) if isinstance(data, dict) else None
            if provider_name:
                metadata.maker = self.clean_text(provider_name) or metadata.maker
            rating = ((data.get("aggregateRating") or {}).get("ratingValue")) if isinstance(data, dict) else None
            if rating:
                metadata.score = self.clean_text(str(rating)) or metadata.score

        if not metadata.title:
            heading = self.clean_text(document.xpath("string(//*[@id='movie']/h1)"))
            if heading:
                metadata.title = heading.split(" - ", 1)[0].strip()

        if not metadata.description:
            metadata.description = self.clean_text(document.xpath("string(//p[@class='memo'])")) or None

        if not metadata.cover_url:
            metadata.cover_url = self.clean_url(
                urljoin(detail_url, document.xpath("string(//meta[@property='og:image']/@content)"))
            )

        for row in document.xpath("//table[contains(@class,'movieInfo')]/tbody/tr"):
            label = self.clean_text(row.xpath("string(.//td[1])"))
            value = self.clean_text(row.xpath("string(.//td[2])"))
            if label == "公開日":
                metadata.release_date = self._normalize_date(value) or metadata.release_date
            elif label == "出演":
                actresses = self.unique(
                    [self.clean_text(item) for item in row.xpath(".//td[2]//a//span/text()") if item]
                )
                if actresses:
                    metadata.actresses = actresses
            elif label == "シリーズ":
                metadata.series = value.strip("-").strip() or metadata.series
            elif label == "評価":
                score = self.clean_text(row.xpath("string(.//span[@itemprop='ratingValue'])")) or value
                metadata.score = score or metadata.score

        metadata.genres = self.unique(
            [self.clean_text(item) for item in document.xpath("//ul[@class='tag-keyword-list']//li/a/text()") if item]
        )

        for script in document.xpath("//script/text()"):
            if not metadata.trailer_url:
                match = re.search(r'emvideo\s*=\s*"(.+?)";', script)
                if match:
                    metadata.trailer_url = self.clean_url(urljoin(detail_url, match.group(1)))

            if not metadata.duration_minutes:
                match = re.search(r"o\s*=\s*(\{.+?});", script, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group(1))
                    except json.JSONDecodeError:
                        data = {}
                    metadata.duration_minutes = self._parse_runtime_text(str(data.get("full"))) or metadata.duration_minutes

            if not metadata.preview_images and "sample-images" in script:
                metadata.preview_images = self.unique(
                    [
                        self.clean_url(urljoin(detail_url, match))
                        for match in re.findall(r'"(/contents/.+?/\d+\.\w+?)"', script)
                    ]
                )

        if not metadata.cover_url and metadata.preview_images:
            metadata.cover_url = metadata.preview_images[0]
        if not metadata.title or not metadata.cover_url:
            raise ProviderError(f"{self.site_name}: 未找到 {code}")
        return metadata
