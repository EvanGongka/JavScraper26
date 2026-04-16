from __future__ import annotations

import re
from lxml import html

from javscraper.providers.base import Provider, ProviderError


class FC2Provider(Provider):
    site_name = "FC2"
    base_url = "https://adult.contents.fc2.com"

    @staticmethod
    def _normalize_date(value: str | None) -> str | None:
        text = " ".join((value or "").split())
        if not text:
            return None
        match = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
        if not match:
            return text or None
        year, month, day = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"

    @staticmethod
    def _clean_title_node(title_node) -> str:
        for span in title_node.xpath(".//span"):
            style = (span.get("style") or "").lower()
            if any(token in style for token in ("zoom:0.01", "display:none", "overflow:hidden")):
                span.drop_tree()
        return " ".join(title_node.text_content().split())

    def _extract_runtime_minutes(self, value: str | None) -> str | None:
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
        return self.extract_duration(text)

    def fetch(self, code: str):
        fc2_id = re.sub(r"(?i)^FC2[^0-9]*", "", code).strip()
        if not fc2_id.isdigit():
            raise ProviderError(f"{self.site_name}: 不支持的编号 {code}")

        detail_url = f"{self.base_url}/article/{fc2_id}/"
        detail_doc, detail_url, response = self.client.get_document(
            detail_url,
            headers={"referer": f"{self.base_url}/"},
            impersonate="chrome136",
            raise_for_status=False,
        )
        if response.status_code != 200:
            raise ProviderError(f"{self.site_name}: 返回状态码 {response.status_code}")

        page_title = self.clean_text(detail_doc.xpath("string(//title)"))
        if any(
            text in page_title
            for text in ("非常抱歉，找不到您要的商品", "未找到您要找的商品", "お探しの商品が見つかりませんでした")
        ) or not detail_doc.xpath("//div[@class='items_article_headerInfo']"):
            raise ProviderError(f"{self.site_name}: 未找到 {code}")

        metadata = self.create_metadata(f"FC2-{fc2_id}")
        metadata.detail_url = detail_url

        title_nodes = detail_doc.xpath("//div[@class='items_article_headerInfo']/h3")
        if title_nodes:
            metadata.title = self._clean_title_node(title_nodes[0]) or None
        if not metadata.title:
            metadata.title = self.clean_text(detail_doc.xpath("string(//h3)")) or None

        metadata.genres = self.unique(
            [
                self.clean_text(item)
                for item in detail_doc.xpath(
                    "//section[@class='items_article_TagArea']//a/text()"
                )
            ]
        )
        metadata.maker = self.clean_text(
            detail_doc.xpath("string(//div[@class='items_article_headerInfo']//ul/li[last()]/a)")
        ) or None

        score_class = self.clean_text(
            detail_doc.xpath(
                "string(//li[contains(@class,'items_article_StarA')]//span/@class)"
            )
        )
        score_match = re.search(r"(\d+)$", score_class)
        if score_match:
            metadata.score = score_match.group(1)

        metadata.release_date = self._normalize_date(
            detail_doc.xpath("string(//div[contains(@class,'items_article_Releasedate')]/p)")
        ) or self._normalize_date(response.text)

        for node in detail_doc.xpath(
            "//div[@class='items_article_headerInfo']/div[@class='items_article_softDevice']/p"
        ):
            text = self.clean_text(node.text_content())
            if ":" not in text:
                continue
            key, value = [part.strip() for part in text.split(":", 1)]
            if key in {"Sale Day", "販売日"}:
                metadata.release_date = self._normalize_date(value) or metadata.release_date

        summary_iframe = self.clean_text(
            detail_doc.xpath("string(//section[@class='items_article_Contents']/iframe/@src)")
        )
        if summary_iframe:
            try:
                summary_response = self.client.request(
                    "GET",
                    summary_iframe,
                    headers={"referer": detail_url},
                    impersonate="chrome136",
                    raise_for_status=False,
                )
                if summary_response.status_code == 200 and summary_response.text.strip():
                    iframe_doc = html.fromstring(summary_response.text)
                    metadata.description = self.clean_text(iframe_doc.text_content()) or None
            except Exception:
                pass

        metadata.cover_url = self.clean_url(
            detail_doc.xpath("string(//div[@class='items_article_MainitemThumb']/span/img/@src)")
        )
        metadata.duration_minutes = self._extract_runtime_minutes(
            detail_doc.xpath(
                "string(//div[@class='items_article_MainitemThumb']//p[@class='items_article_info'])"
            )
        )
        metadata.preview_images = self.unique(
            [
                self.clean_url(url)
                for url in detail_doc.xpath(
                    "//section[@class='items_article_SampleImages']//li//a/@href"
                )
                if self.clean_url(url)
            ]
        )
        if not metadata.cover_url and metadata.preview_images:
            metadata.cover_url = metadata.preview_images[0]
        return metadata
