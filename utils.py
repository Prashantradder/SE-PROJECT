# utils.py
import sqlite3
from database import get_conn
import datetime

def generate_change_id():
    # basic change id: CHG-YYYYMMDD-HHMMSS-<seq>
    now = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM change_requests")
    seq = cur.fetchone()["c"] + 1
    return f"CHG-{now}-{seq}"

def log_audit(username, action, metadata=""):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO audit_logs (username, action, metadata) VALUES (?, ?, ?)",
                (username, action, metadata))
    conn.commit()
