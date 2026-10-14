"""App configuration. SQLite for local dev; Postgres-ready via DATABASE_URL."""
from __future__ import annotations

import os


def _bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, "1" if default else "0") not in ("0", "", "false", "False")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    DEBUG = _bool("FLASK_DEBUG", False)

    DATABASE_URL = os.environ.get("DATABASE_URL") or (
        "sqlite:///" + os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    "instance", "inktrovert.db")
    )

    # Server-side session auth (mirrors luna-lotus-portals/app/auth.py).
    AUTH_COOKIE_NAME = "inktrovert_session"
    SESSION_LIFETIME_SECONDS = 30 * 24 * 3600
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    SESSION_COOKIE_SAMESITE = "Lax"
    LOGIN_VIEW = "account.login"

    CSRF_ENABLED = not _bool("DISABLE_CSRF", False)

    UPLOAD_DIR = os.environ.get(
        "UPLOAD_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads"),
    )
    MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "10"))
