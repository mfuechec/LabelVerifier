import pytest
from unittest.mock import patch
from app.main import create_app
from app.db.setup import get_db, create_tables


@pytest.fixture
def app(tmp_db):
    application = create_app()
    application.state.db_path = tmp_db
    conn = get_db(tmp_db)
    create_tables(conn)
    conn.execute(
        """INSERT INTO verification_sessions
           (id, beverage_type, status, overall_confidence, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("session-1", "distilled_spirits", "pass", 95.0,
         "2026-02-14T10:00:00Z", "2026-02-14T10:00:00Z"),
    )
    conn.execute(
        """INSERT INTO comparison_results
           (id, session_id, field_name, declared_value, extracted_value,
            match_strategy, status, confidence)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("cr-1", "session-1", "brand_name", "Test Brand", "Test Brand",
         "fuzzy", "match", 95.0),
    )
    conn.commit()
    conn.close()
    return application


class TestFieldOverride:
    @pytest.mark.asyncio
    async def test_override_field(self, client, app):
        with patch("app.api.routes.feedback.get_db_path") as mock_path:
            mock_path.return_value = app.state.db_path
            response = await client.patch(
                "/api/v1/verify/session-1/fields/brand_name",
                json={"override_status": "content_mismatch", "note": "Actually wrong"},
            )
        assert response.status_code == 200


class TestDecision:
    @pytest.mark.asyncio
    async def test_submit_decision(self, client, app):
        with patch("app.api.routes.feedback.get_db_path") as mock_path:
            mock_path.return_value = app.state.db_path
            response = await client.post(
                "/api/v1/verify/session-1/decision",
                json={"decision": "confirmed", "notes": "All good"},
            )
        assert response.status_code == 200


class TestFeedback:
    @pytest.mark.asyncio
    async def test_submit_feedback(self, client, app):
        with patch("app.api.routes.feedback.get_db_path") as mock_path:
            mock_path.return_value = app.state.db_path
            response = await client.post(
                "/api/v1/verify/session-1/feedback",
                json={"ai_correct": True},
            )
        assert response.status_code == 200
