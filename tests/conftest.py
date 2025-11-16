import pytest
import sqlite3
import os
import sys

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from database import DB_PATH, init_db


@pytest.fixture
def test_conn(tmp_path, monkeypatch):
    # Point DB_PATH to a temporary test DB
    test_db = tmp_path / "test.db"
    monkeypatch.setattr("database.DB_PATH", test_db)

    # Initialize DB schema (creates tables)
    conn = init_db()

    yield conn
    conn.close()
