from auth import create_user
from change_requests import submit_change
from blackout import add_blackout, check_conflict

def test_end_to_end_change_workflow(test_conn):
    create_user("admin", "pass", "admin")

    cid = submit_change(
        "Integration Change", "desc", "Normal",
        None,
        "2025-01-01T10:00:00",
        "2025-01-01T11:00:00",
        "admin",
        "No","No","No","No"
    )
    assert cid.startswith("CHG")

    # Add blackout and check conflict
    add_blackout("2025-01-01T09:00:00", "2025-01-01T12:00:00", "block")
    conflicts = check_conflict("2025-01-01T10:30:00", "2025-01-01T10:45:00")
    assert len(conflicts) == 1
