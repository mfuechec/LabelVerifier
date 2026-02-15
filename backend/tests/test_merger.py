from app.services.merger import ImageMerger


class TestImageMerger:
    def setup_method(self):
        self.merger = ImageMerger()

    def test_single_panel_passthrough(self):
        panel_results = {
            "front": {
                "brand_name": {"value": "Test Brand", "confidence": 95.0},
                "class_type": {"value": "Bourbon", "confidence": 90.0},
            }
        }
        merged = self.merger.merge_panels(panel_results)
        assert merged.fields["brand_name"].value == "Test Brand"
        assert merged.fields["class_type"].value == "Bourbon"

    def test_front_back_no_overlap(self):
        panel_results = {
            "front": {
                "brand_name": {"value": "Test Brand", "confidence": 95.0},
                "class_type": {"value": "Bourbon", "confidence": 90.0},
            },
            "back": {
                "government_warning": {"value": "GOVERNMENT WARNING: ...", "confidence": 98.0},
                "producer_name": {"value": "Test Distillery", "confidence": 92.0},
            },
        }
        merged = self.merger.merge_panels(panel_results)
        assert "brand_name" in merged.fields
        assert "government_warning" in merged.fields
        assert len(merged.conflicts) == 0

    def test_same_field_same_value_merges(self):
        panel_results = {
            "front": {
                "brand_name": {"value": "Test Brand", "confidence": 95.0},
            },
            "back": {
                "brand_name": {"value": "Test Brand", "confidence": 90.0},
            },
        }
        merged = self.merger.merge_panels(panel_results)
        assert merged.fields["brand_name"].value == "Test Brand"
        # Should use highest confidence
        assert merged.fields["brand_name"].confidence == 95.0
        assert len(merged.conflicts) == 0

    def test_same_field_different_value_flags_conflict(self):
        panel_results = {
            "front": {
                "brand_name": {"value": "Brand A", "confidence": 95.0},
            },
            "back": {
                "brand_name": {"value": "Brand B", "confidence": 90.0},
            },
        }
        merged = self.merger.merge_panels(panel_results)
        # Should prefer front
        assert merged.fields["brand_name"].value == "Brand A"
        assert merged.fields["brand_name"].source_panel == "front"
        # Should flag conflict
        assert len(merged.conflicts) == 1
        assert merged.conflicts[0].field_name == "brand_name"

    def test_extraction_confidence_propagated(self):
        """extraction_confidence should be propagated through merge."""
        panel_results = {
            "front": {
                "brand_name": {
                    "value": "Test Brand",
                    "confidence": 95.0,
                    "extraction_confidence": "medium",
                },
            }
        }
        merged = self.merger.merge_panels(panel_results)
        assert merged.fields["brand_name"].extraction_confidence == "medium"

    def test_extraction_confidence_defaults_to_high(self):
        """Missing extraction_confidence should default to 'high'."""
        panel_results = {
            "front": {
                "brand_name": {"value": "Test Brand", "confidence": 95.0},
            }
        }
        merged = self.merger.merge_panels(panel_results)
        assert merged.fields["brand_name"].extraction_confidence == "high"

    def test_higher_confidence_tier_preferred_in_conflict(self):
        """When panels conflict, prefer higher extraction_confidence tier."""
        panel_results = {
            "front": {
                "brand_name": {
                    "value": "Brand A",
                    "confidence": 90.0,
                    "extraction_confidence": "low",
                },
            },
            "back": {
                "brand_name": {
                    "value": "Brand B",
                    "confidence": 90.0,
                    "extraction_confidence": "high",
                },
            },
        }
        merged = self.merger.merge_panels(panel_results)
        # Should prefer high confidence over panel priority
        assert merged.fields["brand_name"].value == "Brand B"
        assert merged.fields["brand_name"].extraction_confidence == "high"

    def test_null_front_uses_back_value(self):
        """When front returns None and back has a value, use back's value."""
        panel_results = {
            "front": {
                "government_warning": {"value": None, "confidence": 90.0},
            },
            "back": {
                "government_warning": {"value": "GOVERNMENT WARNING: ...", "confidence": 90.0},
            },
        }
        merged = self.merger.merge_panels(panel_results)
        assert merged.fields["government_warning"].value == "GOVERNMENT WARNING: ..."
        assert merged.fields["government_warning"].source_panel == "back"
        assert len(merged.conflicts) == 0
