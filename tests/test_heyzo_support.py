from __future__ import annotations

import unittest

from javscraper import gui, webapp
from javscraper.providers import PROVIDER_CLASSES
from javscraper.providers.heydouga import HeyDougaProvider
from javscraper.providers.heyzo import HEYZOProvider
from javscraper.scanner import extract_code_from_text


class HeyzoSupportTests(unittest.TestCase):
    def test_default_sites_insert_heyzo_family_before_onepondo(self) -> None:
        expected = [
            "JavBus",
            "JavBooks",
            "AVBASE",
            "JAV321",
            "FC2",
            "Caribbeancom",
            "CaribbeancomPR",
            "HEYZO",
            "HeyDouga",
            "1Pondo",
            "10musume",
            "PACOPACOMAMA",
            "MURAMURA",
            "AVMOO",
            "FreeJavBT",
            "JavDB",
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


if __name__ == "__main__":
    unittest.main()
