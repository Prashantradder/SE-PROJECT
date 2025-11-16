# auth.py
import bcrypt
from database import get_conn
import sqlite3
import pyotp
import time


LOCK_THRESHOLD = 5

def hash_password(password: str) -> bytes:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())

def check_password(password: str, hashed: bytes) -> bool:
    return bcrypt.checkpw(password.encode(), hashed)

def create_user(username: str, password: str, role: str):
    conn = get_conn()
    cur = conn.cursor()
    pwd = hash_password(password)
    try:
        cur.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                    (username, pwd, role))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def authenticate(username: str, password: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    if not row:
        return False, "User not found"

    if row["locked"]:
        return False, "Account locked due to multiple failed attempts"

    stored = row["password_hash"]
    if isinstance(stored, str):
        stored = stored.encode('latin1')  # fallback

    if check_password(password, stored):
        # reset failed attempts
        cur.execute("UPDATE users SET failed_attempts = 0 WHERE username = ?", (username,))
        conn.commit()
        return True, row["role"]
    else:
        failed = row["failed_attempts"] + 1
        locked = 1 if failed >= LOCK_THRESHOLD else 0
        cur.execute("UPDATE users SET failed_attempts = ?, locked = ? WHERE username = ?",
                    (failed, locked, username))
        conn.commit()
        if locked:
            return False, "Account locked after too many failed attempts"
        return False, f"Invalid credentials ({failed} failed)"

def ensure_admin_exists():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT * FROM users WHERE username=?", ("admin",))
    row = cur.fetchone()

    if row is None:
        pwd = hash_password("admin")
        cur.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("admin", pwd, "admin"),
        )
        conn.commit()


def generate_otp():
    # Generate a 30-second time-based OTP
    secret = "JBSWY3DPEHPK3PXP"  # Hardcoded secret for demo
    totp = pyotp.TOTP(secret, interval=30)
    otp = totp.now()
    expiry = int(time.time()) + 30
    return otp, expiry
