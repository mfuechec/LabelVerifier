"""
Integration tests that exercise the full pipeline:
  extraction (mocked) -> merger -> comparison -> compliance -> scoring

Uses fixtures from sample_applications.json with realistic mock extraction
results. All services except extraction are real (no mocks).

Scenario categories:
  - pass: application matches label exactly
  - fail_mismatch: application has intentionally wrong values vs label
  - fail_missing: label missing required fields
  - needs_review: hard-to-read labels with extraction uncertainty
  - edge_cases: warning variations, non-English text, etc.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.models.schemas import ApplicationData, FieldComparisonResult
from app.services.extraction import ExtractionResult
from app.services.comparison import ComparisonService, ConfidenceScorer, CANONICAL_WARNING
from app.services.compliance import ComplianceChecker
from app.services.merger import ImageMerger

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "sample_applications.json"
GOLDEN_PATH = Path(__file__).parent / "fixtures" / "golden_extractions.json"


def load_fixtures():
    with open(FIXTURES_PATH) as f:
        return json.load(f)["fixtures"]


def load_golden_extractions() -> tuple[dict[str, dict], dict[str, dict[str, str]]]:
    """Load golden extraction data and confidences from golden_extractions.json.

    Returns (extractions_dict, confidences_dict).
    """
    with open(GOLDEN_PATH) as f:
        data = json.load(f)
    return data["extractions"], data.get("extraction_confidences", {})


FIXTURES = load_fixtures()


def get_fixture(fixture_id: str) -> dict:
    for f in FIXTURES:
        if f["id"] == fixture_id:
            return f
    raise ValueError(f"Fixture {fixture_id} not found")


def fixtures_by_category(category: str) -> list[dict]:
    return [f for f in FIXTURES if f["scenario_category"] == category]


def build_app_data(fixture: dict) -> ApplicationData:
    """Build ApplicationData from fixture's application_data."""
    ad = fixture["application_data"]
    return ApplicationData(
        application_id=ad.get("application_id"),
        brand_name=ad["brand_name"],
        class_type=ad["class_type"],
        alcohol_content=ad["alcohol_content"],
        net_contents=ad["net_contents"],
        producer_name=ad.get("producer_name"),
        producer_address=ad.get("producer_address"),
        country_of_origin=ad.get("country_of_origin"),
        importer_name=ad.get("importer_name"),
        importer_address=ad.get("importer_address"),
        beverage_type=ad["beverage_type"],
        has_sulfites_declaration=ad.get("has_sulfites_declaration", False),
    )


# =============================================================================
# Golden extraction data (loaded from file)
# =============================================================================
# These represent human-verified ground truth of what appears on each label.
# Initially migrated from hand-written mocks, to be updated with real LLM
# extractions via `benchmark.py --save-golden` and then human-reviewed.

GOLDEN_EXTRACTIONS, GOLDEN_EXTRACTION_CONFIDENCES = load_golden_extractions()


def build_mock_extraction(fixture_id: str) -> dict[str, str | None]:
    """Get golden extraction data for a fixture."""
    return GOLDEN_EXTRACTIONS.get(fixture_id, {})

# --- Real service instances (no mocks) ---
comparison_service = ComparisonService()
confidence_scorer = ConfidenceScorer()
compliance_checker = ComplianceChecker()
merger = ImageMerger()


def run_pipeline(fixture_id: str) -> tuple[list[FieldComparisonResult], float, str]:
    """Run the full comparison+compliance+scoring pipeline for a fixture.

    Returns (field_results, overall_confidence, status).
    """
    fixture = get_fixture(fixture_id)
    app_data = build_app_data(fixture)
    extracted = build_mock_extraction(fixture_id)
    extraction_confidences = GOLDEN_EXTRACTION_CONFIDENCES.get(fixture_id)

    field_results = comparison_service.compare_fields(
        extracted, app_data, app_data.beverage_type,
        extraction_confidences=extraction_confidences,
    )

    # Run compliance checks (independent of application data)
    is_imported = bool(app_data.country_of_origin or app_data.importer_name)
    compliance_issues = compliance_checker.check_compliance(
        extracted, app_data.beverage_type,
        is_imported=is_imported,
        requires_sulfites=app_data.has_sulfites_declaration,
    )

    # Merge compliance issues into field_results
    existing_field_names = {r.field_name for r in field_results}
    for issue in compliance_issues:
        existing = next(
            (r for r in field_results if r.field_name == issue.field_name),
            None,
        )
        if existing and existing.status == "field_missing":
            existing.confidence_reason = issue.message
        elif issue.field_name not in existing_field_names:
            status_val = (
                "extraction_uncertain" if issue.severity == "needs_review"
                else "field_missing"
            )
            field_results.append(FieldComparisonResult(
                field_name=issue.field_name,
                declared_value=None,
                extracted_value=None,
                status=status_val,
                confidence=0.0,
                match_strategy="compliance",
                confidence_reason=issue.message,
            ))
            existing_field_names.add(issue.field_name)

    overall_confidence, status = confidence_scorer.calculate(field_results)

    return field_results, overall_confidence, status


