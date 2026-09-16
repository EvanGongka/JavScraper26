from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import time
from threading import Lock
from typing import Callable, Generic, TypeVar


T = TypeVar("T")
K = TypeVar("K")


@dataclass
class _CacheItem(Generic[T]):
    value: T
    created_at: float


class TtlLruCache(Generic[K, T]):
    """Small thread-safe LRU cache with lazy TTL expiration."""

    def __init__(
        self,
        max_entries: int,
        ttl_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_entries = max(1, int(max_entries))
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        self.clock = clock
        self._items: OrderedDict[K, _CacheItem[T]] = OrderedDict()
        self._lock = Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._expired = 0

    def get(self, key: K, default: T | None = None) -> T | None:
        with self._lock:
            item = self._items.get(key)
            if item is None:
                self._misses += 1
                return default
            if self.ttl_seconds and self.clock() - item.created_at >= self.ttl_seconds:
                del self._items[key]
                self._expired += 1
                self._misses += 1
                return default
            self._items.move_to_end(key)
            self._hits += 1
            return item.value

    def set(self, key: K, value: T) -> int:
        evicted = 0
        with self._lock:
            self._items[key] = _CacheItem(value=value, created_at=self.clock())
            self._items.move_to_end(key)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)
                self._evictions += 1
                evicted += 1
        return evicted

    def __setitem__(self, key: K, value: T) -> None:
        self.set(key, value)

    def __len__(self) -> int:
        with self._lock:
            self._purge_expired_locked()
            return len(self._items)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def _purge_expired_locked(self) -> None:
        if not self.ttl_seconds:
            return
        now = self.clock()
        expired = [key for key, item in self._items.items() if now - item.created_at >= self.ttl_seconds]
        for key in expired:
            self._items.pop(key, None)
        self._expired += len(expired)

    def stats(self) -> dict[str, int]:
        with self._lock:
            self._purge_expired_locked()
            return {
                "entries": len(self._items),
                "maxEntries": self.max_entries,
                "ttlSeconds": int(self.ttl_seconds),
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "expired": self._expired,
            }


__all__ = ["TtlLruCache"]
