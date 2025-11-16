from blackout import add_blackout, list_blackouts, delete_blackout

def test_list_blackouts_empty(test_conn):
    assert list_blackouts() == []

def test_list_and_delete_blackout(test_conn):
    bid = add_blackout("2025-01-01T10:00:00", "2025-01-01T12:00:00", "test")
    rows = list_blackouts()
    assert len(rows) == 1

    delete_blackout(bid)
    assert list_blackouts() == []
