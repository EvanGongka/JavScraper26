from __future__ import annotations

import re

from javscraper.models import MovieMetadata
from javscraper.network import HttpClient


class ProviderError(Exception):
    pass


class Provider:
    site_name = "Provider"

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()

    @staticmethod
    def clean_text(value: str | None) -> str:
        return " ".join((value or "").replace("\xa0", " ").split())

    @staticmethod
    def clean_url(value: str | None) -> str | None:
        text = (value or "").strip()
        if not text:
            return None
        if len(text) % 2 == 0:
            half = len(text) // 2
            if text[:half] == text[half:] and text.startswith(("http://", "https://")):
                return text[:half]
        return text

    @staticmethod
    def unique(values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            text = value.strip()
            if text and text not in result:
                result.append(text)
        return result

    @staticmethod
    def extract_duration(text: str | None) -> str | None:
        if not text:
            return None
        match = re.search(r"(\d+)", text)
        return match.group(1) if match else None

    def create_metadata(self, code: str) -> MovieMetadata:
        return MovieMetadata(code=code)

    def fetch(self, code: str) -> MovieMetadata:
        raise NotImplementedError
