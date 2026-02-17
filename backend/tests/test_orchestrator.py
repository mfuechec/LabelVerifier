import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.services.orchestrator import VerificationOrchestrator
from app.services.extraction import ExtractionResult
from app.services.comparison import CANONICAL_WARNING
from app.models.schemas import ApplicationData, FieldComparisonResult


@pytest.fixture
def app_data():
    return ApplicationData(
        application_id="APP-001",
        brand_name="Test Brand",
        class_type="Bourbon Whiskey",
        alcohol_content="45%",
        net_contents="750 mL",
        producer_name="Test Distillery",
        producer_address="Louisville, KY",
        beverage_type="distilled_spirits",
    )


@pytest.fixture
def mock_extraction_result():
    return ExtractionResult(
        fields={
            "brand_name": {"value": "TEST BRAND", "bounding_box": {"x": 10, "y": 5, "width": 30, "height": 8}},
            "class_type": {"value": "BOURBON WHISKEY", "bounding_box": {"x": 10, "y": 15, "width": 30, "height": 6}},
            "alcohol_content": {"value": "45% Alc./Vol.", "bounding_box": {"x": 10, "y": 75, "width": 20, "height": 5}},
            "net_contents": {"value": "750 mL", "bounding_box": {"x": 10, "y": 80, "width": 15, "height": 5}},
            "producer_name": {"value": "Test Distillery", "bounding_box": {"x": 10, "y": 85, "width": 25, "height": 5}},
            "producer_address": {"value": "Louisville, KY", "bounding_box": {"x": 10, "y": 90, "width": 25, "height": 5}},
            "government_warning": {"value": CANONICAL_WARNING, "bounding_box": {"x": 5, "y": 50, "width": 90, "height": 20}},
        },
        panel_type="front",
    )


