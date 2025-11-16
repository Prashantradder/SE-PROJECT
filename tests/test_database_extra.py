from database import init_db, get_conn

def test_init_db_creates_tables(tmp_path, monkeypatch):
    test_db = tmp_path / "test.db"
    monkeypatch.setattr("database.DB_PATH", str(test_db))

    conn = init_db()
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master")
    tables = [row["name"] for row in cur.fetchall()]

    assert "users" in tables
    assert "change_requests" in tables
    assert "blackout_windows" in tables