def get_field_status(fields: list[FieldComparisonResult], field_name: str) -> str | None:
    """Get the status of a specific field from results."""
    for f in fields:
        if f.field_name == field_name:
            return f.status
    return None


def get_field_confidence(fields: list[FieldComparisonResult], field_name: str) -> float | None:
    """Get the confidence of a specific field from results."""
    for f in fields:
        if f.field_name == field_name:
            return f.confidence
    return None


# ============================================================
# Pass scenarios: application matches label exactly
# ============================================================
PASS_IDS = [f["id"] for f in FIXTURES if f["scenario_category"] == "pass"]


class TestPassScenarios:
    """All pass scenarios should result in status='pass' with high confidence."""

    @pytest.mark.parametrize("fixture_id", PASS_IDS)
    def test_overall_status_is_pass(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        assert status == "pass", f"{fixture_id}: expected pass, got {status}"

    @pytest.mark.parametrize("fixture_id", PASS_IDS)
    def test_confidence_at_least_90(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        assert confidence >= 90.0, f"{fixture_id}: confidence {confidence} < 90"

    @pytest.mark.parametrize("fixture_id", PASS_IDS)
    def test_no_content_mismatches(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        mismatches = [f for f in fields if f.status == "content_mismatch"]
        assert len(mismatches) == 0, (
            f"{fixture_id}: unexpected mismatches: "
            f"{[(m.field_name, m.status) for m in mismatches]}"
        )

    @pytest.mark.parametrize("fixture_id", PASS_IDS)
    def test_expected_field_results(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        fixture = get_fixture(fixture_id)
        for field_name, expected in fixture["expected_outcome"]["expected_field_results"].items():
            actual = get_field_status(fields, field_name)
            assert actual == expected, (
                f"{fixture_id}.{field_name}: expected {expected}, got {actual}"
            )


# ============================================================
# Fail mismatch scenarios: app has wrong values vs label
# ============================================================
MISMATCH_IDS = [f["id"] for f in FIXTURES if f["scenario_category"] == "fail_mismatch"]


class TestMismatchScenarios:
    """Mismatch scenarios should fail or need review (non-critical fields → needs_review)."""

    @pytest.mark.parametrize("fixture_id", MISMATCH_IDS)
    def test_overall_status_matches_expected(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        expected = get_fixture(fixture_id)["expected_outcome"]["overall_status"]
        assert status == expected, f"{fixture_id}: expected {expected}, got {status}"

    @pytest.mark.parametrize("fixture_id", MISMATCH_IDS)
    def test_has_at_least_one_mismatch(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        fixture = get_fixture(fixture_id)
        expected_mismatches = [
            k for k, v in fixture["expected_outcome"]["expected_field_results"].items()
            if v == "content_mismatch"
        ]
        actual_mismatches = [f.field_name for f in fields if f.status == "content_mismatch"]
        for expected_field in expected_mismatches:
            assert expected_field in actual_mismatches, (
                f"{fixture_id}: expected {expected_field} to be content_mismatch, "
                f"actual mismatches: {actual_mismatches}"
            )

    @pytest.mark.parametrize("fixture_id", MISMATCH_IDS)
    def test_matching_fields_still_match(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        fixture = get_fixture(fixture_id)
        for field_name, expected in fixture["expected_outcome"]["expected_field_results"].items():
            if expected == "match":
                actual = get_field_status(fields, field_name)
                assert actual == "match", (
                    f"{fixture_id}.{field_name}: expected match, got {actual}"
                )


# ============================================================
# Fail missing scenarios: label missing required fields
# ============================================================
MISSING_IDS = [f["id"] for f in FIXTURES if f["scenario_category"] == "fail_missing"]


class TestMissingScenarios:
    """Labels with missing or mismatched fields should fail or need review."""

    @pytest.mark.parametrize("fixture_id", MISSING_IDS)
    def test_overall_status_matches_expected(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        expected = get_fixture(fixture_id)["expected_outcome"]["overall_status"]
        assert status == expected, f"{fixture_id}: expected {expected}, got {status}"

    @pytest.mark.parametrize("fixture_id", MISSING_IDS)
    def test_expected_field_results(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        fixture = get_fixture(fixture_id)
        for field_name, expected in fixture["expected_outcome"]["expected_field_results"].items():
            actual = get_field_status(fields, field_name)
            assert actual == expected, (
                f"{fixture_id}.{field_name}: expected {expected}, got {actual}"
            )


# ============================================================
# Needs review scenarios: extraction uncertainty
# ============================================================
REVIEW_IDS = [f["id"] for f in FIXTURES if f["scenario_category"] == "needs_review"]


class TestNeedsReviewScenarios:
    """Hard-to-read labels should fail or need review."""

    @pytest.mark.parametrize("fixture_id", REVIEW_IDS)
    def test_overall_status_is_fail_or_needs_review(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        # Missing fields cause fail (which is correct -- agent must review)
        assert status in ("fail", "needs_review"), (
            f"{fixture_id}: expected fail/needs_review, got {status}"
        )

    @pytest.mark.parametrize("fixture_id", REVIEW_IDS)
    def test_has_missing_or_uncertain_fields(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        problem_fields = [
            f for f in fields
            if f.status in ("field_missing", "extraction_uncertain")
        ]
        assert len(problem_fields) > 0, (
            f"{fixture_id}: expected at least one missing/uncertain field"
        )


# ============================================================
# Edge case scenarios: warning variations, non-English text
# ============================================================
EDGE_IDS = [f["id"] for f in FIXTURES if f["scenario_category"] == "edge_cases"]


class TestEdgeCaseScenarios:
    """Edge cases should produce expected outcomes."""

    @pytest.mark.parametrize("fixture_id", EDGE_IDS)
    def test_overall_status_is_fail(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        expected = get_fixture(fixture_id)["expected_outcome"]["overall_status"]
        assert status == expected, f"{fixture_id}: expected {expected}, got {status}"

    @pytest.mark.parametrize("fixture_id", EDGE_IDS)
    def test_expected_field_results(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        fixture = get_fixture(fixture_id)
        for field_name, expected in fixture["expected_outcome"]["expected_field_results"].items():
            actual = get_field_status(fields, field_name)
            assert actual == expected, (
                f"{fixture_id}.{field_name}: expected {expected}, got {actual}"
            )


# ============================================================
# Specific representative tests for key scenarios
# ============================================================
class TestAngelsEnvyPass:
    """Representative pass test: all fields match after golden data correction."""

    def setup_method(self):
        self.fields, self.confidence, self.status = run_pipeline("pass-angels-envy")

    def test_overall_pass(self):
        assert self.status == "pass"
        assert self.confidence >= 90.0

    def test_no_mismatches_or_missing(self):
        for f in self.fields:
            assert f.status not in ("content_mismatch", "field_missing"), (
                f"{f.field_name} has unexpected status {f.status}"
            )


class TestAngelsEnvyWrongAbv:
    """Representative mismatch test: ABV differs between app and label."""

    def setup_method(self):
        self.fields, self.confidence, self.status = run_pipeline(
            "mismatch-angels-envy-wrong-abv"
        )

    def test_overall_fail(self):
        assert self.status == "fail"

    def test_abv_is_content_mismatch(self):
        assert get_field_status(self.fields, "alcohol_content") == "content_mismatch"

    def test_other_fields_still_match(self):
        assert get_field_status(self.fields, "brand_name") == "match"
        assert get_field_status(self.fields, "class_type") == "match"
        assert get_field_status(self.fields, "net_contents") == "match"
        assert get_field_status(self.fields, "government_warning") == "match"


class TestMokkaClassMismatch:
    """Representative fail test: declared class incomplete vs actual label text."""

    def setup_method(self):
        self.fields, self.confidence, self.status = run_pipeline("review-mokka")

    def test_overall_fail(self):
        assert self.status == "fail"

    def test_brand_matches(self):
        assert get_field_status(self.fields, "brand_name") == "match"

    def test_class_content_mismatch(self):
        assert get_field_status(self.fields, "class_type") == "content_mismatch"

    def test_simple_fields_still_match(self):
        assert get_field_status(self.fields, "alcohol_content") == "match"
        assert get_field_status(self.fields, "net_contents") == "match"


class TestWoodfordWarningOmission:
    """Woodford Reserve: golden data has brand_name missing (extraction returns different name)."""

    def setup_method(self):
        self.fields, self.confidence, self.status = run_pipeline(
            "edge-woodford-warning-omission"
        )

    def test_overall_fail(self):
        assert self.status == "fail"

    def test_brand_name_missing(self):
        assert get_field_status(self.fields, "brand_name") == "field_missing"

    def test_warning_matches(self):
        """Golden extraction has correct warning text for this label."""
        assert get_field_status(self.fields, "government_warning") == "match"

    def test_other_fields_match(self):
        assert get_field_status(self.fields, "class_type") == "match"
        assert get_field_status(self.fields, "alcohol_content") == "match"


class TestHowlingMoonWarningSpacing:
    """Howling Moon: warning has spacing issue + class_type mismatch."""

    def setup_method(self):
        self.fields, self.confidence, self.status = run_pipeline(
            "edge-howling-moon-warning-spacing"
        )

    def test_overall_fail(self):
        assert self.status == "fail"

    def test_warning_is_content_mismatch(self):
        assert get_field_status(self.fields, "government_warning") == "content_mismatch"

    def test_class_type_mismatch(self):
        assert get_field_status(self.fields, "class_type") == "content_mismatch"

    def test_other_fields_match(self):
        assert get_field_status(self.fields, "brand_name") == "match"
        assert get_field_status(self.fields, "alcohol_content") == "match"


class TestWhiteLabelWarningTypo:
    """White Label: golden data has brand_name mismatch and warning match."""

    def setup_method(self):
        self.fields, self.confidence, self.status = run_pipeline(
            "edge-white-label-warning-typo"
        )

    def test_overall_fail(self):
        assert self.status == "fail"

    def test_brand_name_mismatch(self):
        assert get_field_status(self.fields, "brand_name") == "content_mismatch"

    def test_warning_matches(self):
        """Golden extraction has correct warning text for this label."""
        assert get_field_status(self.fields, "government_warning") == "match"

    def test_other_fields_match(self):
        assert get_field_status(self.fields, "class_type") == "match"
        assert get_field_status(self.fields, "alcohol_content") == "match"


class TestSailorJerryMiniatureWarning:
    """50mL miniature -- golden data has multiple mismatches and missing fields."""

    def setup_method(self):
        self.fields, self.confidence, self.status = run_pipeline(
            "edge-sailor-jerry-warning-miniature"
        )

    def test_overall_fail(self):
        assert self.status == "fail"

    def test_warning_matches(self):
        """Golden extraction has correct warning text despite small label."""
        assert get_field_status(self.fields, "government_warning") == "match"

    def test_producer_missing(self):
        assert get_field_status(self.fields, "producer_name") == "field_missing"


class TestJacquesCardinTinyWarning:
    """Jacques Cardin: golden data shows all fields match including warning."""

    def setup_method(self):
        self.fields, self.confidence, self.status = run_pipeline(
            "edge-jacques-cardin-warning-tiny"
        )

    def test_overall_pass(self):
        assert self.status == "pass"

    def test_warning_matches(self):
        """Golden extraction has correct warning text."""
        assert get_field_status(self.fields, "government_warning") == "match"


class TestPresidentialDramWarningCorrect:
    """Warning text is correct and clear -- should pass despite being in bad-warning folder."""

    def setup_method(self):
        self.fields, self.confidence, self.status = run_pipeline(
            "edge-presidential-dram-warning-correct"
        )

    def test_overall_pass(self):
        """Label with correct warning text should pass (font-size violations are out of scope)."""
        assert self.status == "pass"

    def test_warning_matches(self):
        assert get_field_status(self.fields, "government_warning") == "match"


# ============================================================
# Compliance checker integration
# ============================================================
# ============================================================
# Compliance scenarios: mandatory fields caught by compliance checker
# ============================================================
COMPLIANCE_IDS = [f["id"] for f in FIXTURES if f["scenario_category"] == "compliance"]


class TestComplianceScenarios:
    """Compliance checker catches missing mandatory fields independent of app data."""

    @pytest.mark.parametrize("fixture_id", COMPLIANCE_IDS)
    def test_overall_status_matches_expected(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        expected = get_fixture(fixture_id)["expected_outcome"]["overall_status"]
        assert status == expected, f"{fixture_id}: expected {expected}, got {status}"

    @pytest.mark.parametrize("fixture_id", COMPLIANCE_IDS)
    def test_expected_field_results(self, fixture_id):
        fields, confidence, status = run_pipeline(fixture_id)
        fixture = get_fixture(fixture_id)
        for field_name, expected in fixture["expected_outcome"]["expected_field_results"].items():
            actual = get_field_status(fields, field_name)
            assert actual == expected, (
                f"{fixture_id}.{field_name}: expected {expected}, got {actual}"
            )

    def test_compliance_missing_producer_has_reason(self):
        """Compliance-injected field_missing should have a regulatory citation."""
        fields, confidence, status = run_pipeline("compliance-missing-producer-on-label")
        producer = next(f for f in fields if f.field_name == "producer_name")
        assert producer.status == "field_missing"
        assert producer.match_strategy == "compliance"
        assert "27 CFR" in (producer.confidence_reason or "")

    def test_compliance_imported_origin_present(self):
        """Imported product with country_of_origin on label should match (not flagged)."""
        fields, confidence, status = run_pipeline("compliance-imported-missing-origin")
        origin = next((f for f in fields if f.field_name == "country_of_origin"), None)
        assert origin is not None
        assert origin.status == "match"

    def test_compliance_producer_flagged_for_imported(self):
        """For imported product with null producer in both app and label, compliance injects field_missing."""
        fields, confidence, status = run_pipeline("compliance-imported-missing-origin")
        producer = next((f for f in fields if f.field_name == "producer_name"), None)
        assert producer is not None
        assert producer.status == "field_missing"
        assert "27 CFR" in (producer.confidence_reason or "")


class TestComplianceIntegration:
    """Verify compliance checker works with real extraction data."""

    def test_good_spirits_no_issues(self):
        extracted = build_mock_extraction("pass-angels-envy")
        issues = compliance_checker.check_compliance(
            extracted, "distilled_spirits", is_imported=False
        )
        assert len(issues) == 0

    def test_imported_spirits_no_issues(self):
        extracted = build_mock_extraction("edge-hanami-gin-miniature")
        issues = compliance_checker.check_compliance(
            extracted, "distilled_spirits", is_imported=True
        )
        assert len(issues) == 0

    def test_imported_wine_sulfites_not_flagged(self):
        extracted = build_mock_extraction("review-rosso-veneto-brand-confusion")
        issues = compliance_checker.check_compliance(
            extracted, "wine", is_imported=True, requires_sulfites=True
        )
        flagged = [i.field_name for i in issues]
        assert "sulfites_declaration" not in flagged
        assert "country_of_origin" not in flagged

    def test_mokka_no_mandatory_fields_missing(self):
        """Mokka golden extraction now has all mandatory fields including producer."""
        extracted = build_mock_extraction("review-mokka")
        issues = compliance_checker.check_compliance(
            extracted, "distilled_spirits", is_imported=False
        )
        missing_fields = [i.field_name for i in issues]
        assert len(missing_fields) == 0, f"Unexpected missing fields: {missing_fields}"

    def test_compliance_catches_missing_producer(self):
        """When producer_name is null in extraction, compliance flags it."""
        extracted = build_mock_extraction("compliance-missing-producer-on-label")
        issues = compliance_checker.check_compliance(
            extracted, "distilled_spirits", is_imported=False
        )
        missing_fields = [i.field_name for i in issues]
        assert "producer_name" in missing_fields
        # Check for regulatory citation
        producer_issue = next(i for i in issues if i.field_name == "producer_name")
        assert "27 CFR" in producer_issue.message


# ============================================================
# Merger integration with multi-panel extraction
# ============================================================
class TestMergerIntegration:
    """Verify merger correctly combines front+back panels."""

    def test_merge_front_back_no_conflict(self):
        front = {
            "brand_name": {"value": "Angel's Envy", "confidence": 95.0},
            "class_type": {"value": "Kentucky Straight Bourbon Whiskey Finished in Port Wine Barrels", "confidence": 90.0},
            "alcohol_content": {"value": "43.3% Alc./Vol.", "confidence": 92.0},
            "net_contents": {"value": "750 mL", "confidence": 98.0},
        }
        back = {
            "producer_name": {"value": "Louisville Spirits Group", "confidence": 90.0},
            "government_warning": {"value": CANONICAL_WARNING, "confidence": 85.0},
        }
        merged = merger.merge_panels({"front": front, "back": back})
        assert "brand_name" in merged.fields
        assert "government_warning" in merged.fields
        assert merged.fields["brand_name"].source_panel == "front"
        assert merged.fields["government_warning"].source_panel == "back"
        assert len(merged.conflicts) == 0

    def test_merge_conflict_prefers_front(self):
        front = {
            "brand_name": {"value": "Angel's Envy", "confidence": 90.0},
        }
        back = {
            "brand_name": {"value": "ANGEL'S ENVY", "confidence": 85.0},
        }
        merged = merger.merge_panels({"front": front, "back": back})
        assert merged.fields["brand_name"].value == "Angel's Envy"
        assert merged.fields["brand_name"].source_panel == "front"
        assert len(merged.conflicts) == 1


# ============================================================
# End-to-end pipeline with orchestrator (mocked extraction)
# ============================================================
class TestOrchestratorIntegration:
    """Test the orchestrator with mocked extraction but real everything else."""

    @pytest.fixture
    def orchestrator(self, tmp_db):
        from app.db.setup import create_tables, get_db
        conn = get_db(tmp_db)
        create_tables(conn)
        conn.close()

        from app.services.orchestrator import VerificationOrchestrator
        orch = VerificationOrchestrator(db_path=tmp_db)
        return orch

    def _mock_extraction_result(self, fixture_id: str, panel: str) -> ExtractionResult:
        """Build an ExtractionResult that mimics Claude's output format."""
        raw = build_mock_extraction(fixture_id)
        fields = {}
        for field_name, value in raw.items():
            fields[field_name] = {
                "value": value,
                "bounding_box": {"x": 10, "y": 10, "width": 30, "height": 5} if value else None,
            }
        return ExtractionResult(
            fields=fields,
            panel_type=panel,
            extraction_notes="Mock extraction for testing",
        )

    @pytest.mark.asyncio
    async def test_pass_scenario_full_orchestrator(self, orchestrator):
        fixture = get_fixture("pass-den-of-thieves")
        app_data = build_app_data(fixture)

        mock_front = self._mock_extraction_result("pass-den-of-thieves", "front")
        mock_back = self._mock_extraction_result("pass-den-of-thieves", "back")

        async def mock_extract(image_bytes, panel_type, mime_type="image/jpeg"):
            return mock_front if panel_type == "front" else mock_back

        with patch.object(orchestrator.extraction_service, "extract_fields", side_effect=mock_extract):
            result = await orchestrator.verify_single(
                images=[b"fake-front", b"fake-back"],
                panels=["front", "back"],
                application_data=app_data,
            )

        assert result.status == "pass"
        assert result.overall_confidence >= 90.0
        assert result.session_id is not None
        assert result.beverage_type == "distilled_spirits"

    @pytest.mark.asyncio
    async def test_mismatch_scenario_full_orchestrator(self, orchestrator):
        fixture = get_fixture("mismatch-angels-envy-wrong-abv")
        app_data = build_app_data(fixture)

        mock_result = self._mock_extraction_result("mismatch-angels-envy-wrong-abv", "front")

        async def mock_extract(image_bytes, panel_type, mime_type="image/jpeg"):
            return mock_result

        with patch.object(orchestrator.extraction_service, "extract_fields", side_effect=mock_extract):
            result = await orchestrator.verify_single(
                images=[b"fake-front"],
                panels=["front"],
                application_data=app_data,
            )

        assert result.status == "fail"
        abv_field = next(f for f in result.fields if f.field_name == "alcohol_content")
        assert abv_field.status == "content_mismatch"

    @pytest.mark.asyncio
    async def test_result_persisted_to_db(self, orchestrator, tmp_db):
        fixture = get_fixture("pass-den-of-thieves")
        app_data = build_app_data(fixture)

        mock_result = self._mock_extraction_result("pass-den-of-thieves", "front")

        async def mock_extract(image_bytes, panel_type, mime_type="image/jpeg"):
            return mock_result

        with patch.object(orchestrator.extraction_service, "extract_fields", side_effect=mock_extract):
            result = await orchestrator.verify_single(
                images=[b"fake-front"],
                panels=["front"],
                application_data=app_data,
            )

        from app.db.setup import get_db
        conn = get_db(tmp_db)
        try:
            row = conn.execute(
                "SELECT * FROM verification_sessions WHERE id = ?",
                (result.session_id,),
            ).fetchone()
            assert row is not None
            assert row["status"] == "pass"
            assert row["beverage_type"] == "distilled_spirits"

            fields = conn.execute(
                "SELECT * FROM comparison_results WHERE session_id = ?",
                (result.session_id,),
            ).fetchall()
            assert len(fields) > 0
        finally:
            conn.close()
