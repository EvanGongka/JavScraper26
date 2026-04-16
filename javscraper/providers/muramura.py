from __future__ import annotations

from javscraper.providers.onepondo_base import OnePondoFamilyProvider


class MuramuraProvider(OnePondoFamilyProvider):
    site_name = "MURAMURA"
    base_url = "https://www.muramura.tv"
    movie_url_template = f"{base_url}/movies/%s/"
    sample_video_url_template = "https://fms.muramura.tv/sample/%s/mb.m3u8"
    maker_name = "ムラムラってくる素人"
    gallery_path = ""
    legacy_gallery_path = ""
    id_pattern = r"\d{6}_\d{3}"
