from __future__ import annotations

import re

from javscraper.providers.base import ProviderError
from javscraper.providers.caribbean_base import CaribbeanFamilyProvider


class CaribbeancomPRProvider(CaribbeanFamilyProvider):
    site_name = "CaribbeancomPR"
    base_url = "https://www.caribbeancompr.com"
    movie_url_template = f"{base_url}/moviepages/%s/index.html"
    maker_name = "カリビアンコムプレミアム"

    def _normalize_id(self, code: str) -> str:
        candidate = code.upper().strip().replace("-", "_")
        if re.fullmatch(r"\d{6}_\d{3}", candidate):
            return candidate
        raise ProviderError(f"{self.site_name}: 不支持的编号 {code}")