class TestVerificationOrchestrator:
    @pytest.mark.asyncio
    async def test_single_label_flow(self, app_data, mock_extraction_result, tmp_db):
        from app.db.setup import get_db, create_tables
        conn = get_db(tmp_db)
        create_tables(conn)
        conn.close()

        orchestrator = VerificationOrchestrator(db_path=tmp_db)
        orchestrator.extraction_service = AsyncMock()
        orchestrator.extraction_service.extract_fields = AsyncMock(
            return_value=mock_extraction_result
        )
        orchestrator.annotation_service = MagicMock()
        orchestrator.annotation_service.annotate_image = MagicMock(
            return_value="/tmp/annotated.png"
        )

        result = await orchestrator.verify_single(
            images=[b"fake-image-bytes"],
            panels=["front"],
            application_data=app_data,
        )

        assert result.session_id is not None
        assert result.status in ("pass", "needs_review", "fail")
        assert len(result.fields) > 0
        orchestrator.extraction_service.extract_fields.assert_called_once()

    @pytest.mark.asyncio
    async def test_multi_panel_flow(self, app_data, tmp_db):
        from app.db.setup import get_db, create_tables
        conn = get_db(tmp_db)
        create_tables(conn)
        conn.close()

        front_result = ExtractionResult(
            fields={
                "brand_name": {"value": "TEST BRAND", "bounding_box": {"x": 10, "y": 5, "width": 30, "height": 8}},
                "class_type": {"value": "BOURBON WHISKEY", "bounding_box": {"x": 10, "y": 15, "width": 30, "height": 6}},
            },
            panel_type="front",
        )
        back_result = ExtractionResult(
            fields={
                "government_warning": {"value": CANONICAL_WARNING, "bounding_box": {"x": 5, "y": 50, "width": 90, "height": 20}},
                "alcohol_content": {"value": "45% Alc./Vol.", "bounding_box": {"x": 10, "y": 75, "width": 20, "height": 5}},
                "net_contents": {"value": "750 mL", "bounding_box": {"x": 10, "y": 80, "width": 15, "height": 5}},
                "producer_name": {"value": "Test Distillery", "bounding_box": {"x": 10, "y": 85, "width": 25, "height": 5}},
                "producer_address": {"value": "Louisville, KY", "bounding_box": {"x": 10, "y": 90, "width": 25, "height": 5}},
            },
            panel_type="back",
        )

        orchestrator = VerificationOrchestrator(db_path=tmp_db)
        orchestrator.extraction_service = AsyncMock()
        orchestrator.extraction_service.extract_fields = AsyncMock(
            side_effect=[front_result, back_result]
        )
        orchestrator.annotation_service = MagicMock()
        orchestrator.annotation_service.annotate_image = MagicMock(
            return_value="/tmp/annotated.png"
        )

        result = await orchestrator.verify_single(
            images=[b"front-bytes", b"back-bytes"],
            panels=["front", "back"],
            application_data=app_data,
        )

        assert orchestrator.extraction_service.extract_fields.call_count == 2
        assert len(result.fields) > 0

    @pytest.mark.asyncio
    async def test_extraction_failure_returns_partial(self, app_data, tmp_db):
        from app.db.setup import get_db, create_tables
        conn = get_db(tmp_db)
        create_tables(conn)
        conn.close()

        error_result = ExtractionResult(
            panel_type="front",
            error="API timeout",
        )

        orchestrator = VerificationOrchestrator(db_path=tmp_db)
        orchestrator.extraction_service = AsyncMock()
        orchestrator.extraction_service.extract_fields = AsyncMock(
            return_value=error_result
        )

        result = await orchestrator.verify_single(
            images=[b"fake-image-bytes"],
            panels=["front"],
            application_data=app_data,
        )

        assert result.session_id is not None
        assert result.status in ("fail", "needs_review")

    @pytest.mark.asyncio
    async def test_db_persistence(self, app_data, mock_extraction_result, tmp_db):
        from app.db.setup import get_db, create_tables
        conn = get_db(tmp_db)
        create_tables(conn)
        conn.close()

        orchestrator = VerificationOrchestrator(db_path=tmp_db)
        orchestrator.extraction_service = AsyncMock()
        orchestrator.extraction_service.extract_fields = AsyncMock(
            return_value=mock_extraction_result
        )
        orchestrator.annotation_service = MagicMock()
        orchestrator.annotation_service.annotate_image = MagicMock(
            return_value="/tmp/annotated.png"
        )

        result = await orchestrator.verify_single(
            images=[b"fake-image-bytes"],
            panels=["front"],
            application_data=app_data,
        )

        # Verify session was stored
        conn = get_db(tmp_db)
        row = conn.execute(
            "SELECT * FROM verification_sessions WHERE id = ?",
            (result.session_id,),
        ).fetchone()
        assert row is not None
        assert row["beverage_type"] == "distilled_spirits"
        conn.close()

    def test_persist_session_is_atomic(self, app_data, tmp_db):
        """Verify _persist_session is atomic: calling with a duplicate session_id
        should fail, and no partial application row should be left behind."""
        from app.db.setup import get_db, create_tables
        conn = get_db(tmp_db)
        create_tables(conn)
        conn.close()

        orchestrator = VerificationOrchestrator(db_path=tmp_db)

        fields = [
            FieldComparisonResult(
                field_name="brand_name",
                declared_value="Test",
                extracted_value="Test",
                status="match",
                confidence=95.0,
                match_strategy="fuzzy",
            )
        ]

        # First call succeeds
        orchestrator._persist_session(
            "dup-session", app_data, fields, 95.0, "pass",
            "2026-02-14T10:00:00Z",
        )

        # Count applications before the failing second call
        conn = get_db(tmp_db)
        app_count_before = conn.execute(
            "SELECT COUNT(*) as cnt FROM applications"
        ).fetchone()["cnt"]
        conn.close()

        # Second call with same session_id should fail on PK constraint
        with pytest.raises(Exception):
            orchestrator._persist_session(
                "dup-session", app_data, fields, 95.0, "pass",
                "2026-02-14T10:00:00Z",
            )

        # Verify no extra application row was persisted (atomic rollback)
        conn = get_db(tmp_db)
        app_count_after = conn.execute(
            "SELECT COUNT(*) as cnt FROM applications"
        ).fetchone()["cnt"]
        conn.close()
        assert app_count_after == app_count_before, (
            "No extra application row should exist after failed duplicate insert"
        )
