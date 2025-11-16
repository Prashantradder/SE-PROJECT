# blackout.py
from database import get_conn

def add_blackout(start_iso: str, end_iso: str, reason: str = "") -> int:
    """
    Add a blackout window (start and end are ISO strings).
    Returns blackout id.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO blackout_windows (start_dt, end_dt, reason)
        VALUES (?, ?, ?)
    """, (start_iso, end_iso, reason))
    conn.commit()
    return cur.lastrowid


def list_blackouts():
    """
    Return all blackout windows as rows.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, start_dt, end_dt, reason FROM blackout_windows ORDER BY start_dt DESC")
    return cur.fetchall()


def delete_blackout(bid: int):
    """
    Delete a blackout by id.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM blackout_windows WHERE id = ?", (bid,))
    conn.commit()
    return True


def check_conflict(start_iso: str, end_iso: str):
    """
    Returns blackout windows that overlap with [start_iso, end_iso].
    
    Overlap logic:
    NOT (existing.end < new.start OR existing.start > new.end)
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, start_dt, end_dt, reason
        FROM blackout_windows
        WHERE NOT (end_dt < ? OR start_dt > ?)
    """, (start_iso, end_iso))
    return cur.fetchall()
