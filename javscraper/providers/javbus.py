from __future__ import annotations

from javscraper.providers.base import Provider, ProviderError


class JavBusProvider(Provider):
    site_name = "JavBus"
    stop_after_fanart_crop = True
    hosts = ("https://www.seedmm.help", "https://www.javbus.com")

    def fetch(self, code: str):
        last_error = None
        document = None
        detail_url = None

        for host in self.hosts:
            try:
                document, detail_url, _ = self.client.get_document(
                    f"{host}/{code}",
                    cookies={"age": "verified"},
                    allow_redirects=False,
                )
                title_text = self.clean_text("".join(document.xpath("/html/head/title/text()")))
                if title_text in {"Redirecting...", "Age Verification JavBus"}:
                    continue
                if title_text.startswith("404 Page Not Found!"):
                    raise ProviderError(f"{self.site_name}: 未找到 {code}")
                break
            except Exception as exc:
                last_error = exc
                continue

        if document is None or detail_url is None:
            raise ProviderError(str(last_error or f"{self.site_name}: 详情页不可访问"))

        container = document.xpath("//div[@class='container']")
        if not container:
            raise ProviderError(f"{self.site_name}: 页面结构异常")
        container = container[0]

        info_nodes = container.xpath(".//div[@class='col-md-3 info']")
        if not info_nodes:
            raise ProviderError(f"{self.site_name}: 未找到信息区")
        info = info_nodes[0]

        metadata = self.create_metadata(code)
        title = self.clean_text("".join(container.xpath("./h3/text()")))
        remote_code = self.clean_text("".join(info.xpath(".//p/span[text()='識別碼:']/following-sibling::text()[1]")))
        big_cover_url = self.clean_url("".join(container.xpath(".//a[@class='bigImage']/@href")))
        inline_cover_url = self.clean_url("".join(container.xpath(".//a[@class='bigImage']/img/@src")))

        metadata.code = remote_code or code
        metadata.detail_url = detail_url.replace("https://www.seedmm.help", "https://www.javbus.com")
        metadata.title = title.replace(metadata.code, "").strip() if title else None
        metadata.cover_url = big_cover_url or inline_cover_url
        metadata.release_date = self.clean_text("".join(info.xpath(".//p/span[text()='發行日期:']/following-sibling::text()[1]"))) or None
        metadata.duration_minutes = self.extract_duration(
            self.clean_text("".join(info.xpath(".//p/span[text()='長度:']/following-sibling::text()[1]")))
        )
        metadata.director = self.clean_text("".join(info.xpath(".//p/span[text()='導演:']/following-sibling::*[1]/text()"))) or None
        metadata.maker = self.clean_text("".join(info.xpath(".//p/span[text()='製作商:']/following-sibling::*[1]/text()"))) or None
        metadata.publisher = self.clean_text("".join(info.xpath(".//p/span[text()='發行商:']/following-sibling::*[1]/text()"))) or None
        metadata.series = self.clean_text("".join(info.xpath(".//p/span[text()='系列:']/following-sibling::*[1]/text()"))) or None
        metadata.genres = self.unique(info.xpath(".//span[@class='genre']/label/a/text()"))
        metadata.actresses = self.unique(document.xpath("//a[@class='avatar-box']/div/img/@title"))
        metadata.preview_images = self.unique(container.xpath(".//div[@id='sample-waterfall']/a/@href"))
        return metadata
