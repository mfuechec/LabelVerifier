"""Tests for the VerificationRepository layer."""

import uuid

import pytest

from app.db.repository import VerificationRepository
from app.models.schemas import ApplicationData, FieldComparisonResult, ProcessingStats


@pytest.fixture
def repo(tmp_db, db_conn):
    """Create a repository backed by the test database.

    db_conn is used only to ensure tables are created; the repo
    opens its own connections via get_db(tmp_db).
    """
    return VerificationRepository(db_path=tmp_db)


@pytest.fixture
def session_id():
    return str(uuid.uuid4())


@pytest.fixture
def app_data(sample_application_data):
    return sample_application_data


@pytest.fixture
def fields():
    return [
        FieldComparisonResult(
            field_name="brand_name",
            declared_value="HOWLING MOON",
            extracted_value="HOWLING MOON",
            match_strategy="fuzzy",
            status="match",
            confidence=95.0,
            extraction_confidence="high",
            confidence_reason="exact token match",
        ),
        FieldComparisonResult(
            field_name="alcohol_content",
            declared_value="50%",
            extracted_value="50%",
            match_strategy="numeric",
            status="match",
            confidence=100.0,
            extraction_confidence="high",
            confidence_reason="numeric match",
        ),
    ]


# ── Session CRUD ─────────────────────────────────────────────────


class TestCreateAndGetSession:
    def test_create_and_get(self, repo, session_id, app_data, fields):
        repo.create_session(session_id, app_data, fields, 95.0, "pass", "2026-01-01T00:00:00Z")

        session = repo.get_session(session_id)
        assert session is not None
        assert session["id"] == session_id
        assert session["status"] == "pass"
        assert session["overall_confidence"] == 95.0
        assert session["beverage_type"] == "distilled_spirits"

    def test_get_nonexistent(self, repo):
        assert repo.get_session("nonexistent-id") is None

    def test_create_with_processing_stats(self, repo, session_id, app_data, fields):
        stats = ProcessingStats(
            total_llm_calls=3,
            total_input_tokens=5000,
            total_output_tokens=1000,
            extraction_time_ms=2000,
            total_time_ms=3000,
            estimated_cost_usd=0.025,
        )
        repo.create_session(session_id, app_data, fields, 90.0, "pass", "2026-01-01T00:00:00Z", processing_stats=stats)

        session = repo.get_session(session_id)
        assert session["total_llm_calls"] == 3
        assert session["total_input_tokens"] == 5000
        assert session["total_output_tokens"] == 1000
        assert session["extraction_time_ms"] == 2000
        assert session["processing_time_ms"] == 3000

    def test_create_with_batch_id(self, repo, session_id, app_data, fields):
        batch_id = str(uuid.uuid4())
        repo.create_batch(batch_id, 1, [])
        repo.create_session(session_id, app_data, fields, 80.0, "needs_review", "2026-01-01T00:00:00Z", batch_id=batch_id)

        session = repo.get_session(session_id)
        assert session["batch_id"] == batch_id


class TestGetSessionFields:
    def test_returns_fields(self, repo, session_id, app_data, fields):
        repo.create_session(session_id, app_data, fields, 95.0, "pass", "2026-01-01T00:00:00Z")

        result = repo.get_session_fields(session_id)
        assert len(result) == 2
        names = {f["field_name"] for f in result}
        assert names == {"brand_name", "alcohol_content"}

    def test_empty_for_nonexistent(self, repo):
        assert repo.get_session_fields("nonexistent") == []


class TestSessionExists:
    def test_exists(self, repo, session_id, app_data, fields):
        repo.create_session(session_id, app_data, fields, 95.0, "pass", "2026-01-01T00:00:00Z")
        assert repo.session_exists(session_id) is True

    def test_not_exists(self, repo):
        assert repo.session_exists("nonexistent") is False


# ── Decision & Feedback ──────────────────────────────────────────


class TestUpdateDecision:
    def test_update(self, repo, session_id, app_data, fields):
        repo.create_session(session_id, app_data, fields, 95.0, "pass", "2026-01-01T00:00:00Z")
        repo.update_decision(session_id, "approved", "Looks good")

        session = repo.get_session(session_id)
        assert session["agent_decision"] == "approved"
        assert session["agent_notes"] == "Looks good"


class TestUpdateFeedback:
    def test_update(self, repo, session_id, app_data, fields):
        repo.create_session(session_id, app_data, fields, 95.0, "pass", "2026-01-01T00:00:00Z")
        repo.update_feedback(session_id, ai_correct=True, field_name="brand_name", note="Correct extraction")

        session = repo.get_session(session_id)
        assert session["ai_correct"] == 1


# ── Field operations ─────────────────────────────────────────────


class TestOverrideField:
    def test_override(self, repo, session_id, app_data, fields):
        repo.create_session(session_id, app_data, fields, 95.0, "pass", "2026-01-01T00:00:00Z")
        repo.override_field(session_id, "brand_name", "match", "Agent confirmed")

        result = repo.get_session_fields(session_id)
        brand = next(f for f in result if f["field_name"] == "brand_name")
        assert brand["override_status"] == "match"
        assert brand["override_note"] == "Agent confirmed"


