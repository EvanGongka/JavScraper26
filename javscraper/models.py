from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class ScanEntry:
    code: str
    files: list[Path]
    status: str = "待处理"

    @property
    def primary_file(self) -> Path:
        return self.files[0]

    @property
    def file_count(self) -> int:
        return len(self.files)


@dataclass
class MovieMetadata:
    code: str
    title: str | None = None
    original_title: str | None = None
    detail_url: str | None = None
    cover_url: str | None = None
    thumb_url: str | None = None
    release_date: str | None = None
    duration_minutes: str | None = None
    director: str | None = None
    maker: str | None = None
    publisher: str | None = None
    series: str | None = None
    score: str | None = None
    description: str | None = None
    trailer_url: str | None = None
    actresses: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    preview_images: list[str] = field(default_factory=list)
    filled_by: dict[str, str] = field(default_factory=dict)
    providers: list[str] = field(default_factory=list)

    def merge_missing(self, other: "MovieMetadata", provider: str) -> None:
        scalar_fields = (
            "title",
            "original_title",
            "detail_url",
            "cover_url",
            "thumb_url",
            "release_date",
            "duration_minutes",
            "director",
            "maker",
            "publisher",
            "series",
            "score",
            "description",
            "trailer_url",
        )
        for field_name in scalar_fields:
            current = getattr(self, field_name)
            incoming = getattr(other, field_name)
            if not current and incoming:
                setattr(self, field_name, incoming)
                self.filled_by[field_name] = provider

        if other.actresses:
            for item in other.actresses:
                if item not in self.actresses:
                    self.actresses.append(item)
            self.filled_by.setdefault("actresses", provider)

        if other.genres:
            for item in other.genres:
                if item not in self.genres:
                    self.genres.append(item)
            self.filled_by.setdefault("genres", provider)

        if other.preview_images:
            for item in other.preview_images:
                if item not in self.preview_images:
                    self.preview_images.append(item)
            self.filled_by.setdefault("preview_images", provider)

        if provider not in self.providers:
            self.providers.append(provider)

    @property
    def is_usable(self) -> bool:
        return bool(self.title and (self.cover_url or self.thumb_url or self.preview_images))

    def to_dict(self) -> dict:
        return asdict(self)
