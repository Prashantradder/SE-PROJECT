from change_requests import submit_change, list_changes, get_change
from database import get_conn

def test_list_changes(test_conn):
    submit_change("A", "B", "Normal", None,
                  "2025-01-01T10:00:00", "2025-01-01T11:00:00",
                  "tester", q1="No", q2="No", q3="No", q4="No")

    rows = list_changes()
    assert len(rows) >= 1


def test_get_change(test_conn):
    cid = submit_change("A", "B", "Normal", None,
                  "2025-01-01T10:00:00", "2025-01-01T11:00:00",
                  "tester", q1="No", q2="No", q3="No", q4="No")

    row = get_change(cid)
    assert row is not None
    assert row["change_id"] == cid
