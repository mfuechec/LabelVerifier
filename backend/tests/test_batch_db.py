import sqlite3
import pytest
from app.db.setup import get_db, create_tables


def test_batches_table_exists(tmp_db):
    conn = get_db(tmp_db)
    create_tables(conn)

    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    ]
    assert "batches" in tables
    conn.close()


def test_batch_insert_and_query(tmp_db):
    conn = get_db(tmp_db)
    create_tables(conn)

    conn.execute(
        """INSERT INTO batches (id, status, total_items, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        ("batch-1", "pending", 3, "2026-02-15T10:00:00Z", "2026-02-15T10:00:00Z"),
    )
    conn.commit()

    row = conn.execute("SELECT * FROM batches WHERE id = ?", ("batch-1",)).fetchone()
    assert row["id"] == "batch-1"
    assert row["status"] == "pending"
    assert row["total_items"] == 3
    assert row["completed_items"] == 0
    assert row["failed_items"] == 0
    conn.close()


def test_session_batch_id_fk(tmp_db):
    conn = get_db(tmp_db)
    create_tables(conn)

    # Insert a batch first
    conn.execute(
        """INSERT INTO batches (id, status, total_items, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        ("batch-1", "pending", 1, "2026-02-15T10:00:00Z", "2026-02-15T10:00:00Z"),
    )

    # Insert session linked to batch
    conn.execute(
        """INSERT INTO verification_sessions
           (id, beverage_type, status, created_at, updated_at, batch_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("sess-1", "distilled_spirits", "pending",
         "2026-02-15T10:00:00Z", "2026-02-15T10:00:00Z", "batch-1"),
    )
    conn.commit()

    row = conn.execute(
        "SELECT batch_id FROM verification_sessions WHERE id = ?", ("sess-1",)
    ).fetchone()
    assert row["batch_id"] == "batch-1"
    conn.close()


def test_session_batch_id_nullable(tmp_db):
    conn = get_db(tmp_db)
    create_tables(conn)

    conn.execute(
        """INSERT INTO verification_sessions
           (id, beverage_type, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        ("sess-2", "wine", "pending",
         "2026-02-15T10:00:00Z", "2026-02-15T10:00:00Z"),
    )
    conn.commit()

    row = conn.execute(
        "SELECT batch_id FROM verification_sessions WHERE id = ?", ("sess-2",)
    ).fetchone()
    assert row["batch_id"] is None
    conn.close()


def test_session_batch_id_fk_enforcement(tmp_db):
    conn = get_db(tmp_db)
    create_tables(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """INSERT INTO verification_sessions
               (id, beverage_type, status, created_at, updated_at, batch_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("sess-3", "beer", "pending",
             "2026-02-15T10:00:00Z", "2026-02-15T10:00:00Z", "nonexistent-batch"),
        )
    conn.close()


def test_batch_index_exists(tmp_db):
    conn = get_db(tmp_db)
    create_tables(conn)

    indexes = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        ).fetchall()
    ]
    assert "idx_sessions_batch" in indexes
    conn.close()