class TestReviewField:
    def test_review_existing(self, repo, session_id, app_data, fields):
        repo.create_session(session_id, app_data, fields, 95.0, "pass", "2026-01-01T00:00:00Z")
        assert repo.review_field(session_id, "brand_name") is True

        result = repo.get_session_fields(session_id)
        brand = next(f for f in result if f["field_name"] == "brand_name")
        assert brand["reviewed"] == 1

    def test_review_nonexistent(self, repo, session_id, app_data, fields):
        repo.create_session(session_id, app_data, fields, 95.0, "pass", "2026-01-01T00:00:00Z")
        assert repo.review_field(session_id, "nonexistent_field") is False


# ── History / listing ────────────────────────────────────────────


class TestListVerifications:
    def _create_sessions(self, repo, app_data, fields):
        """Create 3 sessions with different statuses."""
        for i, (status, conf) in enumerate([("pass", 95.0), ("fail", 40.0), ("needs_review", 75.0)]):
            sid = str(uuid.uuid4())
            repo.create_session(sid, app_data, fields, conf, status, f"2026-01-0{i+1}T00:00:00Z")

    def test_list_all(self, repo, app_data, fields):
        self._create_sessions(repo, app_data, fields)
        items, total = repo.list_verifications()
        assert total == 3
        assert len(items) == 3

    def test_filter_by_status(self, repo, app_data, fields):
        self._create_sessions(repo, app_data, fields)
        items, total = repo.list_verifications(status="pass")
        assert total == 1
        assert items[0]["status"] == "pass"

    def test_filter_by_brand(self, repo, app_data, fields):
        self._create_sessions(repo, app_data, fields)
        items, total = repo.list_verifications(brand="HOWLING")
        assert total == 3

        items, total = repo.list_verifications(brand="NONEXISTENT")
        assert total == 0

    def test_pagination(self, repo, app_data, fields):
        self._create_sessions(repo, app_data, fields)
        items, total = repo.list_verifications(per_page=2, page=1)
        assert total == 3
        assert len(items) == 2

        items2, _ = repo.list_verifications(per_page=2, page=2)
        assert len(items2) == 1


# ── Batch operations ─────────────────────────────────────────────


@pytest.fixture
def batch_id():
    return str(uuid.uuid4())


class TestBatchCRUD:
    def test_create_and_get(self, repo, batch_id):
        repo.create_batch(batch_id, 5, [("bad.pdf", "Empty file")])

        batch = repo.get_batch(batch_id)
        assert batch is not None
        assert batch["id"] == batch_id
        assert batch["total_items"] == 5
        assert batch["status"] == "processing"

    def test_get_nonexistent(self, repo):
        assert repo.get_batch("nonexistent") is None

    def test_skipped_items(self, repo, batch_id):
        skipped = [("a.pdf", "Empty"), ("b.pdf", "Not a PDF")]
        repo.create_batch(batch_id, 3, skipped)

        result = repo.get_batch_skipped(batch_id)
        assert len(result) == 2
        assert result[0]["filename"] == "a.pdf"
        assert result[1]["reason"] == "Not a PDF"


class TestBatchCounters:
    def test_increment_completed(self, repo, batch_id):
        repo.create_batch(batch_id, 3, [])
        repo.increment_batch_completed(batch_id)
        repo.increment_batch_completed(batch_id)

        batch = repo.get_batch(batch_id)
        assert batch["completed_items"] == 2

    def test_increment_failed(self, repo, batch_id):
        repo.create_batch(batch_id, 3, [])
        repo.increment_batch_failed(batch_id)

        batch = repo.get_batch(batch_id)
        assert batch["failed_items"] == 1


class TestFinalizeBatch:
    def test_finalize_completed(self, repo, batch_id):
        repo.create_batch(batch_id, 2, [])
        repo.increment_batch_completed(batch_id)
        repo.increment_batch_completed(batch_id)
        repo.finalize_batch(batch_id)

        batch = repo.get_batch(batch_id)
        assert batch["status"] == "completed"

    def test_finalize_all_failed(self, repo, batch_id):
        repo.create_batch(batch_id, 2, [])
        repo.increment_batch_failed(batch_id)
        repo.increment_batch_failed(batch_id)
        repo.finalize_batch(batch_id)

        batch = repo.get_batch(batch_id)
        assert batch["status"] == "failed"

    def test_finalize_partial_failure(self, repo, batch_id):
        repo.create_batch(batch_id, 3, [])
        repo.increment_batch_completed(batch_id)
        repo.increment_batch_failed(batch_id)
        repo.finalize_batch(batch_id)

        batch = repo.get_batch(batch_id)
        assert batch["status"] == "completed"


class TestGetBatchSessions:
    def test_returns_sessions(self, repo, batch_id, app_data, fields):
        repo.create_batch(batch_id, 2, [])
        sid1 = str(uuid.uuid4())
        sid2 = str(uuid.uuid4())
        repo.create_session(sid1, app_data, fields, 95.0, "pass", "2026-01-01T00:00:00Z", batch_id=batch_id)
        repo.create_session(sid2, app_data, fields, 40.0, "fail", "2026-01-01T00:01:00Z", batch_id=batch_id)

        sessions = repo.get_batch_sessions(batch_id)
        assert len(sessions) == 2
        assert {s["id"] for s in sessions} == {sid1, sid2}

    def test_empty_for_no_sessions(self, repo, batch_id):
        repo.create_batch(batch_id, 0, [])
        assert repo.get_batch_sessions(batch_id) == []
