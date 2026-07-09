from app import cache


def test_report_and_availability_cache_invalidation():
    cache._report_cache.clear()
    cache._availability_cache.clear()

    cache.set_report(7, "2024-01-01", "2024-01-31", {"rooms": []})
    cache.set_report(8, "2024-01-01", "2024-01-31", {"rooms": []})
    cache.set_availability(10, "2024-01-01", {"busy": []})
    cache.set_availability(10, "2024-01-02", {"busy": []})

    assert cache.get_report(7, "2024-01-01", "2024-01-31") == {"rooms": []}
    assert cache.get_availability(10, "2024-01-01") == {"busy": []}

    cache.invalidate_report(7)
    assert cache.get_report(7, "2024-01-01", "2024-01-31") is None
    assert cache.get_report(8, "2024-01-01", "2024-01-31") == {"rooms": []}

    cache.invalidate_availability(10, "2024-01-01")
    assert cache.get_availability(10, "2024-01-01") is None
    assert cache.get_availability(10, "2024-01-02") == {"busy": []}
