from __future__ import annotations

import re
from urllib.parse import urljoin

from javscraper.providers.base import Provider, ProviderError


class JavBooksProvider(Provider):
    site_name = "JavBooks"
    base_url = "https://javbooks.com"

    def _is_detail(self, document) -> bool:
        return bool(document.xpath("//div[@id='title']/b")) and bool(document.xpath("//div[@id='info']"))

    @staticmethod
    def _extract_code(text: str | None) -> str | None:
        match = re.search(r"([A-Z0-9]+)\s*[-_]\s*(\d+)", (text or "").upper())
        if match:
            return f"{match.group(1)}-{match.group(2)}"
        return None

    def fetch(self, code: str):
        search_doc, resolved_url, _ = self.client.post_document(
            f"{self.base_url}/serch_censored.htm",
            data={"skey": code},
            headers={"origin": self.base_url, "referer": f"{self.base_url}/", "content-type": "application/x-www-form-urlencoded"},
            impersonate="chrome136",
        )

        if self._is_detail(search_doc):
            detail_doc = search_doc
            detail_url = resolved_url
        else:
            results = []
            for node in search_doc.xpath("//div[@id='PoShow_Box']/div[contains(@class,'Po_topic')]"):
                detail_path = self.clean_text("".join(node.xpath(".//div[contains(@class,'Po_topic_title')]/a/@href")))
                serial_text = self.clean_text(node.xpath("string(.//div[contains(@class,'Po_topic_Date_Serial')])"))
                remote_code = self._extract_code(serial_text)
                if remote_code and detail_path:
                    results.append((remote_code, detail_path))

            matched = [detail for remote_code, detail in results if remote_code == code.upper()]
            if not matched:
                raise ProviderError(f"{self.site_name}: 未找到 {code}")
            detail_doc, detail_url, _ = self.client.get_document(
                urljoin(self.base_url, matched[0]),
                headers={"referer": resolved_url},
                impersonate="chrome136",
            )
            if not self._is_detail(detail_doc):
                raise ProviderError(f"{self.site_name}: 详情页结构异常")

        metadata = self.create_metadata(code)
        title = self.clean_text(detail_doc.xpath("string(//div[@id='title']/b)"))
        remote_code = self.clean_text(
            detail_doc.xpath("string(//div[@id='info']//div[contains(@class,'infobox')][b[contains(text(),'番號')]]/font/a[1])")
        )

        metadata.code = remote_code or self._extract_code(title) or code.upper()
        metadata.detail_url = detail_url
        metadata.title = title.replace(metadata.code, "").strip() if title and title.upper().startswith(metadata.code.upper()) else title or None
        metadata.cover_url = self.clean_url(
            detail_doc.xpath("string(//div[@id='info']//div[contains(@class,'info_cg')]//img/@src)")
        )
        metadata.release_date = self.clean_text(
            detail_doc.xpath("string(//div[@id='info']//div[contains(@class,'infobox')][b[contains(text(),'發行時間')]])")
        ).replace("發行時間：", "").strip() or None
        metadata.duration_minutes = self.extract_duration(
            self.clean_text(
                detail_doc.xpath("string(//div[@id='info']//div[contains(@class,'infobox')][b[contains(text(),'影片時長')]])")
            ).replace("影片時長：", "")
        )
        metadata.director = self.clean_text(
            detail_doc.xpath("string(//div[@id='info']//div[contains(@class,'infobox')][b[contains(text(),'導演')]]/a[1])")
        ) or None
        metadata.maker = self.clean_text(
            detail_doc.xpath("string(//div[@id='info']//div[contains(@class,'infobox')][b[contains(text(),'製作商')]]/a[1])")
        ) or None
        metadata.publisher = self.clean_text(
            detail_doc.xpath("string(//div[@id='info']//div[contains(@class,'infobox')][b[contains(text(),'發行商')]]/a[1])")
        ) or None
        metadata.series = self.clean_text(
            detail_doc.xpath("string(//div[@id='info']//div[contains(@class,'infobox')][b[contains(text(),'系列')]]/a[1])")
        ) or None
        metadata.genres = self.unique(
            [
                self.clean_text(item)
                for item in detail_doc.xpath("//div[@id='info']//div[contains(@class,'infobox')][b[contains(text(),'影片類別')]]//a/text()")
                if not re.fullmatch(r"\d+", self.clean_text(item))
            ]
        )
        metadata.actresses = self.unique(
            detail_doc.xpath("//div[@id='info']//div[contains(@class,'infobox')][b[contains(text(),'女優')]]//div[contains(@class,'av_performer_name_box')]/a/text()")
        )
        metadata.preview_images = self.unique(detail_doc.xpath("//div[contains(@class,'gallery')]//a/@href"))
        metadata.trailer_url = self.clean_url("".join(detail_doc.xpath("//div[@id='Preview_vedio_box']//iframe/@src")))
        return metadata
