"""Live per-room booking statistics.

Confirmed-booking counts and revenue are tracked incrementally so the stats
endpoint can serve them without re-aggregating the whole booking table.
"""
import threading

_stats: dict[int, dict] = {}
_lock = threading.Lock()


def record_create(room_id: int, price_cents: int) -> None:
    with _lock:
        current = _stats.setdefault(room_id, {"count": 0, "revenue": 0})
        current["count"] += 1
        current["revenue"] += price_cents


def record_cancel(room_id: int, price_cents: int) -> None:
    with _lock:
        current = _stats.setdefault(room_id, {"count": 0, "revenue": 0})
        current["count"] = max(0, current["count"] - 1)
        current["revenue"] = max(0, current["revenue"] - price_cents)


def get(room_id: int) -> dict:
    with _lock:
        current = _stats.get(room_id, {"count": 0, "revenue": 0})
        return {"count": current["count"], "revenue": current["revenue"]}
