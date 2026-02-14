import sqlite3
import pytest
from app.db.setup import get_db, create_tables


def test_create_tables(tmp_db):
    conn = get_db(tmp_db)
    create_tables(conn)

    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]

    assert "verification_sessions" in tables
    assert "applications" in tables
    assert "label_images" in tables
    assert "extracted_fields" in tables
    assert "comparison_results" in tables
    assert "agent_feedback" in tables
    conn.close()


def test_insert_and_query_session(tmp_db):
    conn = get_db(tmp_db)
    create_tables(conn)

    conn.execute(
        """INSERT INTO verification_sessions
           (id, beverage_type, status, overall_confidence, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("test-uuid-1", "distilled_spirits", "pending", None, "2026-02-14T10:00:00Z", "2026-02-14T10:00:00Z"),
    )
    conn.commit()

    row = conn.execute(
        "SELECT * FROM verification_sessions WHERE id = ?", ("test-uuid-1",)
    ).fetchone()

    assert row["id"] == "test-uuid-1"
    assert row["beverage_type"] == "distilled_spirits"
    assert row["status"] == "pending"
    conn.close()


def test_foreign_key_enforcement(tmp_db):
    conn = get_db(tmp_db)
    create_tables(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """INSERT INTO applications (id, session_id, brand_name)
               VALUES (?, ?, ?)""",
            ("app-1", "nonexistent-session", "Test Brand"),
        )
    conn.close()


def test_indexes_created(tmp_db):
    conn = get_db(tmp_db)
    create_tables(conn)

    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
    )
    indexes = [row[0] for row in cursor.fetchall()]

    assert "idx_sessions_status" in indexes
    assert "idx_sessions_beverage" in indexes
    assert "idx_sessions_created" in indexes
    conn.close()
