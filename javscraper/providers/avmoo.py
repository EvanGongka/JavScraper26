from __future__ import annotations

from javscraper.providers.base import Provider, ProviderError


class AVMOOProvider(Provider):
    site_name = "AVMOO"
    base_url = "https://avmoo.website"

    def fetch(self, code: str):
        search_url = f"{self.base_url}/cn/search/{code}"
        search_doc, _, _ = self.client.get_document(search_url, headers={"referer": f"{self.base_url}/cn"}, impersonate="chrome136")

        ids = [item.strip().lower() for item in search_doc.xpath("//div[contains(@class,'photo-info')]/span/date[1]/text()")]
        urls = search_doc.xpath("//a[contains(@href,'/movie/')]/@href")
        if code.lower() not in ids:
            raise ProviderError(f"{self.site_name}: 未找到 {code}")

        detail_url = urls[ids.index(code.lower())]
        detail_doc, detail_url, _ = self.client.get_document(detail_url, headers={"referer": search_url}, impersonate="chrome136")
        info_nodes = detail_doc.xpath("//div[contains(@class,'info')]")
        if not info_nodes:
            raise ProviderError(f"{self.site_name}: 页面结构异常")
        info = info_nodes[0]

        metadata = self.create_metadata(code)
        remote_code = self.clean_text(
            "".join(info.xpath(".//p[span[contains(text(),'识别码')]]/span/following-sibling::text()[1]"))
        )
        title = self.clean_text(detail_doc.xpath("string(//div[@class='container']//h3)"))

        metadata.code = remote_code or code
        metadata.detail_url = detail_url
        metadata.title = title.replace(metadata.code, "").strip() if title else None
        metadata.cover_url = self.clean_url("".join(detail_doc.xpath("//a[contains(@class,'bigImage')]/@href")))
        metadata.release_date = self.clean_text(
            "".join(info.xpath(".//p[span[contains(text(),'发行时间')]]/span/following-sibling::text()[1]"))
        ) or None
        metadata.duration_minutes = self.extract_duration(
            self.clean_text("".join(info.xpath(".//p[span[contains(text(),'长度')]]/span/following-sibling::text()[1]")))
        )
        metadata.director = self.clean_text("".join(info.xpath(".//p[span[contains(text(),'导演')]]/a/text()"))) or None
        metadata.maker = self.clean_text("".join(info.xpath(".//p[contains(text(),'制作商')]/a/text()"))) or None
        metadata.publisher = self.clean_text("".join(info.xpath(".//p[contains(text(),'发行商')]/a/text()"))) or None
        metadata.series = self.clean_text("".join(info.xpath(".//p[contains(text(),'系列')]/a/text()"))) or None
        metadata.genres = self.unique(detail_doc.xpath("//span[@class='genre']/a/text()"))
        metadata.actresses = self.unique(detail_doc.xpath("//a[@class='avatar-box']/span/text()"))
        metadata.preview_images = self.unique(detail_doc.xpath("//a[@class='sample-box']/@href"))
        return metadata
