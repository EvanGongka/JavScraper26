from __future__ import annotations

import unittest

from javscraper.runtime_cache import TtlLruCache


class RuntimeCacheTests(unittest.TestCase):
    def test_cache_has_lru_eviction_and_ttl_expiration(self) -> None:
        now = [0.0]
        cache = TtlLruCache[str, str](2, 10, clock=lambda: now[0])
        cache.set("a", "A")
        cache.set("b", "B")
        self.assertEqual(cache.get("a"), "A")
        cache.set("c", "C")
        self.assertIsNone(cache.get("b"))
        self.assertEqual(cache.get("a"), "A")
        now[0] = 11
        self.assertIsNone(cache.get("a"))
        stats = cache.stats()
        self.assertEqual(stats["entries"], 0)
        self.assertEqual(stats["evictions"], 1)
        self.assertGreaterEqual(stats["expired"], 1)
        self.assertLessEqual(len(cache), 2)


if __name__ == "__main__":
    unittest.main()
