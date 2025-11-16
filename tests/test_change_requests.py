from change_requests import submit_change

def test_submit_change(test_conn):
    cid = submit_change(
        title="Unit Test Change",
        description="testing",
        category="Normal",
        ci_id=None,
        start="2025-01-01T10:00:00",
        end="2025-01-01T11:00:00",
        created_by="tester",
        q1="No", q2="No", q3="No", q4="No"
    )
    assert cid.startswith("CHG-")
