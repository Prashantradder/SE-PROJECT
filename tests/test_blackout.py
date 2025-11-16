from blackout import add_blackout, check_conflict

def test_blackout_conflict(test_conn):
    add_blackout("2025-01-01T10:00:00", "2025-01-01T12:00:00", "maintenance")

    conflicts = check_conflict("2025-01-01T11:00:00", "2025-01-01T13:00:00")
    assert len(conflicts) == 1
