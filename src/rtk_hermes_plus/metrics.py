from __future__ import annotations

import threading
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class Metrics:
    _counts: Counter = field(default_factory=Counter)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self, key: str, amount: float = 1) -> None:
        with self._lock:
            self._counts[key] += amount

    def reset(self) -> None:
        with self._lock:
            self._counts.clear()

    def snapshot(self) -> dict:
        with self._lock:
            data = dict(self._counts)

        raw = int(data.get("native_raw_chars", 0))
        compact = int(data.get("native_output_chars", 0))
        saved = max(0, raw - compact)
        data["native_saved_chars"] = saved
        data["native_estimated_tokens_saved"] = round(saved / 4)
        data["native_savings_pct"] = round(saved / raw * 100, 1) if raw else 0.0

        attempts = int(data.get("rewrite_attempted", 0))
        total_ms = float(data.get("rewrite_total_ms", 0.0))
        data["average_rewrite_ms"] = round(total_ms / attempts, 2) if attempts else 0.0
        return data
