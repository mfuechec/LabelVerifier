"""Tests for multi-panel image merger."""

import pytest
from app.services.merger import ImageMerger


@pytest.fixture
def merger():
    return ImageMerger()


class TestImageMerger:
    def test_single_panel(self, merger):
        """Single panel: all fields pass through."""
        panel_data = {
            "front": {
                "brand_name": {"value": "TEST", "confidence": 95.0},
                "alcohol_content": {"value": "40%", "confidence": 90.0},
            }
        }
        result = merger.merge_panels(panel_data)
        assert result.fields["brand_name"].value == "TEST"
        assert result.fields["alcohol_content"].value == "40%"

    def test_multi_panel_merge(self, merger):
        """Two panels: each contributes different fields."""
        panel_data = {
            "front": {
                "brand_name": {"value": "TEST", "confidence": 95.0},
            },
            "back": {
                "government_warning": {"value": "GOVERNMENT WARNING: ...", "confidence": 90.0},
            },
        }
        result = merger.merge_panels(panel_data)
        assert "brand_name" in result.fields
        assert "government_warning" in result.fields

    def test_multi_panel_conflict_higher_extraction_confidence(self, merger):
        """When same field appears on multiple panels, higher extraction confidence wins."""
        panel_data = {
            "front": {
                "brand_name": {"value": "BRAND A", "confidence": 60.0, "extraction_confidence": "low"},
            },
            "back": {
                "brand_name": {"value": "BRAND B", "confidence": 95.0, "extraction_confidence": "high"},
            },
        }
        result = merger.merge_panels(panel_data)
        assert result.fields["brand_name"].value == "BRAND B"

    def test_multi_panel_conflict_same_tier_prefers_front(self, merger):
        """When extraction confidence is equal, front panel wins by priority."""
        panel_data = {
            "front": {
                "brand_name": {"value": "BRAND A", "confidence": 60.0},
            },
            "back": {
                "brand_name": {"value": "BRAND B", "confidence": 95.0},
            },
        }
        result = merger.merge_panels(panel_data)
        assert result.fields["brand_name"].value == "BRAND A"

    def test_multi_panel_agreement(self, merger):
        """Same field, same value on both panels."""
        panel_data = {
            "front": {
                "brand_name": {"value": "SAME BRAND", "confidence": 90.0},
            },
            "back": {
                "brand_name": {"value": "SAME BRAND", "confidence": 85.0},
            },
        }
        result = merger.merge_panels(panel_data)
        assert result.fields["brand_name"].value == "SAME BRAND"

    def test_empty_panels(self, merger):
        result = merger.merge_panels({})
        assert len(result.fields) == 0

    def test_extraction_confidence_preserved(self, merger):
        panel_data = {
            "front": {
                "brand_name": {
                    "value": "TEST",
                    "confidence": 90.0,
                    "extraction_confidence": "medium",
                },
            },
        }
        result = merger.merge_panels(panel_data)
        assert result.fields["brand_name"].extraction_confidence == "medium"
