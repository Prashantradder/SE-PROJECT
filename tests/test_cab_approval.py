from auth import create_user
from change_requests import submit_change
from cab_approval import record_approval
from database import get_conn


def test_cab_approval_accept(test_conn):
    # Setup: create user + submit a change
    create_user("cab1", "pass", "cab")

    cid = submit_change(
        "CAB Test",
        "desc",
        "Normal",
        None,
        "2025-01-01T10:00:00",
        "2025-01-01T11:00:00",
        "cab1",
        q1="No", q2="No", q3="No", q4="No"
    )

    # CAB approves
    record_approval(cid, "cab1", "Approve", "ok")

    conn = get_conn()
    cur = conn.cursor()

    # Check cab_approvals table
    cur.execute("SELECT * FROM cab_approvals WHERE change_id=?", (cid,))
    row = cur.fetchone()
    assert row is not None
    assert row["decision"] == "Approve"

    # Workflow should update to "Approved"
    cur.execute("SELECT workflow_status FROM change_requests WHERE change_id=?", (cid,))
    status = cur.fetchone()["workflow_status"]
    assert status == "Approved"


def test_cab_approval_reject(test_conn):
    create_user("cab2", "pass", "cab")

    cid = submit_change(
        "CAB Reject Test",
        "desc",
        "Normal",
        None,
        "2025-02-01T10:00:00",
        "2025-02-01T11:00:00",
        "cab2",
        q1="No", q2="No", q3="No", q4="No"
    )

    # CAB rejects the change
    record_approval(cid, "cab2", "Reject", "bad change")

    conn = get_conn()
    cur = conn.cursor()

    # Check approval stored
    cur.execute("SELECT decision FROM cab_approvals WHERE change_id=?", (cid,))
    decision = cur.fetchone()["decision"]
    assert decision == "Reject"

    # Workflow must be "Rejected"
    cur.execute("SELECT workflow_status FROM change_requests WHERE change_id=?", (cid,))
    status = cur.fetchone()["workflow_status"]
    assert status == "Rejected"
