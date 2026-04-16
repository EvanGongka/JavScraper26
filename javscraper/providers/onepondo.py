from __future__ import annotations

from javscraper.providers.onepondo_base import OnePondoFamilyProvider


class OnePondoProvider(OnePondoFamilyProvider):
    site_name = "1Pondo"
    base_url = "https://www.1pondo.tv"
    movie_url_template = f"{base_url}/movies/%s/"
    sample_video_url_template = "https://fms.1pondo.tv/sample/%s/mb.m3u8"
    maker_name = "一本道"
    gallery_path = "/dyn/dla/images/%s"
    legacy_gallery_path = "/assets/sample/%s/popu/%s"
    id_pattern = r"\d{6}_\d{3}"
