# cab_approval.py
from database import get_conn
from utils import log_audit
import datetime
from change_requests import update_workflow_status
from sla_engine import escalate_sla_breach

def record_approval(change_id, approver, decision, comments=""):
    """
    Record a CAB approval/rejection. Update the workflow status accordingly.
    Simple rules:
      - If decision == 'Reject' -> set status to 'Rejected'
      - If decision == 'Approve' -> set status to 'Approved'
    After status update, last_status_change is updated in update_workflow_status.
    """
    conn = get_conn()
    cur = conn.cursor()
    decided_at = datetime.datetime.now().isoformat()

    cur.execute("""
      INSERT INTO cab_approvals (change_id, approver, decision, comments, decided_at)
      VALUES (?, ?, ?, ?, ?)
    """, (change_id, approver, decision, comments, decided_at))
    conn.commit()

    # update workflow status
    if decision == "Reject":
        update_workflow_status(change_id, "Rejected")
    else:
        # Approve -> Approved
        update_workflow_status(change_id, "Approved")

    log_audit(approver, f"cab_{decision.lower()}", change_id)

    # after updating status, ensure SLA logic: if new stage has SLA, timestamp is set
    # Also check if any existing SLA was breached previously and escalate if necessary
    # (This is optional — you can call sla_engine.check_sla_for_change externally to review)
    try:
        # If there was an outstanding SLA breach for this change, clear/escalate as needed.
        # For now we won't reverse escalations automatically. But attempt to escalate if breached:
        from sla_engine import check_sla_for_change_row
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM change_requests WHERE change_id = ?", (change_id,))
        row = cur.fetchone()
        overdue = check_sla_for_change_row(row)
        if overdue is not None:
            # escalate by marking SLA Breached (idempotent)
            escalate_sla_breach(change_id)
    except Exception:
        pass
