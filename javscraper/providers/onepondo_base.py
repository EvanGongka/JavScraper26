from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from javscraper.providers.base import Provider, ProviderError


class OnePondoFamilyProvider(Provider):
    base_url = ""
    movie_url_template = ""
    sample_video_url_template = ""
    maker_name = ""
    gallery_path = ""
    legacy_gallery_path = ""
    id_pattern = ""

    def _normalize_id(self, code: str) -> str:
        upper = code.upper().strip()
        candidate = upper.replace("-", "_")
        if self.id_pattern and re.fullmatch(self.id_pattern, candidate):
            return candidate
        raise ProviderError(f"{self.site_name}: 不支持的编号 {code}")

    def _request_json(self, url: str) -> dict:
        response = self.client.request(
            "GET",
            url,
            headers={
                "referer": self.base_url,
                "content-type": "application/json",
                "connection": "keep-alive",
            },
            raise_for_status=False,
        )
        if response.status_code != 200:
            raise ProviderError(f"{self.site_name}: 返回状态码 {response.status_code}")
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise ProviderError(f"{self.site_name}: JSON 解析失败") from exc

    @staticmethod
    def _normalize_date(value: str | None) -> str | None:
        text = (value or "").strip()
        if not text:
            return None
        match = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
        if not match:
            return None
        year, month, day = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"

    def _cover_url_from_detail(self, data: dict) -> str | None:
        for key in ("ThumbUltra", "ThumbHigh", "ThumbMed", "ThumbLow"):
            value = self.clean_url(data.get(key))
            if value:
                return urljoin(self.base_url, value.replace("https:///", "/"))
        thumb = self.clean_url(data.get("MovieThumb"))
        return urljoin(self.base_url, thumb) if thumb else None

    def _preview_images(self, movie_id: str, data: dict) -> list[str]:
        if data.get("Gallery") and self.gallery_path:
            try:
                gallery_data = self._request_json(urljoin(self.base_url, f"/dyn/dla/json/movie_gallery/{movie_id}.json"))
                return self.unique(
                    [
                        urljoin(self.base_url, self.gallery_path % row["Img"])
                        for row in gallery_data.get("Rows", [])
                        if not row.get("Protected") and row.get("Img")
                    ]
                )
            except ProviderError:
                return []

        if data.get("HasGallery") and self.legacy_gallery_path:
            try:
                gallery_data = self._request_json(
                    urljoin(self.base_url, f"/dyn/phpauto/movie_galleries/movie_id/{movie_id}.json")
                )
                return self.unique(
                    [
                        urljoin(self.base_url, self.legacy_gallery_path % (row["MovieID"], row["Filename"]))
                        for row in gallery_data.get("Rows", [])
                        if not row.get("Protected") and row.get("MovieID") and row.get("Filename")
                    ]
                )
            except ProviderError:
                return []

        return []

    def _trailer_url(self, movie_id: str, data: dict) -> str | None:
        sample_files = data.get("SampleFiles") or []
        if sample_files:
            best = sorted(sample_files, key=lambda item: item.get("FileSize", 0))[-1]
            if best.get("URL"):
                return urljoin(self.base_url, best["URL"])
        if self.sample_video_url_template:
            return self.sample_video_url_template % movie_id
        return None

    def fetch(self, code: str):
        movie_id = self._normalize_id(code)
        detail_url = self.movie_url_template % movie_id
        data = self._request_json(urljoin(self.base_url, f"/dyn/phpauto/movie_details/movie_id/{movie_id}.json"))
        if not data.get("MovieID") or not data.get("Title"):
            raise ProviderError(f"{self.site_name}: 未找到 {code}")

        metadata = self.create_metadata(code.upper())
        metadata.code = movie_id.replace("_", "-")
        metadata.detail_url = detail_url
        metadata.title = self.clean_text(data.get("Title")) or None
        metadata.description = self.clean_text(data.get("Desc")) or None
        metadata.cover_url = self.clean_url(self._cover_url_from_detail(data))
        metadata.release_date = self._normalize_date(data.get("Release"))
        metadata.duration_minutes = str(int(int(data["Duration"]) / 60)) if data.get("Duration") else None
        metadata.maker = self.maker_name or None
        metadata.series = self.clean_text(data.get("Series")) or None
        metadata.score = str(data.get("AvgRating")) if data.get("AvgRating") else None
        metadata.trailer_url = self.clean_url(self._trailer_url(movie_id, data))
        metadata.genres = self.unique([self.clean_text(item) for item in data.get("UCNAME") or [] if item])
        metadata.actresses = self.unique(
            [self.clean_text(item).strip("-").strip() for item in data.get("ActressesJa") or [] if item]
        )
        metadata.preview_images = self._preview_images(movie_id, data)
        return metadata
