from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from .settings import COOKIE_SECURE, SESSION_MAX_AGE_SECONDS


SESSION_COOKIE = "financial_analyzer_session"
DEFAULT_USERS = (
    "zekkx:admin:pbkdf2_sha256$260000$DgpWnsn44Eot6gOuFXVS6g$Yg4J63AmftT9OrHM2uv_AKjvtkg3UCzm9mwzixDafto;"
    "guest001:guest:pbkdf2_sha256$260000$dxjHe-Rt_ouv-WNbwDwbvg$kKYvvUclYME2TZXmGVnbwTyNYwbaYkh18V2Ns9j2VCg"
)
SESSION_SECRET = os.getenv("FINANCIAL_ANALYZER_SESSION_SECRET") or secrets.token_urlsafe(48)


@dataclass(frozen=True)
class User:
    username: str
    role: str
    password_hash: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def parse_users() -> dict[str, User]:
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
        users[username] = User(username=username, role=role or "guest", password_hash=password_hash)
    return users


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash.startswith("pbkdf2_sha256$"):
        return False
    try:
        _, iterations, salt, expected = password_hash.split("$", 3)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(_b64(digest), expected)


def authenticate(username: str, password: str) -> User | None:
    user = parse_users().get(username)
    if not user or not verify_password(password, user.password_hash):
        return None
    return user


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
    user = parse_users().get(username)
    if not user or user.role != role:
        return None
    return user


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


def require_admin(request: Request) -> User:
    user = getattr(request.state, "user", None)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="管理者権限が必要です。")
    return user
