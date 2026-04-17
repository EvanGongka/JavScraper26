from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from javscraper.images import should_crop_poster_from_fanart


@dataclass(frozen=True)
class ProviderCatalogItem:
    name: str
    group: str
    sort_order: int
    connectivity_target: str


PROVIDER_CATALOG: tuple[ProviderCatalogItem, ...] = (
    ProviderCatalogItem("JavBus", "regular", 10, "https://www.javbus.com"),
    ProviderCatalogItem("JAV321", "regular", 20, "https://www.jav321.com"),
    ProviderCatalogItem("JavBooks", "regular", 30, "https://javbooks.com"),
    ProviderCatalogItem("AVBASE", "regular", 40, "https://www.avbase.net"),
    ProviderCatalogItem("FreeJavBT", "regular", 50, "https://freejavbt.com"),
    ProviderCatalogItem("AVMOO", "regular", 60, "https://avmoo.website"),
    ProviderCatalogItem("JavDB", "regular", 70, "https://javdb.com"),
    ProviderCatalogItem("FC2", "special", 110, "https://adult.contents.fc2.com"),
    ProviderCatalogItem("Caribbeancom", "special", 120, "https://www.caribbeancom.com"),
    ProviderCatalogItem("CaribbeancomPR", "special", 130, "https://www.caribbeancompr.com"),
    ProviderCatalogItem("HEYZO", "special", 140, "https://www.heyzo.com"),
    ProviderCatalogItem("HeyDouga", "special", 150, "https://www.heydouga.com"),
    ProviderCatalogItem("1Pondo", "special", 160, "https://www.1pondo.tv"),
    ProviderCatalogItem("10musume", "special", 170, "https://www.10musume.com"),
    ProviderCatalogItem("PACOPACOMAMA", "special", 180, "https://www.pacopacomama.com"),
    ProviderCatalogItem("MURAMURA", "special", 190, "https://www.muramura.tv"),
)

PROVIDER_GROUP_LABELS = {
    "regular": "普通番号站点",
    "special": "特殊番号站点",
}

DEFAULT_SITES = [item.name for item in PROVIDER_CATALOG]
REGULAR_SITES = [item.name for item in PROVIDER_CATALOG if item.group == "regular"]
SPECIAL_SITES = [item.name for item in PROVIDER_CATALOG if item.group == "special"]

SITE_CONNECTIVITY_TARGETS = {
    item.name: item.connectivity_target
    for item in PROVIDER_CATALOG
}

PROVIDER_GROUP_BY_NAME = {
    item.name: item.group
    for item in PROVIDER_CATALOG
}


def normalize_provider_names(provider_names: Iterable[str] | None = None) -> list[str]:
    ordered = provider_names or DEFAULT_SITES
    result: list[str] = []
    for name in ordered:
        text = str(name).strip()
        if text and text not in result:
            result.append(text)
    return result


def provider_group_for_code(code: str | None) -> str:
    return "regular" if should_crop_poster_from_fanart(code) else "special"


def provider_names_for_group(
    group: str,
    provider_names: Iterable[str] | None = None,
    *,
    javdb_available: bool = True,
) -> list[str]:
    names = [
        name
        for name in normalize_provider_names(provider_names)
        if PROVIDER_GROUP_BY_NAME.get(name) in {None, group}
    ]
    if javdb_available:
        return names
    return [name for name in names if name != "JavDB"]


def provider_names_for_code(
    code: str | None,
    provider_names: Iterable[str] | None = None,
    *,
    javdb_available: bool = True,
) -> list[str]:
    return provider_names_for_group(
        provider_group_for_code(code),
        provider_names,
        javdb_available=javdb_available,
    )


def connectivity_provider_names_for_codes(
    codes: Iterable[str],
    provider_names: Iterable[str] | None = None,
    *,
    javdb_available: bool = True,
) -> list[str]:
    needs_regular = False
    needs_special = False
    for code in codes:
        group = provider_group_for_code(code)
        if group == "regular":
            needs_regular = True
        else:
            needs_special = True

    if not needs_regular and not needs_special:
        needs_regular = True
        needs_special = True

    results: list[str] = []
    if needs_regular:
        results.extend(
            provider_names_for_group(
                "regular",
                provider_names,
                javdb_available=javdb_available,
            )
        )
    if needs_special:
        results.extend(
            provider_names_for_group(
                "special",
                provider_names,
                javdb_available=javdb_available,
            )
        )
    return results
