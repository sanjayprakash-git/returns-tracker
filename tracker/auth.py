"""Staff sign-in: salted PBKDF2 password hashes (no plain-text passwords stored)."""
import hashlib
import os
import hmac
import secrets

ITERATIONS = 200_000

# Demo accounts: one-click "Try as…" buttons on the sign-in page when DEMO_MODE is on (passwords are never shown)
DEMO_LOGINS = [("sanjay", "manager-demo", "Manager"), ("karolina", "tech-demo", "Technician"),
               ("kariana", "sales-demo", "Sales")]
DEMO_MODE = os.environ.get("RETURNS_TRACKER_DEMO", "1") == "1"  # set to 0 for real shop use


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, digest = stored.split("$")
    except (ValueError, AttributeError):
        return False
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
    return hmac.compare_digest(check, digest)


def authenticate(conn, username: str, password: str):
    """Return {id, name, role} for valid credentials, else None."""
    row = conn.execute("SELECT id, name, role, password_hash FROM staff WHERE username = ?",
                       (username.strip().lower(),)).fetchone()
    if row and verify_password(password, row[3]):
        return {"id": row[0], "name": row[1], "role": row[2]}
    return None


def demo_user(conn, username: str):
    """Sign in as a demo account without a password — only when DEMO_MODE is on."""
    if not DEMO_MODE or username not in {u for u, _, _ in DEMO_LOGINS}:
        return None
    row = conn.execute("SELECT id, name, role FROM staff WHERE username = ?", (username,)).fetchone()
    return {"id": row[0], "name": row[1], "role": row[2]} if row else None
