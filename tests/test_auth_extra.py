from auth import ensure_admin_exists, generate_otp, authenticate

def test_generate_otp():
    otp, expiry = generate_otp()
    assert len(str(otp)) == 6
    assert expiry > 0


def test_ensure_admin_exists(test_conn):
    ensure_admin_exists()
    ok, role = authenticate("admin", "admin")
    assert ok is True
    assert role == "admin"
