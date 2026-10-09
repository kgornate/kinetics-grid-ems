from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class UGXFrequencyPlan:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.is_absolute():
            self.path = Path.cwd() / self.path
        with open(self.path, "r", encoding="utf-8") as f:
            self.data: dict[str, Any] = json.load(f)
        raw = self.data.get("keys_by_frequency") or {}
        self.keys_by_frequency: dict[int, list[str]] = {}
        for freq, keys in raw.items():
            if str(freq).lower() == "na":
                continue
            self.keys_by_frequency[int(freq)] = [str(k) for k in keys]

    def keys_for_frequency(self, frequency_sec: int) -> list[str]:
        return list(self.keys_by_frequency.get(int(frequency_sec), []))

    def counts_by_frequency(self) -> dict[str, int]:
        return {str(k): len(v) for k, v in sorted(self.keys_by_frequency.items())}
