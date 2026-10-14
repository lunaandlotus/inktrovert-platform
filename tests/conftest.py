"""Shared fixtures: per-test temp SQLite DB, test client, seed users."""
import os

# Set before importing the app so Config picks it up as the default.
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/inktrovert-test-bootstrap.db")

import pytest  # noqa: E402

from app import create_app  # noqa: E402
from app import db as _db  # noqa: E402


@pytest.fixture()
def app(tmp_path):
    application = create_app()
    # Swap to a fresh per-test database (create_app already bound the default).
    _db.init_engine(f"sqlite:///{tmp_path}/test.db")
    with application.app_context():
        _db.create_all()
        from app.auth import ensure_roles
        ensure_roles()
    application.config["TESTING"] = True
    application.config["CSRF_ENABLED"] = False
    yield application
    _db.get_engine().dispose()


@pytest.fixture()
def client(app):
    return app.test_client()


def _make_user(app, email, password, full_name="", roles=()):
    from app.auth import register_user
    with app.app_context():
        return register_user(email, password, full_name, roles=roles)


@pytest.fixture()
def owner_user(app):
    return _make_user(app, "owner@test.local", "OwnerPass1!", "Test Owner",
                      roles=["platform_owner"])


@pytest.fixture()
def collector_user(app):
    return _make_user(app, "fan@test.local", "FanPass1!", "Test Fan",
                      roles=["collector"])


@pytest.fixture()
def artist_user(app):
    return _make_user(app, "pro@test.local", "ProPass1!", "Test Pro",
                      roles=["tattoo_artist", "collector"])


def login_as(client, email, password):
    return client.post("/account/login",
                       data={"email": email, "password": password},
                       follow_redirects=True)


@pytest.fixture()
def owner_client(client, owner_user):
    login_as(client, "owner@test.local", "OwnerPass1!")
    return client


@pytest.fixture()
def collector_client(client, collector_user):
    login_as(client, "fan@test.local", "FanPass1!")
    return client
