import datetime
from database import get_conn
from utils import log_audit


def check_sla_for_change_row(row):
    """
    Returns:
        None  => SLA OK
        float => overdue hours
    """

    status = row.get("workflow_status")
    deadline = row.get("sla_deadline")
    last_change = row.get("last_status_change")

    # Do not enforce SLA for completed items
    if status in ("Approved", "Rejected"):
        return None

    if not deadline or not last_change:
        return None

    try:
        deadline_dt = datetime.datetime.fromisoformat(deadline)
    except:
        return None

    now = datetime.datetime.now()
    if now <= deadline_dt:
        return None

    # SLA breached
    overdue = (now - deadline_dt).total_seconds() / 3600
    return round(overdue, 2)


def escalate_sla_breach(change_id):
    """
    Writes an audit log entry when SLA is breached.
    """
    try:
        log_audit("system", "sla_breached", change_id)
    except Exception:
        pass
