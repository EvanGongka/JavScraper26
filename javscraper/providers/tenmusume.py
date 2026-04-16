from __future__ import annotations

from javscraper.providers.onepondo_base import OnePondoFamilyProvider


class TenMusumeProvider(OnePondoFamilyProvider):
    site_name = "10musume"
    base_url = "https://www.10musume.com"
    movie_url_template = f"{base_url}/movies/%s/"
    sample_video_url_template = "https://fms.10musume.com/sample/%s/mb.m3u8"
    maker_name = "天然むすめ"
    gallery_path = "/dyn/dla/images/%s"
    legacy_gallery_path = "/assets/sample/%s/%s"
    id_pattern = r"\d{6}_\d{2}"
