from __future__ import annotations

import unittest

from javscraper import gui, webapp
from javscraper.provider_catalog import REGULAR_SITES, SPECIAL_SITES, connectivity_provider_names_for_codes, provider_names_for_code
from javscraper.providers import PROVIDER_CLASSES
from javscraper.providers.heydouga import HeyDougaProvider
from javscraper.providers.heyzo import HEYZOProvider
from javscraper.scanner import extract_code_from_text


class HeyzoSupportTests(unittest.TestCase):
    def test_default_sites_insert_heyzo_family_before_onepondo(self) -> None:
        expected = [
            "JavBus",
            "JAV321",
            "JavBooks",
            "AVBASE",
            "FreeJavBT",
            "AVMOO",
            "JavDB",
            "FC2",
            "Caribbeancom",
            "CaribbeancomPR",
            "HEYZO",
            "HeyDouga",
            "1Pondo",
            "10musume",
            "PACOPACOMAMA",
            "MURAMURA",
        ]
        self.assertEqual(gui.DEFAULT_SITES, expected)
        self.assertEqual(webapp.DEFAULT_SITES, expected)
        self.assertEqual(list(webapp.SITE_CONNECTIVITY_TARGETS.keys()), expected)

    def test_provider_classes_register_heyzo_family(self) -> None:
        self.assertIs(PROVIDER_CLASSES["HEYZO"], HEYZOProvider)
        self.assertIs(PROVIDER_CLASSES["HeyDouga"], HeyDougaProvider)

    def test_heyzo_normalize_id(self) -> None:
        self.assertEqual(HEYZOProvider._normalize_id("HEYZO-841"), "0841")
        self.assertEqual(HEYZOProvider._normalize_id("0841"), "0841")

    def test_heydouga_normalize_id(self) -> None:
        self.assertEqual(HeyDougaProvider._normalize_id("HEYDOUGA-4037-479"), "4037-479")
        self.assertEqual(HeyDougaProvider._normalize_id("4030_1938"), "4030-1938")

    def test_scanner_extracts_heydouga_code(self) -> None:
        self.assertEqual(extract_code_from_text("HEYDOUGA-4037-479.mp4"), "HEYDOUGA-4037-479")
        self.assertEqual(extract_code_from_text("heydouga_4030_1938"), "HEYDOUGA-4030-1938")

    def test_regular_code_routes_only_regular_sites_and_can_skip_javdb(self) -> None:
        self.assertEqual(
            provider_names_for_code("ABP-123", javdb_available=False),
            [name for name in REGULAR_SITES if name != "JavDB"],
        )

    def test_special_codes_route_only_special_sites(self) -> None:
        self.assertEqual(provider_names_for_code("HEYZO-0841"), SPECIAL_SITES)
        self.assertEqual(provider_names_for_code("010115-771"), SPECIAL_SITES)

    def test_connectivity_scope_follows_scanned_code_groups(self) -> None:
        self.assertEqual(
            connectivity_provider_names_for_codes(["ABP-123"], javdb_available=False),
            [name for name in REGULAR_SITES if name != "JavDB"],
        )
        self.assertEqual(
            connectivity_provider_names_for_codes(["HEYZO-0841"], javdb_available=False),
            SPECIAL_SITES,
        )
        self.assertEqual(
            connectivity_provider_names_for_codes(["ABP-123", "HEYZO-0841"], javdb_available=False),
            [name for name in REGULAR_SITES if name != "JavDB"] + SPECIAL_SITES,
        )


if __name__ == "__main__":
    unittest.main()
