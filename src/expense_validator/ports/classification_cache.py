"""The classification answer cache port (spec 006, research R3).

A cache holds one billed model answer per key. `put` is first-writer-wins: it stores the row and
returns True only when the key was new, so two workers that race on one line keep one answer and
the loser can read it back with `get`.
"""

from __future__ import annotations

from typing import Protocol

from expense_validator.domain.models import CacheEntry


class ClassificationCachePort(Protocol):
    def get(self, key: str) -> CacheEntry | None: ...

    def put(self, entry: CacheEntry) -> bool:
        """Store `entry` unless its key exists. True when this call stored the row."""
        ...

    def __len__(self) -> int: ...
