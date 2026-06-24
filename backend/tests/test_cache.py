"""Disk cache governance (C2): hit/miss accounting + optional TTL expiry."""
import os
import time

from app.lib import cache


def test_hit_miss_counted(monkeypatch, tmp_path):
    monkeypatch.setattr(cache.settings, "cache_dir", tmp_path)
    monkeypatch.setattr(cache.settings, "cache_ttl_hours", 0)
    before = cache.stats()
    assert cache.get_cached("k", 1) is None          # miss (absent)
    cache.set_cached({"v": 1}, "k", 1)
    assert cache.get_cached("k", 1) == {"v": 1}       # hit
    after = cache.stats()
    assert after["misses"] >= before["misses"] + 1
    assert after["hits"] >= before["hits"] + 1


def test_ttl_expiry(monkeypatch, tmp_path):
    monkeypatch.setattr(cache.settings, "cache_dir", tmp_path)
    monkeypatch.setattr(cache.settings, "cache_ttl_hours", 1)
    cache.set_cached({"v": 2}, "stale")
    p = cache._path(("stale",))
    old = time.time() - 2 * 3600                       # 2h old, TTL is 1h
    os.utime(p, (old, old))
    assert cache.get_cached("stale") is None           # expired -> miss
