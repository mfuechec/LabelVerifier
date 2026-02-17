"""Tests for database setup and migrations."""

import pytest
import sqlite3

from app.db.setup import create_tables, _migrate


class TestCreateTables:
    def test_creates_all_tables(self, db_conn):
        """All required tables should exist after create_tables."""
        tables = {
            row[0]
            for row in db_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "verification_sessions" in tables
        assert "applications" in tables
        assert "comparison_results" in tables
        assert "batches" in tables
        assert "batch_skipped_items" in tables
        assert "agent_feedback" in tables

    def test_idempotent(self, db_conn):
        """Calling create_tables twice should not fail."""
        create_tables(db_conn)
        create_tables(db_conn)

    def test_applications_has_cola_columns(self, db_conn):
        """Applications table should have fanciful_name, ttb_id, source_of_product."""
        columns = {
            row[1]
            for row in db_conn.execute("PRAGMA table_info(applications)").fetchall()
        }
        assert "fanciful_name" in columns
        assert "ttb_id" in columns
        assert "source_of_product" in columns

    def test_sessions_has_batch_id(self, db_conn):
        columns = {
            row[1]
            for row in db_conn.execute("PRAGMA table_info(verification_sessions)").fetchall()
        }
        assert "batch_id" in columns


class TestMigration:
    def test_migrate_adds_missing_columns(self, tmp_db):
        """Migration should add new columns to existing tables."""
        conn = sqlite3.connect(tmp_db)
        conn.row_factory = sqlite3.Row

        # Create tables without new columns (simulating old schema)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS batches (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'pending',
                total_items INTEGER NOT NULL,
                completed_items INTEGER NOT NULL DEFAULT 0,
                failed_items INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS verification_sessions (
                id TEXT PRIMARY KEY,
                application_id TEXT,
                beverage_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                overall_confidence REAL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS applications (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                brand_name TEXT,
                class_type TEXT
            );
        """)
        conn.commit()

        _migrate(conn)

        # Check new columns were added
        session_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(verification_sessions)").fetchall()
        }
        assert "batch_id" in session_cols

        app_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(applications)").fetchall()
        }
        assert "fanciful_name" in app_cols
        assert "ttb_id" in app_cols
        assert "source_of_product" in app_cols

        conn.close()
