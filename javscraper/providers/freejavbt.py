from __future__ import annotations

import re

from javscraper.providers.base import Provider, ProviderError


class FreeJavBTProvider(Provider):
    site_name = "FreeJavBT"
    base_url = "https://freejavbt.com"

    def _is_detail(self, document) -> bool:
        return bool(document.xpath("//div[contains(@class,'single-video-info')]")) and bool(document.xpath("//h1"))

    def _detail_page(self, code: str):
        direct_url = f"{self.base_url}/zh/{code.upper()}"
        document, resolved, _ = self.client.get_document(
            direct_url,
            headers={"referer": f"{self.base_url}/zh"},
            impersonate="chrome136",
            raise_for_status=False,
        )
        if self._is_detail(document):
            return document, resolved

        search_url = f"{self.base_url}/zh/search?wd={code}"
        search_doc, _, _ = self.client.get_document(
            search_url,
            headers={"referer": f"{self.base_url}/zh"},
            impersonate="chrome136",
        )
        candidates = search_doc.xpath("//div[contains(@class,'card')]//a[starts-with(@href, 'https://freejavbt.com/zh/')]/@href")
        matched = [item for item in candidates if item.rstrip("/").split("/")[-1].upper() == code.upper()]
        if not matched:
            raise ProviderError(f"{self.site_name}: 未找到 {code}")
        detail_doc, detail_url, _ = self.client.get_document(
            matched[0],
            headers={"referer": search_url},
            impersonate="chrome136",
        )
        if not self._is_detail(detail_doc):
            raise ProviderError(f"{self.site_name}: 详情页结构异常")
        return detail_doc, detail_url

    def fetch(self, code: str):
        detail_doc, detail_url = self._detail_page(code)
        metadata = self.create_metadata(code)

        raw_code = self.clean_text(" ".join(detail_doc.xpath("//div[contains(@class,'single-video-meta')][contains(@class,'code')]//text()")))
        code_match = re.search(r"([A-Z0-9]+)\s*-\s*(\d+)", raw_code.upper())
        remote_code = f"{code_match.group(1)}-{code_match.group(2)}" if code_match else code.upper()
        title = self.clean_text(detail_doc.xpath("string(//h1)"))
        title = re.sub(r"\s*免费AV在线看\s*$", "", title).strip()

        metadata.code = remote_code
        metadata.detail_url = detail_url
        metadata.title = title.replace(remote_code, "").strip() if title.upper().startswith(remote_code) else title
        metadata.cover_url = self.clean_url("".join(detail_doc.xpath("//video/@poster")))
        metadata.trailer_url = self.clean_url("".join(detail_doc.xpath("//video/@src")))
        metadata.release_date = self.clean_text(
            detail_doc.xpath("string(//div[contains(@class,'single-video-meta')][span[contains(text(),'日期')]]/span[2])")
        ) or None
        metadata.duration_minutes = self.extract_duration(
            detail_doc.xpath("string(//div[contains(@class,'single-video-meta')][span[contains(text(),'时长')]]/span[2])")
        )
        metadata.director = self.clean_text(
            detail_doc.xpath("string(//div[contains(@class,'director')]//a[1])")
        ) or None
        metadata.publisher = self.clean_text(
            detail_doc.xpath("string(//div[contains(@class,'publisher')]//a[1])")
        ) or None
        metadata.maker = self.clean_text(
            detail_doc.xpath("string(//div[contains(@class,'maker')]//a[1])")
        ) or None
        metadata.series = self.clean_text(
            detail_doc.xpath("string(//div[contains(@class,'series')]//a[1])")
        ) or None
        metadata.genres = self.unique(
            [self.clean_text(value) for value in detail_doc.xpath("//div[contains(@class,'single-video-meta')][span[contains(text(),'类别')]]//a/text()")]
        )
        actresses = self.unique(
            [
                self.clean_text(value)
                for value in detail_doc.xpath("//div[contains(@class,'single-video-meta')][span[contains(text(),'女优')]]//a[not(contains(@class,'text-primary'))]/text()")
            ]
        )
        metadata.actresses = actresses if len(actresses) == 1 else []
        metadata.preview_images = self.unique(detail_doc.xpath("//div[contains(@class,'preview')]//a[contains(@class,'tile-item')]/@href"))
        return metadata
