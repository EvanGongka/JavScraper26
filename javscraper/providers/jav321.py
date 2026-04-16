from __future__ import annotations

import re
from urllib.parse import urljoin

from javscraper.providers.base import Provider, ProviderError


class JAV321Provider(Provider):
    site_name = "JAV321"
    base_url = "https://www.jav321.com"

    def _is_detail(self, document) -> bool:
        return bool(document.xpath("//div[contains(@class,'panel-heading')]/h3")) or bool(
            document.xpath("/html/body/div[2]/div[1]/div[1]/div[1]/h3")
        )

    def fetch(self, code: str):
        detail_doc, detail_url, response = self.client.post_document(
            f"{self.base_url}/search",
            data={"sn": code},
            headers={
                "origin": self.base_url,
                "referer": f"{self.base_url}/",
                "content-type": "application/x-www-form-urlencoded",
            },
            impersonate="chrome136",
            raise_for_status=False,
        )

        if not self._is_detail(detail_doc):
            redirect_target = response.headers.get("Location")
            if redirect_target:
                redirected_url = urljoin(str(response.url), redirect_target)
                detail_doc, detail_url, _ = self.client.get_document(
                    redirected_url,
                    headers={"referer": f"{self.base_url}/search"},
                    impersonate="chrome136",
                )

        if not self._is_detail(detail_doc):
            raise ProviderError(f"{self.site_name}: 未找到 {code}")

        metadata = self.create_metadata(code)

        raw_title = self.clean_text(
            detail_doc.xpath("string(/html/body/div[2]/div[1]/div[1]/div[1]/h3)")
        ) or self.clean_text(detail_doc.xpath("string(//div[contains(@class,'panel-heading')]/h3)"))
        summary = self.clean_text(
            detail_doc.xpath("string(/html/body/div[2]/div[1]/div[1]/div[2]/div[3]/div)")
        ) or self.clean_text(
            detail_doc.xpath("string(//div[@class='panel-body']/div[@class='row']/div[@class='col-md-12'])")
        )
        thumb_url = self.clean_url(
            detail_doc.xpath("string(//div[@class='panel-body']//div[contains(@class,'col-md-3')]/img/@src)")
        )

        images = [
            self.clean_url(url)
            for url in detail_doc.xpath("//div[@class='col-xs-12 col-md-12']/p/a/img[contains(@class,'img-responsive')]/@src")
        ]
        images = [url for url in images if url]

        actresses = self.unique(
            [
                self.clean_text(item)
                for item in detail_doc.xpath("//div[@class='thumbnail']/a[contains(@href,'/star/')]/text()")
            ]
        )
        if not actresses:
            actresses = self.unique(
                [
                    self.clean_text(item)
                    for item in detail_doc.xpath("//b[contains(text(),'出演者')]/following-sibling::a[starts-with(@href,'/star')]/text()")
                ]
            )
        if not actresses:
            actress_text = self.clean_text(
                "".join(detail_doc.xpath("//b[contains(text(),'出演者')]/following-sibling::text()[1]"))
            )
            actresses = self.unique(
                [item.lstrip(":").strip() for item in re.split(r"[、/,;]", actress_text) if item.strip()]
            )

        raw_code = self.clean_text(
            "".join(detail_doc.xpath("//b[contains(text(),'品番')]/following-sibling::text()[1]"))
        )
        if not raw_code:
            code_match = re.search(r"([A-Z0-9]+)\s*-\s*(\d+[A-Z]?)", raw_title.upper())
            raw_code = f"{code_match.group(1)}-{code_match.group(2)}" if code_match else code.upper()

        title = raw_title
        if title:
            title = re.sub(re.escape(metadata.code), "", title, flags=re.IGNORECASE).strip()
            for actress in actresses:
                title = re.sub(rf"\s*{re.escape(actress)}\s*$", "", title).strip()

        metadata.code = raw_code or code.upper()
        metadata.detail_url = detail_url
        metadata.title = title or None
        metadata.description = summary or None
        metadata.cover_url = images[0] if images else thumb_url
        metadata.preview_images = images[1:] if len(images) > 1 else []
        metadata.actresses = actresses
        metadata.release_date = self.clean_text(
            "".join(detail_doc.xpath("//b[contains(text(),'配信開始日')]/following-sibling::text()[1]"))
        ).lstrip(":").strip() or None
        metadata.duration_minutes = self.extract_duration(
            self.clean_text(
                "".join(detail_doc.xpath("//b[contains(text(),'収録時間')]/following-sibling::text()[1]"))
            )
        )
        metadata.maker = self.clean_text(
            "".join(detail_doc.xpath("//b[contains(text(),'メーカー')]/following-sibling::a[starts-with(@href,'/company')][1]/text()"))
        ) or None
        metadata.series = self.clean_text(
            "".join(detail_doc.xpath("//b[contains(text(),'シリーズ')]/following-sibling::a[starts-with(@href,'/series')][1]/text()"))
        ) or None
        metadata.genres = self.unique(
            [
                self.clean_text(item)
                for item in detail_doc.xpath("//b[contains(text(),'ジャンル')]/following-sibling::a[starts-with(@href,'/genre')]/text()")
            ]
        )

        trailer = self.clean_url("".join(detail_doc.xpath("//div[contains(@class,'panel-body')]//video/source/@src")))
        if trailer:
            trailer = trailer.replace("awscc3001.r18.com", "cc3001.dmm.co.jp").replace(
                "cc3001.r18.com", "cc3001.dmm.co.jp"
            )
        metadata.trailer_url = trailer

        score_text = self.clean_text(
            "".join(detail_doc.xpath("//b[contains(text(),'平均評価')]/following-sibling::text()[1]"))
        )
        if not score_text:
            score_src = self.clean_text(
                "".join(detail_doc.xpath("//b[contains(text(),'平均評価')]/following-sibling::img[1]/@data-original"))
            )
            score_match = re.search(r"(\d+)\.gif", score_src)
            if score_match:
                score_text = str(float(score_match.group(1)) / 10)
        metadata.score = score_text or None
        return metadata
