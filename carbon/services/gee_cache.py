"""Cache de desenvolvimento para consultas ao Earth Engine.

Evita repetir a mesma redução server-side dentro de uma sessão. Regras:

* chave = dataset + hash da geometria + intervalo de datas + parâmetros;
* nada é cacheado indefinidamente: TTL explícito, default em ``GEEConfig``;
* a data de AQUISIÇÃO original acompanha o valor e vai para a proveniência —
  um resultado servido do cache não se disfarça de consulta nova.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Optional

from pydantic import BaseModel


class CacheEntry(BaseModel):
    key: str
    dataset_id: str
    value: Any
    acquired_at: str
    acquired_monotonic: float
    hits: int = 0


def cache_key(dataset_id: str, geometry_hash: str, start: str, end: str, **params) -> str:
    payload = {
        "dataset": dataset_id,
        "geometry": geometry_hash,
        "start": start,
        "end": end,
        "params": {key: params[key] for key in sorted(params)},
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class GEEQueryCache:
    """Cache em memória com TTL. ``ttl_seconds=0`` desliga o cache."""

    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._entries: dict[str, CacheEntry] = {}

    @property
    def enabled(self) -> bool:
        return self.ttl_seconds > 0

    def get(self, key: str) -> Optional[CacheEntry]:
        if not self.enabled:
            return None
        entry = self._entries.get(key)
        if entry is None:
            return None
        if time.monotonic() - entry.acquired_monotonic > self.ttl_seconds:
            del self._entries[key]
            return None
        entry.hits += 1
        return entry

    def set(self, key: str, dataset_id: str, value: Any, acquired_at: str) -> Optional[CacheEntry]:
        if not self.enabled:
            return None
        entry = CacheEntry(
            key=key,
            dataset_id=dataset_id,
            value=value,
            acquired_at=acquired_at,
            acquired_monotonic=time.monotonic(),
        )
        self._entries[key] = entry
        return entry

    def clear(self) -> None:
        self._entries.clear()

    def stats(self) -> dict:
        return {
            "enabled": self.enabled,
            "ttl_seconds": self.ttl_seconds,
            "entries": len(self._entries),
            "total_hits": sum(entry.hits for entry in self._entries.values()),
        }
