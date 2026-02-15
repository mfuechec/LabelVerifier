"""Tests for benchmark caching, throttling, and quick subset features."""

import asyncio
import json
import os
import re

import pytest

# Add backend to path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.extraction import ExtractionResult


# ---------------------------------------------------------------------------
# BenchmarkCache tests
# ---------------------------------------------------------------------------


class TestBenchmarkCache:
    def test_cache_miss_returns_none(self, tmp_path):
        from benchmark import BenchmarkCache

        cache = BenchmarkCache(cache_dir=str(tmp_path / "cache"))
        result = cache.get(b"image_bytes", "prompt text")
        assert result is None

    def test_cache_put_then_get(self, tmp_path):
        from benchmark import BenchmarkCache

        cache = BenchmarkCache(cache_dir=str(tmp_path / "cache"))
        original = ExtractionResult(
            fields={"brand_name": {"value": "Test Brand", "bounding_box": None}},
            panel_type="front",
        )
        cache.put(b"image_bytes", "prompt text", original)
        retrieved = cache.get(b"image_bytes", "prompt text")

        assert retrieved is not None
        assert retrieved.fields == original.fields
        assert retrieved.panel_type == original.panel_type

    def test_cache_key_changes_with_prompt(self, tmp_path):
        from benchmark import BenchmarkCache

        cache = BenchmarkCache(cache_dir=str(tmp_path / "cache"))
        result = ExtractionResult(fields={"f": {"value": "v"}}, panel_type="front")
        cache.put(b"image", "prompt_a", result)

        assert cache.get(b"image", "prompt_a") is not None
        assert cache.get(b"image", "prompt_b") is None

    def test_cache_key_changes_with_image(self, tmp_path):
        from benchmark import BenchmarkCache

        cache = BenchmarkCache(cache_dir=str(tmp_path / "cache"))
        result = ExtractionResult(fields={"f": {"value": "v"}}, panel_type="front")
        cache.put(b"image_a", "prompt", result)

        assert cache.get(b"image_a", "prompt") is not None
        assert cache.get(b"image_b", "prompt") is None

    def test_cache_disabled_is_noop(self, tmp_path):
        from benchmark import BenchmarkCache

        cache = BenchmarkCache(cache_dir=str(tmp_path / "cache"), enabled=False)
        result = ExtractionResult(fields={"f": {"value": "v"}}, panel_type="front")
        cache.put(b"image", "prompt", result)

        assert cache.get(b"image", "prompt") is None
        assert cache.stats() == "Cache: disabled"

    def test_cache_clear(self, tmp_path):
        from benchmark import BenchmarkCache

        cache = BenchmarkCache(cache_dir=str(tmp_path / "cache"))
        result = ExtractionResult(fields={"f": {"value": "v"}}, panel_type="front")
        cache.put(b"image", "prompt", result)
        assert cache.get(b"image", "prompt") is not None

        cache.clear()
        assert cache.get(b"image", "prompt") is None

    def test_cache_stats_format(self, tmp_path):
        from benchmark import BenchmarkCache

        cache = BenchmarkCache(cache_dir=str(tmp_path / "cache"))
        result = ExtractionResult(fields={"f": {"value": "v"}}, panel_type="front")

        # 1 miss
        cache.get(b"image", "prompt")
        # 1 put + 1 hit
        cache.put(b"image", "prompt", result)
        cache.get(b"image", "prompt")

        stats = cache.stats()
        assert re.match(r"Cache: \d+ hits, \d+ misses \(\d+% hit rate\)", stats)
        assert "1 hits" in stats
        assert "1 misses" in stats
        assert "50% hit rate" in stats


# ---------------------------------------------------------------------------
# RateThrottle tests
# ---------------------------------------------------------------------------


class TestRateThrottle:
    def test_throttle_on_success_decreases_delay(self):
        from benchmark import RateThrottle

        throttle = RateThrottle(initial_delay=5.0, min_delay=1.0, max_delay=10.0)
        initial = throttle._delay
        throttle.on_success()
        assert throttle._delay < initial

    def test_throttle_on_rate_limit_increases_delay(self):
        from benchmark import RateThrottle

        throttle = RateThrottle(initial_delay=3.0, min_delay=1.0, max_delay=10.0)
        initial = throttle._delay
        throttle.on_rate_limit()
        assert throttle._delay > initial

    def test_throttle_respects_bounds(self):
        from benchmark import RateThrottle

        throttle = RateThrottle(initial_delay=3.0, min_delay=1.0, max_delay=10.0)

        # Many successes should not go below min
        for _ in range(100):
            throttle.on_success()
        assert throttle._delay >= 1.0

        # Many rate limits should not go above max
        for _ in range(100):
            throttle.on_rate_limit()
        assert throttle._delay <= 10.0

    def test_throttle_stats_format(self):
        from benchmark import RateThrottle

        throttle = RateThrottle(initial_delay=3.0, min_delay=1.0, max_delay=10.0)
        throttle.on_success()
        throttle.on_success()
        throttle.on_rate_limit()

        stats = throttle.stats()
        assert "success" in stats.lower() or "2" in stats
        assert "rate_limit" in stats.lower() or "1" in stats


# ---------------------------------------------------------------------------
# Quick subset tests
# ---------------------------------------------------------------------------


class TestQuickSubset:
    def _make_fixtures(self) -> list[dict]:
        """Create a realistic fixture set with varying category sizes."""
        fixtures = []
        categories = {
            "good spirits": 18,
            "good wine+beer": 3,
            "bad spirits label": 18,
            "bad spirits photo": 10,
            "bad spirits warning": 8,
            "bad wine+beer": 3,
        }
        for cat, count in categories.items():
            for i in range(count):
                fixtures.append({
                    "id": f"fixture-{cat}-{i}",
                    "category": cat,
                })
        return fixtures

    def test_quick_subset_covers_all_categories(self):
        from benchmark import select_quick_subset

        fixtures = self._make_fixtures()
        subset = select_quick_subset(fixtures)
        subset_cats = {fx["category"] for fx in subset}
        all_cats = {fx["category"] for fx in fixtures}
        assert subset_cats == all_cats

    def test_quick_subset_limits_count(self):
        from benchmark import select_quick_subset

        fixtures = self._make_fixtures()
        subset = select_quick_subset(fixtures)
        # Should be much smaller than the full set (60 fixtures)
        assert len(subset) < len(fixtures)
        # 4 large categories * 2 + 2 small categories * 1 = 10
        assert len(subset) == 10

    def test_quick_subset_fewer_for_small_categories(self):
        from benchmark import select_quick_subset

        fixtures = self._make_fixtures()
        subset = select_quick_subset(fixtures)

        by_cat = {}
        for fx in subset:
            by_cat.setdefault(fx["category"], []).append(fx)

        # Categories with <= 3 fixtures should have 1 representative
        assert len(by_cat["good wine+beer"]) == 1
        assert len(by_cat["bad wine+beer"]) == 1

        # Larger categories should have 2
        assert len(by_cat["good spirits"]) == 2
        assert len(by_cat["bad spirits label"]) == 2
