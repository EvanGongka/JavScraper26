from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from javscraper.providers.base import Provider, ProviderError


class HeyDougaProvider(Provider):
    site_name = "HeyDouga"
    base_url = "https://www.heydouga.com"
    access_cookies = {
        "lang": "ja",
        "over18_ppv": "1",
        "feature_group": "1",
    }

    @staticmethod
    def _normalize_id(code: str) -> str:
        match = re.search(r"(?i)(?:HEYDOUGA[-_ ]?)?(\d{4})[-_ ]([A-Z0-9]{3,4})", code.strip())
        if not match:
            raise ProviderError(f"HeyDouga: 不支持的编号 {code}")
        return f"{match.group(1)}-{match.group(2)}"

    @staticmethod
    def _canonical_code(movie_id: str) -> str:
        return f"HEYDOUGA-{movie_id}"

    @staticmethod
    def _split_id(movie_id: str) -> tuple[str, str]:
        provider_id, movie_no = movie_id.split("-", 1)
        return provider_id, movie_no

    def _request_json(self, method: str, url: str, **kwargs) -> dict:
        response = self.client.request(
            method,
            url,
            cookies=self.access_cookies,
            raise_for_status=False,
            **kwargs,
        )
        if response.status_code != 200:
            raise ProviderError(f"{self.site_name}: 接口返回状态码 {response.status_code}")
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise ProviderError(f"{self.site_name}: 接口 JSON 解析失败") from exc

    @staticmethod
    def _split_actresses(value: str) -> list[str]:
        cleaned = re.sub(r"^(?:期間限定配信|おすすめ)\s*", "", value).strip()
        if not cleaned:
            return []
        if re.search(r"[、/,，]", cleaned):
            return [item.strip() for item in re.split(r"[、/,，]", cleaned) if item.strip()]
        if re.fullmatch(r"[\u3040-\u30ff\u3400-\u9fff\s]+", cleaned) and " " in cleaned:
            return [item.strip() for item in cleaned.split() if item.strip()]
        return [cleaned]

    @staticmethod
    def _clean_title(value: str) -> str:
        title = value.strip()
        changed = True
        while changed:
            changed = False
            for suffix in ("単品販売", "見放題"):
                if title.endswith(suffix):
                    title = title[: -len(suffix)].strip()
                    changed = True
        return title

    def fetch(self, code: str):
        movie_id = self._normalize_id(code)
        provider_id, movie_no = self._split_id(movie_id)
        detail_url = f"{self.base_url}/moviepages/{provider_id}/{movie_no}/index.html"
        document, detail_url, response = self.client.get_document(
            detail_url,
            headers={"referer": f"{self.base_url}/"},
            cookies=self.access_cookies,
            raise_for_status=False,
        )
        if response.status_code != 200:
            raise ProviderError(f"{self.site_name}: 返回状态码 {response.status_code}")

        title_heading = self.clean_text(document.xpath("string(//*[@id='contents-header']//h1)"))
        if not title_heading:
            raise ProviderError(f"{self.site_name}: 未找到 {code}")

        metadata = self.create_metadata(self._canonical_code(movie_id))
        metadata.code = self._canonical_code(movie_id)
        metadata.detail_url = detail_url

        title_parts = [part.strip() for part in title_heading.split(" - ", 1)]
        if len(title_parts) == 2:
            actress_text, title_text = title_parts
            metadata.title = self._clean_title(title_text) or title_heading
            metadata.actresses = self.unique([self.clean_text(item) for item in self._split_actresses(actress_text)])
        else:
            metadata.title = self._clean_title(title_heading) or None

        metadata.description = self.clean_text(
            document.xpath("string(//*[@id='movie-detail-mobile']//div[contains(@class,'movie-description')]/p[1])")
        ) or None
        metadata.maker = self.clean_text(
            document.xpath("string((//ul[@class='breadcrumbs']//li/a)[last()])")
        ) or None

        page_text = response.text
        poster_match = re.search(r'player_poster\s*=\s*[\'"](.+?)[\'"]', page_text)
        if poster_match:
            metadata.cover_url = self.clean_url(urljoin(detail_url, poster_match.group(1)))

        trailer_match = re.search(r'source\s*=\s*[\'"](.+?\.m3u8[^\'"]*)[\'"]', page_text)
        if trailer_match:
            metadata.trailer_url = self.clean_url(urljoin(detail_url, trailer_match.group(1)))

        file_type_url = f"https://hls-ppv.heydouga.com/sample/{provider_id}/{movie_no}/file_type.php?format=javascript&is_vip=0"
        file_type_response = self.client.request(
            "GET",
            file_type_url,
            headers={"referer": detail_url},
            cookies=self.access_cookies,
            raise_for_status=False,
        )
        if file_type_response.status_code == 200:
            match = re.search(r"movie_file_status\s*=\s*(\{.+\});", file_type_response.text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                except json.JSONDecodeError:
                    data = {}
                bitrates = (((data.get("whole") or {}).get("file") or {}).get("bitrate") or {})
                for rows in bitrates.values():
                    if rows and rows[0].get("duration"):
                        duration_seconds = int(rows[0]["duration"])
                        if duration_seconds >= 600:
                            metadata.duration_minutes = str(max(1, duration_seconds // 60))
                        break

        rating_match = re.search(r'url_get_movie_rating\s*=\s*"(.+?)";', page_text)
        if rating_match:
            rating_data = self._request_json("GET", urljoin(detail_url, rating_match.group(1)))
            metadata.score = self.clean_text(str(rating_data.get("movie_rating_average"))) or None

        provider_id_match = re.search(r"provider_id\s*=\s*(\d+);", page_text)
        movie_seq_match = re.search(r"movie_seq\s*[:=]\s*(\d+)", page_text)
        if provider_id_match and movie_seq_match:
            tag_data = self._request_json(
                "POST",
                f"{self.base_url}/get_movie_tag_all/",
                data={
                    "movie_seq": movie_seq_match.group(1),
                    "provider_id": provider_id_match.group(1),
                    "lang": "ja",
                },
                headers={"referer": detail_url},
            )
            metadata.genres = self.unique(
                [self.clean_text(item.get("tag_name")) for item in tag_data.get("tag", []) if item.get("tag_name")]
            )

        if not metadata.title or not metadata.cover_url:
            raise ProviderError(f"{self.site_name}: 未找到 {code}")
        return metadata
