from auth import create_user, authenticate

def test_user_creation_and_auth(test_conn):
    create_user("testuser", "password", "admin")

    ok, role = authenticate("testuser", "password")
    assert ok is True
    assert role == "admin"
