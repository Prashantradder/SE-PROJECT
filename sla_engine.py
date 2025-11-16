# sla_engine.py
import datetime
from database import get_conn

SLA_RULES = {
    "Draft": 24,
    "Pending CAB": 48,
    "Approved": 72
}

def safe_get(row, key, default=None):
    try:
        return row.get(key, default)
    except Exception:
        return default

def check_sla_for_change_row(row):
    stage = safe_get(row, "workflow_status")
    last_change = safe_get(row, "last_status_change")

    # If missing fields, skip SLA
    if not stage or not last_change:
        return None

    if stage not in SLA_RULES:
        return None

    try:
        last_dt = datetime.datetime.fromisoformat(last_change)
    except:
        return None

    now = datetime.datetime.now()
    hours_passed = (now - last_dt).total_seconds() / 3600
    allowed = SLA_RULES.get(stage, None)

    if allowed and hours_passed > allowed:
        return round(hours_passed - allowed, 2)
    return None

def escalate_sla_breach(change_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO audit_logs (change_id, action) VALUES (?, ?)",
        (change_id, "sla_escalation"),
    )
    conn.commit()

