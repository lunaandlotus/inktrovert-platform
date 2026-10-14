"""Studio roster invites + profile links/socials.

Covers: invite creates a pending affiliation (invisible publicly), artist
accept/decline, studio remove/cancel, artist leave, permission boundaries,
duplicate-invite handling, and link add/remove/display.
"""
import pytest

from app.models import Profile, ProfileLink, TeamAffiliation


def _seed_cast(app):
    """A claimed studio, a claimed artist, and an uninvolved stranger."""
    from app.auth import register_user
    from app.db import get_db
    with app.app_context():
        db = get_db()
        studio_owner = register_user("studio@test.local", "StudioPass1!",
                                     "Studio Boss", roles=["studio_owner"])
        artist = register_user("ink@test.local", "InkPass1!",
                               "Ink Artist", roles=["tattoo_artist"])
        stranger = register_user("stranger@test.local", "Stranger1!",
                                 "Stranger", roles=["collector"])
        studio = Profile(kind="studio", display_name="Test Studio",
                         slug="test-studio", city="Casper", state="WY",
                         claim_status="claimed", verified=True,
                         claimed_by_user_id=studio_owner.id)
        artist_profile = Profile(kind="tattoo_artist",
                                 display_name="Test Artist",
                                 slug="test-artist", city="Casper", state="WY",
                                 claim_status="claimed", verified=True,
                                 claimed_by_user_id=artist.id)
        db.add_all([studio, artist_profile])
        db.commit()
        return {"studio_id": studio.id, "artist_id": artist_profile.id}


def _login(client, email, password):
    return client.post("/account/login",
                       data={"email": email, "password": password},
                       follow_redirects=True)


def _aff(app, studio_id, artist_id):
    from app.db import get_db
    with app.app_context():
        return (get_db().query(TeamAffiliation)
                .filter_by(studio_profile_id=studio_id,
                           member_profile_id=artist_id).one_or_none())


def test_invite_creates_pending_and_stays_private(client, app):
    ids = _seed_cast(app)
    _login(client, "studio@test.local", "StudioPass1!")
    rv = client.post("/manage/test-studio/roster/invite",
                     data={"member_profile_id": ids["artist_id"],
                           "role_label": "Resident artist"},
                     follow_redirects=True)
    assert rv.status_code == 200
    aff = _aff(app, ids["studio_id"], ids["artist_id"])
    assert aff is not None and aff.status == "pending"
    # Not shown publicly until the artist accepts.
    assert b"Test Artist" not in client.get("/directory/test-studio").data


def test_artist_accept_shows_on_both_profiles(client, app):
    ids = _seed_cast(app)
    _login(client, "studio@test.local", "StudioPass1!")
    client.post("/manage/test-studio/roster/invite",
                data={"member_profile_id": ids["artist_id"]})
    aff = _aff(app, ids["studio_id"], ids["artist_id"])
    client.get("/account/logout")
    _login(client, "ink@test.local", "InkPass1!")
    rv = client.post(f"/manage/roster/{aff.id}/accept", follow_redirects=True)
    assert rv.status_code == 200
    assert _aff(app, ids["studio_id"], ids["artist_id"]).status == "accepted"
    assert b"Test Artist" in client.get("/directory/test-studio").data
    assert b"Test Studio" in client.get("/directory/test-artist").data


def test_artist_decline_leaves_no_trace(client, app):
    ids = _seed_cast(app)
    _login(client, "studio@test.local", "StudioPass1!")
    client.post("/manage/test-studio/roster/invite",
                data={"member_profile_id": ids["artist_id"]})
    aff = _aff(app, ids["studio_id"], ids["artist_id"])
    client.get("/account/logout")
    _login(client, "ink@test.local", "InkPass1!")
    client.post(f"/manage/roster/{aff.id}/decline", follow_redirects=True)
    assert _aff(app, ids["studio_id"], ids["artist_id"]).status == "declined"
    assert b"Test Artist" not in client.get("/directory/test-studio").data
    assert b"Test Studio" not in client.get("/directory/test-artist").data


def test_studio_can_remove_artist(client, app):
    ids = _seed_cast(app)
    _login(client, "studio@test.local", "StudioPass1!")
    client.post("/manage/test-studio/roster/invite",
                data={"member_profile_id": ids["artist_id"]})
    aff = _aff(app, ids["studio_id"], ids["artist_id"])
    client.get("/account/logout")
    _login(client, "ink@test.local", "InkPass1!")
    client.post(f"/manage/roster/{aff.id}/accept")
    client.get("/account/logout")
    _login(client, "studio@test.local", "StudioPass1!")
    rv = client.post(f"/manage/roster/{aff.id}/remove", follow_redirects=True)
    assert rv.status_code == 200
    assert _aff(app, ids["studio_id"], ids["artist_id"]) is None
    assert b"Test Artist" not in client.get("/directory/test-studio").data


def test_studio_can_cancel_pending_invite(client, app):
    ids = _seed_cast(app)
    _login(client, "studio@test.local", "StudioPass1!")
    client.post("/manage/test-studio/roster/invite",
                data={"member_profile_id": ids["artist_id"]})
    aff = _aff(app, ids["studio_id"], ids["artist_id"])
    client.post(f"/manage/roster/{aff.id}/cancel", follow_redirects=True)
    assert _aff(app, ids["studio_id"], ids["artist_id"]) is None


