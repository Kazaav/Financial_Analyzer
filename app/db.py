"""SQLite store for users and invite codes. Stdlib only (sqlite3).

Lives at STORAGE_DIR/app.db (prod: /var/lib/financial-analyzer/app.db) so it
sits in the persistent data dir and survives file-overwrite deploys.

Concurrency: prod runs a single uvicorn worker, but FastAPI dispatches sync
work to a threadpool, so multiple threads may touch the DB. We use one shared
connection (check_same_thread=False) guarded by a module-level lock; every
helper runs under the lock and commits its own short transaction. WAL +
busy_timeout are extra safety. All helpers are SYNC — async callers wrap them
in run_in_threadpool (same pattern as parse_pdf).
"""
from __future__ import annotations

import secrets
import sqlite3
import threading
import time

from .passwords import verify_password
from .settings import STORAGE_DIR

DB_PATH = STORAGE_DIR / "app.db"

_LOCK = threading.Lock()
_conn: sqlite3.Connection | None = None


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        _conn = conn
    return _conn


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def init_db() -> None:
    with _LOCK:
        c = _connect()
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              username TEXT NOT NULL,
              username_ci TEXT NOT NULL,
              email TEXT NOT NULL DEFAULT '',
              display_name TEXT NOT NULL DEFAULT '',
              password_hash TEXT NOT NULL,
              role TEXT NOT NULL DEFAULT 'user',
              status TEXT NOT NULL DEFAULT 'active',
              created_at TEXT NOT NULL DEFAULT '',
              last_login_at TEXT NOT NULL DEFAULT ''
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_ci ON users(username_ci);
            CREATE TABLE IF NOT EXISTS invites (
              code TEXT PRIMARY KEY,
              role TEXT NOT NULL DEFAULT 'user',
              created_by TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL DEFAULT '',
              expires_at TEXT NOT NULL DEFAULT '',
              max_uses INTEGER NOT NULL DEFAULT 1,
              uses INTEGER NOT NULL DEFAULT 0,
              revoked INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        c.commit()


# ── users ───────────────────────────────────────────────────────────────
def create_user(username, password_hash, role="user", email="", display_name=""):
    with _LOCK:
        c = _connect()
        try:
            cur = c.execute(
                "INSERT INTO users(username,username_ci,email,display_name,password_hash,role,status,created_at)"
                " VALUES(?,?,?,?,?,?, 'active', ?)",
                (username, username.lower(), email, display_name or username,
                 password_hash, role, _now()),
            )
            c.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError as exc:
            raise ValueError("username_taken") from exc


def get_user_by_name(username):
    with _LOCK:
        c = _connect()
        return c.execute(
            "SELECT * FROM users WHERE username_ci=?", (username.lower(),)
        ).fetchone()


def authenticate(username, password):
    row = get_user_by_name(username)
    if not row or row["status"] != "active":
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return row


def list_users():
    with _LOCK:
        c = _connect()
        return c.execute(
            "SELECT * FROM users ORDER BY (role='admin') DESC, username_ci"
        ).fetchall()


def set_password(username, password_hash):
    with _LOCK:
        c = _connect()
        c.execute("UPDATE users SET password_hash=? WHERE username_ci=?",
                  (password_hash, username.lower()))
        c.commit()


def set_status(username, status):
    with _LOCK:
        c = _connect()
        c.execute("UPDATE users SET status=? WHERE username_ci=?", (status, username.lower()))
        c.commit()


def set_role(username, role):
    with _LOCK:
        c = _connect()
        c.execute("UPDATE users SET role=? WHERE username_ci=?", (role, username.lower()))
        c.commit()


def set_profile(username, email, display_name):
    with _LOCK:
        c = _connect()
        c.execute("UPDATE users SET email=?, display_name=? WHERE username_ci=?",
                  (email, display_name, username.lower()))
        c.commit()


def delete_user(username):
    with _LOCK:
        c = _connect()
        c.execute("DELETE FROM users WHERE username_ci=?", (username.lower(),))
        c.commit()


def touch_login(username):
    with _LOCK:
        c = _connect()
        c.execute("UPDATE users SET last_login_at=? WHERE username_ci=?", (_now(), username.lower()))
        c.commit()


def count_users() -> int:
    with _LOCK:
        c = _connect()
        return c.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def count_admins() -> int:
    """Active admins — used to guard against removing the last admin."""
    with _LOCK:
        c = _connect()
        return c.execute(
            "SELECT COUNT(*) FROM users WHERE role='admin' AND status='active'"
        ).fetchone()[0]


# ── invites ─────────────────────────────────────────────────────────────
def create_invite(role="user", created_by="", max_uses=1, expires_at="") -> str:
    code = secrets.token_urlsafe(12)
    with _LOCK:
        c = _connect()
        c.execute(
            "INSERT INTO invites(code,role,created_by,created_at,expires_at,max_uses)"
            " VALUES(?,?,?,?,?,?)",
            (code, role, created_by, _now(), str(expires_at or ""), int(max_uses)),
        )
        c.commit()
    return code


def get_invite(code):
    with _LOCK:
        c = _connect()
        return c.execute("SELECT * FROM invites WHERE code=?", (code,)).fetchone()


def validate_invite(code) -> bool:
    row = get_invite(code)
    if not row or row["revoked"] or row["uses"] >= row["max_uses"]:
        return False
    if row["expires_at"] and int(row["expires_at"]) < int(time.time()):
        return False
    return True


def consume_invite(code) -> bool:
    """Atomically claim one use of the invite. Returns False if it raced out."""
    now = int(time.time())
    with _LOCK:
        c = _connect()
        cur = c.execute(
            "UPDATE invites SET uses=uses+1 WHERE code=? AND revoked=0 AND uses<max_uses"
            " AND (expires_at='' OR CAST(expires_at AS INTEGER)>?)",
            (code, now),
        )
        c.commit()
        return cur.rowcount == 1


def list_invites():
    with _LOCK:
        c = _connect()
        return c.execute("SELECT * FROM invites ORDER BY created_at DESC").fetchall()


def revoke_invite(code):
    with _LOCK:
        c = _connect()
        c.execute("UPDATE invites SET revoked=1 WHERE code=?", (code,))
        c.commit()
