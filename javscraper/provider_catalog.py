from __future__ import annotations

from dataclasses import dataclass


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

SITE_CONNECTIVITY_TARGETS = {
    item.name: item.connectivity_target
    for item in PROVIDER_CATALOG
}

PROVIDER_GROUP_BY_NAME = {
    item.name: item.group
    for item in PROVIDER_CATALOG
}
