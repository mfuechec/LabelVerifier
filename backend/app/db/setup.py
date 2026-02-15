import sqlite3


def get_db(db_path: str = "data/labelverify.db") -> sqlite3.Connection:
    """Get a database connection."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_tables(conn: sqlite3.Connection) -> None:
    """Create all database tables."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS verification_sessions (
            id TEXT PRIMARY KEY,
            application_id TEXT,
            beverage_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            overall_confidence REAL,
            agent_decision TEXT,
            agent_notes TEXT,
            ai_correct INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS applications (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES verification_sessions(id),
            brand_name TEXT,
            class_type TEXT,
            alcohol_content TEXT,
            net_contents TEXT,
            producer_name TEXT,
            producer_address TEXT,
            country_of_origin TEXT,
            importer_name TEXT,
            importer_address TEXT,
            has_sulfites_declaration INTEGER DEFAULT 0,
            raw_json TEXT
        );

        CREATE TABLE IF NOT EXISTS label_images (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES verification_sessions(id),
            panel_type TEXT NOT NULL,
            file_path TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            file_size INTEGER,
            annotated_path TEXT
        );

        CREATE TABLE IF NOT EXISTS extracted_fields (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES verification_sessions(id),
            image_id TEXT REFERENCES label_images(id),
            field_name TEXT NOT NULL,
            extracted_value TEXT,
            confidence REAL,
            bbox_x REAL,
            bbox_y REAL,
            bbox_width REAL,
            bbox_height REAL,
            panel_type TEXT
        );

        CREATE TABLE IF NOT EXISTS comparison_results (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES verification_sessions(id),
            field_name TEXT NOT NULL,
            declared_value TEXT,
            extracted_value TEXT,
            match_strategy TEXT NOT NULL,
            status TEXT NOT NULL,
            confidence REAL,
            override_status TEXT,
            override_note TEXT,
            reviewed INTEGER DEFAULT 0,
            extraction_confidence TEXT,
            confidence_reason TEXT
        );

        CREATE TABLE IF NOT EXISTS agent_feedback (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES verification_sessions(id),
            ai_correct INTEGER NOT NULL,
            field_name TEXT,
            note TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_sessions_status ON verification_sessions(status);
        CREATE INDEX IF NOT EXISTS idx_sessions_beverage ON verification_sessions(beverage_type);
        CREATE INDEX IF NOT EXISTS idx_sessions_created ON verification_sessions(created_at);
        CREATE INDEX IF NOT EXISTS idx_sessions_app_id ON verification_sessions(application_id);
        CREATE INDEX IF NOT EXISTS idx_applications_session ON applications(session_id);
        CREATE INDEX IF NOT EXISTS idx_images_session ON label_images(session_id);
        CREATE INDEX IF NOT EXISTS idx_extracted_session ON extracted_fields(session_id);
        CREATE INDEX IF NOT EXISTS idx_comparison_session ON comparison_results(session_id);
        CREATE INDEX IF NOT EXISTS idx_feedback_session ON agent_feedback(session_id);
    """)
    conn.commit()
