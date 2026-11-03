"""Eenvoudige JSON-cache zodat Yahoo-lookups niet bij elke run opnieuw gebeuren."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_FLUSH_EVERY = 50


class JsonCache:
    """Key-value cache opgeslagen als één JSON-bestand.

    `None` is een geldige waarde (bv. "bedrijf niet op de beurs"). Gebruik `has()`
    om onderscheid te maken tussen "niet gecachet" en "gecachet als None".
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._data: dict[str, Any] = {}
        self._pending = 0
        if path.exists():
            try:
                self._data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("Cache %s is onleesbaar (%s); er wordt opnieuw opgebouwd", path, exc)

    def has(self, key: str) -> bool:
        return key in self._data

    def get(self, key: str) -> Any:
        return self._data.get(key)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._pending += 1
        if self._pending >= _FLUSH_EVERY:
            self.flush()

    def flush(self) -> None:
        if self._pending == 0 and self._path.exists():
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._path)
        self._pending = 0

    def __len__(self) -> int:
        return len(self._data)
