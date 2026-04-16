from __future__ import annotations

from javscraper.providers.onepondo_base import OnePondoFamilyProvider


class PacopacomamaProvider(OnePondoFamilyProvider):
    site_name = "PACOPACOMAMA"
    base_url = "https://www.pacopacomama.com"
    movie_url_template = f"{base_url}/movies/%s/"
    sample_video_url_template = "https://fms.pacopacomama.com/sample/%s/mb.m3u8"
    maker_name = "パコパコママ"
    gallery_path = "/dyn/dla/images/%s"
    legacy_gallery_path = "/assets/sample/%s/l/%s"
    id_pattern = r"\d{6}_\d{3}"
