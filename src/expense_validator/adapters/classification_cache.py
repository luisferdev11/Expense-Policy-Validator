"""The committed classification cache: outputs/classifications.jsonl (research R5, FR-008).

One row per cache key, written sorted by key, so the file is byte-stable. The key covers the
cleaned description, merchant, MCC, model, provider endpoint and prompt version: a change in
any of them is a miss, never a wrong hit.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from expense_validator.domain.models import CacheEntry, ClassifierRequest


def cache_key(request: ClassifierRequest, model_id: str, endpoint: str, prompt_version: str) -> str:
    canonical = json.dumps(
        {
            "description_clean": request.description_clean,
            "merchant_name": request.merchant_name,
            "mcc": request.mcc,
            "model_id": model_id,
            "provider_endpoint": endpoint,
            "prompt_version": prompt_version,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ClassificationCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._rows: dict[str, CacheEntry] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    entry = CacheEntry.model_validate_json(line)
                    self._rows[entry.cache_key] = entry
        self._dirty = False

    def get(self, key: str) -> CacheEntry | None:
        return self._rows.get(key)

    def put(self, entry: CacheEntry) -> None:
        self._rows[entry.cache_key] = entry
        self._dirty = True

    def total_cost_usd(self) -> float:
        return sum(e.cost_usd or 0.0 for e in self._rows.values())

    @property
    def dirty(self) -> bool:
        """True when entries were added since the file was read or last saved."""
        return self._dirty

    def __len__(self) -> int:
        return len(self._rows)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            json.dumps(self._rows[k].model_dump(mode="json"), ensure_ascii=False)
            for k in sorted(self._rows)
        ]
        # Write beside the file and rename over it: a crash leaves the old file, never half of
        # a new one.
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
        os.replace(temporary, self.path)
        self._dirty = False
