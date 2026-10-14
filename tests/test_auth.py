"""Auth: register, login, logout, role gates, CSRF."""
import pytest

from app.auth import hash_password, verify_password


def test_password_hashing_roundtrip():
    h = hash_password("correct horse")
    assert verify_password(h, "correct horse")
    assert not verify_password(h, "wrong")
    with pytest.raises(ValueError):
        hash_password("")


def test_register_and_login_flow(client):
    rv = client.post("/account/register", data={
        "email": "new@test.local", "password": "Password1!",
        "full_name": "New Person",
    }, follow_redirects=True)
    assert rv.status_code == 200
    assert b"New Person" in rv.data  # landed on profile, signed in


def test_register_duplicate_email_friendly_error(client, collector_user):
    rv = client.post("/account/register", data={
        "email": "fan@test.local", "password": "Password1!",
    }, follow_redirects=True)
    assert b"already" in rv.data.lower()


def test_register_short_password_rejected(client):
    rv = client.post("/account/register", data={
        "email": "short@test.local", "password": "abc",
    }, follow_redirects=True)
    assert b"at least 8 characters" in rv.data
    # not created, not signed in: profile still redirects to login
    rv2 = client.get("/account/profile", follow_redirects=False)
    assert rv2.status_code in (302, 303)


def test_register_grants_pro_role(client):
    client.post("/account/register", data={
        "email": "pro2@test.local", "password": "Password1!",
        "roles": ["tattoo_artist"],
    }, follow_redirects=True)
    from app.auth import get_db as _get_db  # noqa
    # verify via fresh login -> profile shows role
    rv = client.get("/account/profile")
    assert b"Tattoo Artist" in rv.data  # template title-cases role names


def test_login_bad_credentials_generic_error(client, collector_user):
    rv = client.post("/account/login", data={
        "email": "fan@test.local", "password": "wrongpass",
    }, follow_redirects=True)
    assert b"don&#39;t match" in rv.data or b"don't match" in rv.data


def test_login_next_honors_relative_only(client, collector_user):
    rv = client.post("/account/login?next=/owner/", data={
        "email": "fan@test.local", "password": "FanPass1!",
    }, follow_redirects=False)
    assert rv.status_code in (302, 303)
    assert rv.headers["Location"].startswith("/owner/")


def test_login_next_rejects_absolute_url(client, collector_user):
    rv = client.post("/account/login?next=https://evil.example/", data={
        "email": "fan@test.local", "password": "FanPass1!",
    }, follow_redirects=False)
    assert "evil.example" not in rv.headers.get("Location", "")


def test_logout_clears_session(collector_client):
    rv = collector_client.get("/account/logout", follow_redirects=True)
    assert b"Sign in" in rv.data
    # profile now redirects to login
    rv2 = collector_client.get("/account/profile", follow_redirects=False)
    assert rv2.status_code in (302, 303)


def test_login_required_redirects_anonymous(client):
    rv = client.get("/account/profile", follow_redirects=False)
    assert rv.status_code in (302, 303)
    assert "/account/login" in rv.headers["Location"]


def test_owner_desk_forbidden_for_collector(collector_client):
    rv = collector_client.get("/owner/", follow_redirects=False)
    assert rv.status_code == 403


def test_owner_desk_ok_for_owner(owner_client):
    rv = owner_client.get("/owner/")
    assert rv.status_code == 200


def test_csrf_blocks_tokenless_post(app, client, collector_user):
    app.config["CSRF_ENABLED"] = True
    rv = client.post("/account/login", data={
        "email": "fan@test.local", "password": "FanPass1!",
    }, follow_redirects=False)
    assert rv.status_code == 400
