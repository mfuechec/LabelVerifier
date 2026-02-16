import os

# Must be set before any app imports so create_app() skips config validation
os.environ["TESTING"] = "1"

import tempfile
from pathlib import Path

import pytest
import sqlite3

from app.models.schemas import ApplicationData


FIXTURES_DIR = Path(__file__).parent / "fixtures"
COLA_PDFS_DIR = FIXTURES_DIR / "cola_pdfs"


@pytest.fixture
def tmp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def db_conn(tmp_db):
    """Create a database connection with tables created."""
    from app.db.setup import create_tables

    conn = sqlite3.connect(tmp_db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_tables(conn)
    yield conn
    conn.close()


@pytest.fixture
def sample_application_data() -> ApplicationData:
    """A typical domestic spirits application."""
    return ApplicationData(
        ttb_id="12175001000069",
        brand_name="HOWLING MOON",
        fanciful_name="MIDNIGHT MOONSHINE",
        class_type="OTHER SPECIALTIES & PROPRIETARIES",
        alcohol_content="50",
        net_contents="750 MILLILITERS",
        producer_name="HOWLING MOON, THE COPPER STILL LLC",
        producer_address="123 MAIN ST, ASHEVILLE NC 28801",
        beverage_type="distilled_spirits",
        source_of_product="domestic",
    )


@pytest.fixture
def sample_imported_application() -> ApplicationData:
    """A typical imported spirits application."""
    return ApplicationData(
        ttb_id="11115001000373",
        brand_name="BARENJAGER",
        fanciful_name="HONEY & BOURBON",
        class_type="OTHER SPECIALTIES & PROPRIETARIES",
        alcohol_content="35",
        net_contents="750 MILLILITERS\n1 LITER",
        importer_name="SIDNEY FRANK IMPORTING CO., INC.",
        importer_address="20 CEDAR ST, NEW ROCHELLE NY 10801",
        beverage_type="distilled_spirits",
        source_of_product="imported",
    )


@pytest.fixture
def sample_wine_application() -> ApplicationData:
    """A typical domestic wine application."""
    return ApplicationData(
        ttb_id="03235001000006",
        brand_name="CASCADE WINERY",
        class_type="TABLE RED WINE",
        alcohol_content="11.5",
        net_contents="750 MILLILITERS",
        producer_name="CASCADE WINERY, CASCADE WINERY, INC.",
        producer_address="6275 28TH ST, GRAND RAPIDS MI 49546",
        beverage_type="wine",
        source_of_product="domestic",
    )


def load_cola_pdf(name: str) -> bytes:
    """Load a COLA PDF fixture by filename."""
    path = COLA_PDFS_DIR / name
    if not path.exists():
        pytest.skip(f"COLA PDF fixture not found: {name}")
    return path.read_bytes()
