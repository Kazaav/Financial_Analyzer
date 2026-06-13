from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from dataclasses import dataclass
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from . import db
from .passwords import hash_password, verify_password  # noqa: F401 (re-exported)
from .settings import COOKIE_SECURE, SESSION_MAX_AGE_SECONDS

SESSION_COOKIE = "financial_analyzer_session"
# Users now live in SQLite (app.db). FINANCIAL_ANALYZER_USERS is only read once,
# at first run, to seed the admin into an empty DB (see bootstrap_users).
DEFAULT_USERS = ""
SESSION_SECRET = os.getenv("FINANCIAL_ANALYZER_SESSION_SECRET")
if not SESSION_SECRET:
    logging.getLogger("financial_analyzer").warning(
        "FINANCIAL_ANALYZER_SESSION_SECRET is unset; using an ephemeral secret. "
        "Sessions will not survive a restart — set it in production."
    )
    SESSION_SECRET = secrets.token_urlsafe(48)


@dataclass(frozen=True)
class User:
    username: str
    role: str
    password_hash: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def _row_to_user(row) -> User:
    return User(username=row["username"], role=row["role"], password_hash=row["password_hash"])


def parse_users() -> dict[str, User]:
    """Parse the legacy FINANCIAL_ANALYZER_USERS env var (used only by bootstrap)."""
    raw = os.getenv("FINANCIAL_ANALYZER_USERS", DEFAULT_USERS)
    users: dict[str, User] = {}
    for item in raw.split(";"):
        item = item.strip()
        if not item:
            continue
        parts = item.split(":", 2)
        if len(parts) != 3:
            continue
        username, role, password_hash = parts
        users[username] = User(username=username, role=role or "user", password_hash=password_hash)
    return users


def bootstrap_users() -> None:
    """First-run seed: if the users table is empty, import the env-defined users
    so the existing admin keeps working. Idempotent — only acts on an empty table."""
    try:
        if db.count_users() > 0:
            return
        for u in parse_users().values():
            try:
                db.create_user(u.username, u.password_hash, role=u.role)
            except ValueError:
                pass
    except Exception:  # pragma: no cover - never block startup on bootstrap
        logging.getLogger("financial_analyzer").exception("bootstrap_users failed")


def authenticate(username: str, password: str) -> User | None:
    row = db.authenticate(username, password)
    return _row_to_user(row) if row else None


def _sign(payload: str) -> str:
    return hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def make_session_value(user: User) -> str:
    expires = int(time.time() + SESSION_MAX_AGE_SECONDS)
    payload = f"{user.username}|{user.role}|{expires}"
    return f"{payload}|{_sign(payload)}"


def read_session_user(request: Request) -> User | None:
    value = request.cookies.get(SESSION_COOKIE, "")
    parts = value.split("|")
    if len(parts) != 4:
        return None
    username, role, expires, signature = parts
    payload = f"{username}|{role}|{expires}"
    if not hmac.compare_digest(_sign(payload), signature):
        return None
    try:
        if int(expires) < int(time.time()):
            return None
    except ValueError:
        return None
    # Re-load from the DB every request: the cookie's role is NOT trusted, and a
    # disabled/deleted account loses access immediately.
    row = db.get_user_by_name(username)
    if not row or row["status"] != "active":
        return None
    return _row_to_user(row)


def set_login_cookie(response: Response, user: User) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        make_session_value(user),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
    )


def clear_login_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)


def login_redirect(request: Request) -> RedirectResponse:
    target = quote(str(request.url.path) + (f"?{request.url.query}" if request.url.query else ""))
    return RedirectResponse(url=f"/login?next={target}", status_code=303)


def current_user(request: Request) -> User:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="ログインが必要です。")
    return user


def require_admin(request: Request) -> User:
    user = getattr(request.state, "user", None)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="管理者権限が必要です。")
    return user


# ── CSRF ─────────────────────────────────────────────────────────────────
# Stateless token bound to the (httponly, signed) session cookie. A cross-site
# attacker cannot read the cookie, so cannot forge a matching token.
def make_csrf_token(request: Request) -> str:
    sess = request.cookies.get(SESSION_COOKIE, "")
    return hmac.new(SESSION_SECRET.encode(), ("csrf:" + sess).encode(), hashlib.sha256).hexdigest()


def verify_csrf(request: Request, token: str) -> bool:
    return bool(token) and hmac.compare_digest(make_csrf_token(request), token)
