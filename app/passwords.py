"""Password hashing helpers (pbkdf2_sha256). Stdlib only.

Kept in its own module so both app.auth and app.db can import it without a
circular dependency. Hash format (unchanged, back-compatible with the old
env-var users):  pbkdf2_sha256$<iterations>$<salt_b64>$<digest_b64>
The salt is stored as a urlsafe-base64 (no padding) string and is fed to
pbkdf2 as that string's UTF-8 bytes — verify_password and hash_password must
agree on this so existing env hashes keep verifying.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

PBKDF2_ITERATIONS = 260000


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def hash_password(password: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = _b64(secrets.token_bytes(16))
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${_b64(digest)}"


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash.startswith("pbkdf2_sha256$"):
        return False
    try:
        _, iterations, salt, expected = password_hash.split("$", 3)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(_b64(digest), expected)
