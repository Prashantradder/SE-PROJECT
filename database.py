# database.py
import sqlite3
from pathlib import Path
import datetime

DB_PATH = Path(__file__).parent / "data" / "change_management.db"

def get_conn():
    # Always treat DB_PATH as a Path object
    p = Path(DB_PATH)

    # Ensure folder exists
    p.parent.mkdir(exist_ok=True, parents=True)

    conn = sqlite3.connect(p, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # users
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash BLOB NOT NULL,
        role TEXT NOT NULL,
        failed_attempts INTEGER DEFAULT 0,
        locked INTEGER DEFAULT 0
    )
    """)

    # cis
    cur.execute("""
    CREATE TABLE IF NOT EXISTS cis (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    )
    """)

    # dependencies
    cur.execute("""
    CREATE TABLE IF NOT EXISTS dependencies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ci_from INTEGER NOT NULL,
        ci_to INTEGER NOT NULL,
        FOREIGN KEY(ci_from) REFERENCES cis(id),
        FOREIGN KEY(ci_to) REFERENCES cis(id)
    )
    """)

    # blackout windows (admin-managed)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS blackout_windows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        start_dt TEXT NOT NULL,   -- ISO timestamp
        end_dt TEXT NOT NULL,     -- ISO timestamp
        reason TEXT
    )
    """)

    # change_requests -- include last_status_change column
    cur.execute("""
    CREATE TABLE IF NOT EXISTS change_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        change_id TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        category TEXT,
        ci_id INTEGER,
        scheduled_start TEXT,
        scheduled_end TEXT,
        risk_score INTEGER,
        workflow_status TEXT,
        created_by TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        sla_deadline TEXT,
        last_status_change TEXT,
        FOREIGN KEY(ci_id) REFERENCES cis(id)
    )
    """)

    # cab_approvals
    cur.execute("""
    CREATE TABLE IF NOT EXISTS cab_approvals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        change_id TEXT NOT NULL,
        approver TEXT NOT NULL,
        decision TEXT,
        comments TEXT,
        decided_at TEXT,
        FOREIGN KEY(change_id) REFERENCES change_requests(change_id)
    )
    """)

    # audit_logs
    cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        action TEXT,
        metadata TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()

    # Migration safety: attempt to add column last_status_change if missing (no-op if exists)
    try:
        cur.execute("PRAGMA table_info(change_requests)")
        cols = [r[1] for r in cur.fetchall()]
        if "last_status_change" not in cols:
            cur.execute("ALTER TABLE change_requests ADD COLUMN last_status_change TEXT")
            conn.commit()
    except Exception:
        pass

    # Migration safety: attempt to add blackout_windows if older DB lacks it (no-op)
    try:
        cur.execute("PRAGMA table_info(blackout_windows)")
        cols = [r[1] for r in cur.fetchall()]
        if not cols:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS blackout_windows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_dt TEXT NOT NULL,
                end_dt TEXT NOT NULL,
                reason TEXT
            )
            """)
            conn.commit()
    except Exception:
        pass

    return conn
