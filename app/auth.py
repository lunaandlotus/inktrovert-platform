"""Authentication: argon2id password hashing + server-side login sessions.

Mirrors luna-lotus-portals/app/auth.py:
- register_user(): create a user with roles (get-or-create Role rows).
- create_login_session(user): persists a LoginSession row, returns the raw
  token; set_login_cookie()/clear_login_cookie() move it in/out of the
  HttpOnly cookie. The cookie alone is useless without the DB row.
- init_auth(app): before_request loads g.user (None when anonymous);
  teardown closes the DB session.
- @login_required, @role_required('platform_owner', ...).
- CSRF: csrf_token() template global; validate_csrf() for POST handlers.
  Logged-in users sign with their LoginSession.csrf_token; anonymous forms
  use a token kept in Flask's signed session cookie.

No email, no network calls, no external auth deps.
"""
from __future__ import annotations

import functools
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from flask import (abort, current_app, flash, g, redirect, request,
                   session as flask_session, url_for)

from .db import get_db
from .models import LoginSession, Role, User, VALID_ROLES, utcnow

_ph = PasswordHasher()  # argon2id by default

# How many devices/browsers may stay signed in for one user at the same time.
MAX_SESSIONS_PER_USER = 10


def _as_aware(dt: datetime | None) -> datetime | None:
    """SQLite strips tzinfo; compare safely either way."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Passwords (argon2id)
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    if not password:
        raise ValueError("password must not be empty")
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except Exception:
        return False


def register_user(email: str, password: str, full_name: str = "",
                  roles: tuple[str, ...] | list[str] = ()) -> User:
    """Create a user with roles. Raises ValueError on bad input/duplicates."""
    email = (email or "").strip().lower()
    if "@" not in email:
        raise ValueError("a valid email address is required")
    for role in roles:
        if role not in VALID_ROLES:
            raise ValueError(f"unknown role {role!r}; valid roles: {VALID_ROLES}")

    db = get_db()
    if db.query(User).filter_by(email=email).first():
        raise ValueError(f"user {email} already exists")

    user = User(email=email, password_hash=hash_password(password),
                full_name=full_name.strip(), claimed=True)
    db.add(user)
    db.flush()  # assign id before role wiring
    for role_name in roles:
        role_row = db.query(Role).filter_by(name=role_name).one_or_none()
        if role_row is None:
            role_row = Role(name=role_name)
            db.add(role_row)
            db.flush()
        user.roles.append(role_row)
    db.commit()
    return user


def ensure_roles(db=None) -> None:
    """Make sure every VALID_ROLES row exists (used at startup/seed)."""
    db = db or get_db()
    existing = {r.name for r in db.query(Role).all()}
    for name in VALID_ROLES:
        if name not in existing:
            db.add(Role(name=name))
    db.commit()


# ---------------------------------------------------------------------------
# Login sessions
# ---------------------------------------------------------------------------

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_login_session(user: User) -> str:
    """Persist a LoginSession row; return the raw token for the cookie."""
    db = get_db()
    # Prune oldest beyond the cap so a new device doesn't kick others out.
    sessions = (db.query(LoginSession)
                .filter_by(user_id=user.id, revoked=False)
                .order_by(LoginSession.created_at.desc()).all())
    for stale in sessions[MAX_SESSIONS_PER_USER - 1:]:
        stale.revoked = True
    token = secrets.token_urlsafe(32)
    lifetime = current_app.config["SESSION_LIFETIME_SECONDS"]
    db.add(LoginSession(
        user_id=user.id,
        token_hash=_hash_token(token),
        csrf_token=secrets.token_hex(32),
        expires_at=utcnow() + timedelta(seconds=lifetime),
    ))
    db.commit()
    return token


def set_login_cookie(response, token: str):
    cfg = current_app.config
    response.set_cookie(
        cfg["AUTH_COOKIE_NAME"], token,
        max_age=cfg["SESSION_LIFETIME_SECONDS"],
        httponly=cfg["SESSION_COOKIE_HTTPONLY"],
        secure=cfg["SESSION_COOKIE_SECURE"],
        samesite=cfg["SESSION_COOKIE_SAMESITE"],
    )
    return response


def clear_login_cookie(response):
    response.delete_cookie(current_app.config["AUTH_COOKIE_NAME"])
    return response


def logout_current_session() -> None:
    token = request.cookies.get(current_app.config["AUTH_COOKIE_NAME"])
    if token:
        db = get_db()
        row = (db.query(LoginSession)
               .filter_by(token_hash=_hash_token(token), revoked=False).one_or_none())
        if row is not None:
            row.revoked = True
            db.commit()


def get_current_user() -> User | None:
    return g.get("user")


def init_auth(app) -> None:
    @app.before_request
    def _load_user():
        g.user = None
        g.csrf_token_value = None
        token = request.cookies.get(app.config["AUTH_COOKIE_NAME"])
        if not token:
            return
        db = get_db()
        row = (db.query(LoginSession)
               .filter_by(token_hash=_hash_token(token), revoked=False).one_or_none())
        if row is None:
            return
        if _as_aware(row.expires_at) <= utcnow():
            row.revoked = True
            db.commit()
            return
        g.user = db.get(User, row.user_id)
        g.csrf_token_value = row.csrf_token

    @app.teardown_appcontext
    def _teardown(_exc=None):
        from .db import close_db
        close_db(_exc)


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def login_required(view):
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if g.get("user") is None:
            flash("Sign in to continue.", "info")
            return redirect(url_for("account.login", next=request.path))
        return view(*args, **kwargs)
    return wrapper


def role_required(*names: str):
    def decorator(view):
        @functools.wraps(view)
        def wrapper(*args, **kwargs):
            user = g.get("user")
            if user is None:
                flash("Sign in to continue.", "info")
                return redirect(url_for("account.login", next=request.path))
            if not any(user.has_role(n) for n in names):
                abort(403)
            return view(*args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------

def csrf_token() -> str:
    """Token for forms. Bound to the login session when signed in."""
    if g.get("csrf_token_value"):
        return g.csrf_token_value
    tok = flask_session.get("csrf_token")
    if not tok:
        tok = secrets.token_hex(32)
        flask_session["csrf_token"] = tok
    return tok


def validate_csrf() -> bool:
    if not current_app.config.get("CSRF_ENABLED", True):
        return True
    form_tok = request.form.get("csrf_token", "")
    return bool(form_tok) and secrets.compare_digest(form_tok, csrf_token())


def require_csrf(view):
    """Abort 400 when a POST/PUT/DELETE arrives without a valid CSRF token."""
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and not validate_csrf():
            abort(400, "Invalid or missing form token. Please go back and try again.")
        return view(*args, **kwargs)
    return wrapper
