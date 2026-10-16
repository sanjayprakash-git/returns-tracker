"""Staff sign-in: salted PBKDF2 password hashes (no plain-text passwords stored)."""
import hashlib
import hmac
import secrets

ITERATIONS = 200_000

# Demo accounts shown on the sign-in page of the public demo
DEMO_LOGINS = [("mei", "manager-demo", "Manager"), ("ciaran", "tech-demo", "Technician"), ("aoife", "sales-demo", "Sales")]


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