def test_artist_can_leave_roster(client, app):
    ids = _seed_cast(app)
    _login(client, "studio@test.local", "StudioPass1!")
    client.post("/manage/test-studio/roster/invite",
                data={"member_profile_id": ids["artist_id"]})
    aff = _aff(app, ids["studio_id"], ids["artist_id"])
    client.get("/account/logout")
    _login(client, "ink@test.local", "InkPass1!")
    client.post(f"/manage/roster/{aff.id}/accept")
    rv = client.post(f"/manage/roster/{aff.id}/leave", follow_redirects=True)
    assert rv.status_code == 200
    assert _aff(app, ids["studio_id"], ids["artist_id"]) is None
    assert b"Test Studio" not in client.get("/directory/test-artist").data


def test_duplicate_invite_is_rejected_gracefully(client, app):
    ids = _seed_cast(app)
    _login(client, "studio@test.local", "StudioPass1!")
    client.post("/manage/test-studio/roster/invite",
                data={"member_profile_id": ids["artist_id"]})
    client.post("/manage/test-studio/roster/invite",
                data={"member_profile_id": ids["artist_id"]},
                follow_redirects=True)
    from app.db import get_db
    with app.app_context():
        count = (get_db().query(TeamAffiliation)
                 .filter_by(studio_profile_id=ids["studio_id"],
                            member_profile_id=ids["artist_id"]).count())
    assert count == 1


def test_stranger_cannot_manage_or_invite(client, app):
    ids = _seed_cast(app)
    _login(client, "stranger@test.local", "Stranger1!")
    assert client.get("/manage/test-studio").status_code == 403
    rv = client.post("/manage/test-studio/roster/invite",
                     data={"member_profile_id": ids["artist_id"]})
    assert rv.status_code == 403
    assert _aff(app, ids["studio_id"], ids["artist_id"]) is None


def test_stranger_cannot_accept_invite(client, app):
    ids = _seed_cast(app)
    _login(client, "studio@test.local", "StudioPass1!")
    client.post("/manage/test-studio/roster/invite",
                data={"member_profile_id": ids["artist_id"]})
    aff = _aff(app, ids["studio_id"], ids["artist_id"])
    client.get("/account/logout")
    _login(client, "stranger@test.local", "Stranger1!")
    rv = client.post(f"/manage/roster/{aff.id}/accept")
    assert rv.status_code == 403
    assert _aff(app, ids["studio_id"], ids["artist_id"]).status == "pending"


def test_platform_owner_bypasses(client, app, owner_user):
    ids = _seed_cast(app)
    _login(client, "owner@test.local", "OwnerPass1!")
    # Owner can open the studio's manage desk…
    assert client.get("/manage/test-studio").status_code == 200
    # …and invite on its behalf.
    client.post("/manage/test-studio/roster/invite",
                data={"member_profile_id": ids["artist_id"]})
    aff = _aff(app, ids["studio_id"], ids["artist_id"])
    assert aff is not None and aff.status == "pending"
    # …and accept on the artist's behalf.
    client.post(f"/manage/roster/{aff.id}/accept", follow_redirects=True)
    assert _aff(app, ids["studio_id"], ids["artist_id"]).status == "accepted"


def test_links_add_remove_and_display(client, app):
    ids = _seed_cast(app)
    _login(client, "studio@test.local", "StudioPass1!")
    rv = client.post("/manage/test-studio/links/add",
                     data={"label": "Instagram",
                           "url": "instagram.com/teststudio"},
                     follow_redirects=True)
    assert rv.status_code == 200
    from app.db import get_db
    with app.app_context():
        link = get_db().query(ProfileLink).filter_by(
            profile_id=ids["studio_id"]).one()
        assert link.label == "Instagram"
        assert link.url == "https://instagram.com/teststudio"
        link_id = link.id
    # Shown on the public profile.
    page = client.get("/directory/test-studio")
    assert b"Instagram" in page.data
    assert b"https://instagram.com/teststudio" in page.data
    # Remove it.
    client.post(f"/manage/links/{link_id}/remove", follow_redirects=True)
    with app.app_context():
        assert get_db().get(ProfileLink, link_id) is None
    assert b"Instagram" not in client.get("/directory/test-studio").data


def test_links_require_label_and_url(client, app):
    _seed_cast(app)
    _login(client, "studio@test.local", "StudioPass1!")
    rv = client.post("/manage/test-studio/links/add",
                     data={"label": "", "url": ""}, follow_redirects=True)
    assert rv.status_code == 200
    from app.db import get_db
    with app.app_context():
        assert get_db().query(ProfileLink).count() == 0


def test_stranger_cannot_touch_links(client, app):
    ids = _seed_cast(app)
    _login(client, "studio@test.local", "StudioPass1!")
    client.post("/manage/test-studio/links/add",
                data={"label": "Instagram", "url": "https://instagram.com/x"})
    from app.db import get_db
    with app.app_context():
        link_id = get_db().query(ProfileLink).one().id
    client.get("/account/logout")
    _login(client, "stranger@test.local", "Stranger1!")
    assert client.post("/manage/test-studio/links/add",
                       data={"label": "Evil", "url": "https://evil.example"}
                       ).status_code == 403
    assert client.post(f"/manage/links/{link_id}/remove").status_code == 403
    with app.app_context():
        assert get_db().query(ProfileLink).count() == 1
