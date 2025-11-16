# change_requests.py
from database import get_conn
from utils import generate_change_id, log_audit
import datetime

def submit_change(title, description, category, ci_id, start, end, created_by,
                  q1, q2, q3, q4):
    """
    Inserts a new change request with questionnaire-based risk scoring.
    """
    conn = get_conn()
    cur = conn.cursor()
    change_id = generate_change_id()

    risk = calculate_risk(category, description, q1, q2, q3, q4)

    workflow_status = "Draft" if (category or "").strip().lower() == "standard" else "Pending CAB"
    sla_deadline = calculate_sla_deadline(category)
    now = datetime.datetime.now().isoformat()

    cur.execute("""
      INSERT INTO change_requests
      (change_id, title, description, category, ci_id,
       scheduled_start, scheduled_end, risk_score,
       workflow_status, created_by, sla_deadline, last_status_change)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        change_id, title, description, category, ci_id,
        start, end, risk,
        workflow_status, created_by, sla_deadline, now
    ))

    conn.commit()
    log_audit(created_by, "submit_change", change_id)
    return change_id


def calculate_risk(category, description, q1, q2, q3, q4):
    # Base from category
    base = {"emergency": 8, "normal": 5, "standard": 2}.get((category or "").lower(), 4)

    # Keyword score
    keywords = ["database", "downtime", "kernel", "root", "reboot"]
    keyword_score = sum(2 for k in keywords if k in (description or "").lower())

    # Questionnaire scores
    qscore = 0
    if q1 == "Yes": qscore += 3    # production impact
    if q2 == "Yes": qscore += 2    # no rollback
    if q3 == "Yes": qscore += 2    # critical CI
    if q4 == "Yes": qscore += 3    # customer impact

    total = base + keyword_score + qscore
    return min(10, total)


def calculate_sla_deadline(category):
    now = datetime.datetime.now()
    if (category or "").lower() == "emergency":
        return (now + datetime.timedelta(hours=6)).isoformat()
    elif (category or "").lower() == "normal":
        return (now + datetime.timedelta(days=2)).isoformat()
    else:
        return (now + datetime.timedelta(days=7)).isoformat()


def list_changes(filter_by=None):
    conn = get_conn()
    cur = conn.cursor()
    q = "SELECT cr.*, c.name as ci_name FROM change_requests cr LEFT JOIN cis c ON cr.ci_id = c.id"
    if filter_by:
        q += " WHERE " + filter_by
    cur.execute(q)
    return cur.fetchall()


def get_change(change_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM change_requests WHERE change_id = ?", (change_id,))
    return cur.fetchone()


def update_workflow_status(change_id, new_status):
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.datetime.now().isoformat()
    cur.execute("""
      UPDATE change_requests
      SET workflow_status = ?, last_status_change = ?
      WHERE change_id = ?
    """, (new_status, now, change_id))
    conn.commit()
    log_audit("system", f"update_status:{new_status}", change_id)
    return True
