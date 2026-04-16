from __future__ import annotations

import re

from javscraper.providers.base import ProviderError
from javscraper.providers.caribbean_base import CaribbeanFamilyProvider


class CaribbeancomProvider(CaribbeanFamilyProvider):
    site_name = "Caribbeancom"
    base_url = "https://www.caribbeancom.com"
    movie_url_template = f"{base_url}/moviepages/%s/index.html"
    maker_name = "カリビアンコム"

    def _normalize_id(self, code: str) -> str:
        candidate = code.upper().strip()
        if re.fullmatch(r"\d{6}-\d{3}", candidate):
            return candidate
        raise ProviderError(f"{self.site_name}: 不支持的编号 {code}")
