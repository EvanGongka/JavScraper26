from __future__ import annotations

import unittest

from javscraper import gui, webapp
from javscraper.providers import PROVIDER_CLASSES
from javscraper.providers.caribbeancom import CaribbeancomProvider
from javscraper.providers.caribbeancompr import CaribbeancomPRProvider


class CaribbeanSupportTests(unittest.TestCase):
    def test_default_sites_insert_caribbean_before_onepondo(self) -> None:
        expected = [
            "JavBus",
            "JavBooks",
            "AVBASE",
            "JAV321",
            "FC2",
            "Caribbeancom",
            "CaribbeancomPR",
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

    def test_provider_classes_register_caribbean_family(self) -> None:
        self.assertIs(PROVIDER_CLASSES["Caribbeancom"], CaribbeancomProvider)
        self.assertIs(PROVIDER_CLASSES["CaribbeancomPR"], CaribbeancomPRProvider)

    def test_caribbeancom_accepts_dash_code(self) -> None:
        provider = CaribbeancomProvider()
        self.assertEqual(provider._normalize_id("050422-001"), "050422-001")
        with self.assertRaisesRegex(Exception, "不支持的编号"):
            provider._normalize_id("050422_001")

    def test_caribbeancompr_converts_dash_to_underscore_for_request(self) -> None:
        provider = CaribbeancomPRProvider()
        self.assertEqual(provider._normalize_id("052121-002"), "052121_002")
        self.assertEqual(provider._normalize_id("052121_002"), "052121_002")
        self.assertEqual(provider._canonical_code("052121_002"), "052121-002")


if __name__ == "__main__":
    unittest.main()
