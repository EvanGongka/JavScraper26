from __future__ import annotations

import re
from urllib.parse import urljoin

from javscraper.providers.base import Provider, ProviderError
from javscraper.utils.browser import load_browser_cookies


class JavDBProvider(Provider):
    site_name = "JavDB"
    base_url = "https://javdb.com"
    headers = {
        "accept-language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,en;q=0.7,ja;q=0.6",
    }

    def fetch(self, code: str):
        cookies = load_browser_cookies(["javdb.com"])
        if not cookies:
            raise ProviderError(f"{self.site_name}: 未读取到 javdb.com Cookie，请先在浏览器登录")

        search_response = self.client.request(
            "GET",
            f"{self.base_url}/search?q={code}",
            headers=self.headers,
            cookies=cookies,
            impersonate="chrome136",
            raise_for_status=False,
        )
        if search_response.status_code in (403, 503):
            raise ProviderError(f"{self.site_name}: Cloudflare 或权限校验未通过")
        if "/login" in str(search_response.url):
            raise ProviderError(f"{self.site_name}: Cookie 已失效，请重新登录浏览器")

        search_doc, _, _ = self.client.get_document(
            f"{self.base_url}/search?q={code}",
            headers=self.headers,
            cookies=cookies,
            impersonate="chrome136",
        )

        ids = [item.strip().lower() for item in search_doc.xpath("//div[@class='video-title']/strong/text()")]
        urls = search_doc.xpath("//a[@class='box']/@href")
        boxes = search_doc.xpath("//a[@class='box']")
        if code.lower() not in ids:
            raise ProviderError(f"{self.site_name}: 未找到 {code}")

        index = ids.index(code.lower())
        detail_url = urljoin(self.base_url, urls[index])
        detail_response = self.client.request(
            "GET",
            detail_url,
            headers=self.headers,
            cookies=cookies,
            impersonate="chrome136",
            raise_for_status=False,
        )

        if "/pay/" in str(detail_response.url):
            return self._from_search_box(code, detail_url, boxes[index])
        if detail_response.status_code in (403, 503):
            return self._from_search_box(code, detail_url, boxes[index])

        detail_doc, detail_url, _ = self.client.get_document(
            detail_url,
            headers=self.headers,
            cookies=cookies,
            impersonate="chrome136",
        )

        container_nodes = detail_doc.xpath("/html/body/section/div/div[@class='video-detail']")
        if not container_nodes:
            return self._from_search_box(code, detail_url, boxes[index])
        container = container_nodes[0]
        info_nodes = container.xpath(".//nav[@class='panel movie-panel-info']")
        if not info_nodes:
            return self._from_search_box(code, detail_url, boxes[index])
        info = info_nodes[0]

        metadata = self.create_metadata(code)
        title = self.clean_text("".join(container.xpath("./h2/strong[@class='current-title']/text()")))
        remote_code = self.clean_text("".join(info.xpath("./div/span[1]/text()")))

        metadata.code = remote_code or code
        metadata.detail_url = detail_url
        metadata.title = title.replace(metadata.code, "").strip() if title else None
        metadata.original_title = self.clean_text("".join(container.xpath("./h2/span[@class='origin-title']/text()"))) or None
        metadata.cover_url = self.clean_url("".join(container.xpath(".//img[@class='video-cover']/@src")))
        metadata.release_date = self.clean_text("".join(info.xpath("./div/strong[text()='日期:']/following-sibling::text()[1]"))) or None
        metadata.duration_minutes = self.extract_duration(
            self.clean_text("".join(info.xpath("./div/strong[text()='時長:']/following-sibling::text()[1]")))
        )
        metadata.director = self.clean_text("".join(info.xpath("./div/strong[text()='導演:']/following-sibling::*[1]//text()"))) or None
        metadata.maker = self.clean_text("".join(info.xpath("./div/strong[text()='片商:']/following-sibling::*[1]//text()"))) or None
        metadata.publisher = self.clean_text("".join(info.xpath("./div/strong[text()='發行:']/following-sibling::*[1]//text()"))) or None
        metadata.series = self.clean_text("".join(info.xpath("./div/strong[text()='系列:']/following-sibling::*[1]//text()"))) or None
        metadata.score = self._extract_score(self.clean_text("".join(container.xpath(".//span[@class='score-stars']/following-sibling::text()[1]"))))
        metadata.genres = self.unique(info.xpath(".//strong[text()='類別:']/../span/a/text()"))
        metadata.actresses = self._extract_female_actors(info)
        metadata.preview_images = self.unique(container.xpath(".//a[@class='tile-item'][@data-fancybox='gallery']/@href"))
        trailer = self.clean_text("".join(container.xpath(".//video[@id='preview-video']/source/@src")))
        if trailer.startswith("//"):
            trailer = f"https:{trailer}"
        metadata.trailer_url = self.clean_url(trailer)
        return metadata

    def _extract_score(self, text: str) -> str | None:
        match = re.search(r"([\d.]+)分", text)
        if not match:
            return None
        return f"{float(match.group(1)) * 2:.2f}"

    def _extract_female_actors(self, info_node) -> list[str]:
        actor_spans = info_node.xpath(".//strong[text()='演員:']/../span")
        if not actor_spans:
            return []
        actor_node = actor_spans[0]
        names = actor_node.xpath("./a/text()")
        genders = actor_node.xpath("./strong/text()")
        result: list[str] = []
        for index, name in enumerate(names):
            gender = genders[index] if index < len(genders) else ""
            if gender == "♀":
                result.append(name.strip())
        return self.unique(result)

    def _from_search_box(self, code: str, detail_url: str, box_node):
        metadata = self.create_metadata(code)
        title = self.clean_text(box_node.get("title"))
        score_text = self.clean_text("".join(box_node.xpath(".//div[@class='score']/span/span/following-sibling::text()[1]")))

        metadata.detail_url = detail_url
        metadata.title = title.replace(code, "").strip() if title.upper().startswith(code.upper()) else title or None
        metadata.cover_url = self.clean_url("".join(box_node.xpath(".//div/img/@src")))
        metadata.release_date = self.clean_text("".join(box_node.xpath(".//div[@class='meta']/text()[1]"))) or None
        metadata.score = self._extract_score(score_text)
        return metadata
