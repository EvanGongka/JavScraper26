from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import urljoin

from lxml import html

from javscraper.providers.base import Provider, ProviderError


class CaribbeanFamilyProvider(Provider):
    base_url = ""
    movie_url_template = ""
    maker_name = ""

    def _normalize_id(self, code: str) -> str:
        raise NotImplementedError

    @staticmethod
    def _canonical_code(movie_id: str) -> str:
        return movie_id.replace("_", "-")

    @staticmethod
    def _extract_charset(response) -> str | None:
        content_type = response.headers.get("content-type", "")
        match = re.search(r"charset=([A-Za-z0-9._-]+)", content_type, re.IGNORECASE)
        if match:
            return match.group(1)

        head = response.content[:8192]
        for pattern in (
            br"<meta[^>]+charset=['\"]?\s*([A-Za-z0-9._-]+)",
            br"<meta[^>]+content=['\"][^>]*charset=([A-Za-z0-9._-]+)",
        ):
            meta_match = re.search(pattern, head, re.IGNORECASE)
            if meta_match:
                return meta_match.group(1).decode("ascii", errors="ignore")

        apparent_encoding = getattr(response, "apparent_encoding", None)
        if apparent_encoding:
            return apparent_encoding

        response_encoding = getattr(response, "encoding", None)
        if response_encoding and response_encoding.lower() != "iso-8859-1":
            return response_encoding
        return None

    def _request_document(self, url: str):
        response = self.client.request(
            "GET",
            url,
            headers={"referer": self.base_url},
            raise_for_status=False,
        )
        if response.status_code != 200:
            raise ProviderError(f"{self.site_name}: 返回状态码 {response.status_code}")

        encoding = self._extract_charset(response) or "utf-8"
        text = response.content.decode(encoding, errors="replace")
        document = html.fromstring(text)
        document.make_links_absolute(str(response.url), resolve_base_href=True)
        return document, str(response.url), text

    def _first_text(self, document, selectors: list[str]) -> str:
        for selector in selectors:
            value = self.clean_text(document.xpath(f"string({selector})"))
            if value:
                return value
        return ""

    def _spec_rows(self, document) -> dict[str, dict[str, list[str] | str]]:
        rows: dict[str, dict[str, list[str] | str]] = {}
        for node in document.xpath("//*[@id='moviepages']//li[.//span]"):
            key = self.clean_text(
                node.xpath("string((.//span[contains(@class,'spec-title')][1] | .//span[1])[1])")
            )
            if not key:
                continue

            value_node = node.xpath("(.//span[contains(@class,'spec-content')][1] | .//span[2])[1]")
            if value_node:
                value_text = self.clean_text(value_node[0].text_content())
                links = self.unique([self.clean_text(item) for item in value_node[0].xpath(".//a/text()") if item])
            else:
                value_text = self.clean_text(node.text_content().replace(key, "", 1))
                links = self.unique([self.clean_text(item) for item in node.xpath(".//a/text()") if item])

            rows[key] = {"text": value_text, "links": links}
        return rows

    @staticmethod
    def _runtime_minutes(value: str | None) -> str | None:
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
        duration_match = re.search(r"(\d+)", text)
        return duration_match.group(1) if duration_match else None

    def _release_date(self, movie_id: str, specs: dict[str, dict[str, list[str] | str]]) -> str | None:
        for key in ("配信日", "販売日"):
            value = str(specs.get(key, {}).get("text", ""))
            match = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", value)
            if match:
                year, month, day = match.groups()
                return f"{year}-{int(month):02d}-{int(day):02d}"

        match = re.match(r"(\d{6})[-_]\d{3}$", movie_id)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%m%d%y").strftime("%Y-%m-%d")
        except ValueError:
            return None

    def _cover_url(self, page_text: str, movie_id: str, detail_url: str) -> str | None:
        match = re.search(r"emimg\s*=\s*'(.+?)';", page_text)
        if match:
            return self.clean_url(urljoin(detail_url, match.group(1)))

        match = re.search(r"posterImage\s*=\s*'(.+?)'\+movie_id\+'(.+?)';", page_text)
        if match:
            return self.clean_url(urljoin(detail_url, f"{match.group(1)}{movie_id}{match.group(2)}"))
        return None

    def _trailer_url(self, page_text: str, detail_url: str) -> str | None:
        match = re.search(r"Movie\s*=\s*(\{.+?});", page_text, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            return None

        for key in ("sample_flash_url", "sample_m_flash_url"):
            value = self.clean_url(data.get(key))
            if value:
                return urljoin(detail_url, value)
        return None

    def fetch(self, code: str):
        movie_id = self._normalize_id(code)
        detail_url = self.movie_url_template % movie_id
        document, detail_url, page_text = self._request_document(detail_url)

        title = self._first_text(
            document,
            [
                "(//h1[@itemprop='name'])[1]",
                "(//*[@id='moviepages']//div[contains(@class,'heading')]/h1[1])[1]",
                "(//*[@id='moviepages']//h1[1])[1]",
            ],
        )
        if not title:
            raise ProviderError(f"{self.site_name}: 未找到 {code}")

        description = self._first_text(
            document,
            [
                "(//p[@itemprop='description'])[1]",
                "(//*[@id='moviepages']//div[contains(@class,'heading')]/following-sibling::p[1])[1]",
            ],
        )
        specs = self._spec_rows(document)

        actresses = specs.get("出演", {}).get("links") or []
        if not actresses:
            actress_text = str(specs.get("出演", {}).get("text", ""))
            actresses = [actress_text] if actress_text else []

        genres = specs.get("タグ", {}).get("links") or []
        if not genres:
            genre_text = str(specs.get("タグ", {}).get("text", ""))
            genres = [item for item in re.split(r"\s+", genre_text) if item]

        score_text = str(specs.get("ユーザー評価", {}).get("text", ""))
        score = str(score_text.count("★")) if "★" in score_text else None

        metadata = self.create_metadata(self._canonical_code(movie_id))
        metadata.code = self._canonical_code(movie_id)
        metadata.detail_url = detail_url
        metadata.title = title or None
        metadata.description = description or None
        metadata.cover_url = self._cover_url(page_text, movie_id, detail_url)
        metadata.release_date = self._release_date(movie_id, specs)
        metadata.duration_minutes = self._runtime_minutes(str(specs.get("再生時間", {}).get("text", "")))
        metadata.maker = self.maker_name or str(specs.get("スタジオ", {}).get("text", "")) or None
        metadata.series = str(specs.get("シリーズ", {}).get("text", "")) or None
        metadata.score = score
        metadata.trailer_url = self._trailer_url(page_text, detail_url)
        metadata.actresses = self.unique([self.clean_text(item) for item in actresses if item])
        metadata.genres = self.unique([self.clean_text(item) for item in genres if item])
        metadata.preview_images = self.unique(
            [
                self.clean_url(url)
                for url in document.xpath("//div[contains(@class,'gallery-ratio')]//a/@href")
                if self.clean_url(url) and "/member/" not in self.clean_url(url)
            ]
        )
        if not metadata.cover_url and metadata.preview_images:
            metadata.cover_url = metadata.preview_images[0]
        return metadata
