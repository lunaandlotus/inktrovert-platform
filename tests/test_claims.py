"""Directory + claims: browse, profile detail, claim workflow."""
import pytest

from app.models import ClaimRequest, Profile


def _seed_profiles(app, owner_user):
    from app.db import get_db
    with app.app_context():
        db = get_db()
        studio = Profile(
            kind="studio", display_name="Claimed Studio", slug="claimed-studio",
            bio="A verified studio.", city="Casper", state="WY",
            specialties=["blackwork"], services=["tattoo"],
            claim_status="claimed", verified=True,
            claimed_by_user_id=owner_user.id)
        artist = Profile(
            kind="tattoo_artist", display_name="Unclaimed Artist",
            slug="unclaimed-artist", bio="Free agent.", city="Denver",
            state="CO", specialties=["fine line"], services=["tattoo"],
            claim_status="unclaimed")
        db.add_all([studio, artist])
        db.commit()
        return studio.id, artist.id


def test_browse_lists_profiles_and_filters(client, app, owner_user):
    _seed_profiles(app, owner_user)
    rv = client.get("/directory/")
    assert rv.status_code == 200
    assert b"Claimed Studio" in rv.data
    rv2 = client.get("/directory/?q=Denver")
    assert b"Unclaimed Artist" in rv2.data
    assert b"Claimed Studio" not in rv2.data
    rv3 = client.get("/directory/?style=blackwork")
    assert b"Claimed Studio" in rv3.data


def test_profile_detail_shows_verified_badge(client, app, owner_user):
    _seed_profiles(app, owner_user)
    rv = client.get("/directory/claimed-studio")
    assert rv.status_code == 200
    assert b"Verified" in rv.data


def test_claim_flow_end_to_end(collector_client, app, owner_user):
    _seed_profiles(app, owner_user)
    from app.db import get_db
    with app.app_context():
        pid = get_db().query(Profile).filter_by(slug="unclaimed-artist").one().id
    # file a claim
    rv = collector_client.post(f"/claims/for/{pid}", data={
        "claimer_relationship": "artist",
        "evidence_text": "This is me, here is my portfolio link.",
    }, follow_redirects=True)
    assert rv.status_code == 200
    with app.app_context():
        claim = get_db().query(ClaimRequest).filter_by(profile_id=pid).one()
        assert claim.status == "pending"
    # second attempt redirects to the existing pending claim
    rv2 = collector_client.post(f"/claims/for/{pid}", data={
        "claimer_relationship": "artist", "evidence_text": "again",
    }, follow_redirects=False)
    assert rv2.status_code in (302, 303)


def test_owner_approves_claim(owner_client, owner_user, app, collector_user):
    _seed_profiles(app, owner_user)
    from app.db import get_db
    with app.app_context():
        db = get_db()
        profile = db.query(Profile).filter_by(slug="unclaimed-artist").one()
        claim = ClaimRequest(profile_id=profile.id, user_id=collector_user.id,
                             claimer_relationship="artist",
                             evidence_text="me", status="pending")
        db.add(claim)
        db.commit()
        cid = claim.id
    rv = owner_client.post(f"/owner/claims/{cid}/approve",
                           follow_redirects=True)
    assert rv.status_code == 200
    with app.app_context():
        db = get_db()
        claim = db.get(ClaimRequest, cid)
        profile = db.get(Profile, claim.profile_id)
        assert claim.status == "approved"
        assert profile.claim_status == "claimed"
        assert profile.verified is True
        assert profile.claimed_by_user_id == collector_user.id


def test_new_listing_creates_profile_and_claim(collector_client, app):
    rv = collector_client.post("/claims/new", data={
        "kind": "studio",
        "display_name": "Brand New Studio",
        "city": "Cheyenne", "state": "WY",
        "bio": "Just opened.",
        "specialties": "blackwork, cover-ups",
        "services": "tattoo",
        "claimer_relationship": "owner",
        "evidence_text": "I own this shop.",
    }, follow_redirects=True)
    assert rv.status_code == 200
    from app.db import get_db
    with app.app_context():
        db = get_db()
        profile = db.query(Profile).filter_by(
            display_name="Brand New Studio").one()
        assert profile.claim_status == "pending"
        assert "blackwork" in profile.specialties
        claim = db.query(ClaimRequest).filter_by(
            profile_id=profile.id).one()
        assert claim.status == "pending"


def test_claim_status_private_to_owner(collector_client, client, app,
                                       collector_user, artist_user):
    from app.db import get_db
    _seed_profiles(app, collector_user)
    with app.app_context():
        db = get_db()
        pid = db.query(Profile).filter_by(slug="unclaimed-artist").one().id
        claim = ClaimRequest(profile_id=pid, user_id=collector_user.id,
                             claimer_relationship="artist",
                             evidence_text="me", status="pending")
        db.add(claim)
        db.commit()
        cid = claim.id
    # another signed-in user gets 403 (fresh client: login page bounces
    # already-signed-in sessions, so don't reuse the fan session)
    other = app.test_client()
    other.post("/account/login",
               data={"email": "pro@test.local", "password": "ProPass1!"})
    assert other.get(f"/claims/{cid}").status_code == 403
    # anonymous users are sent to sign in
    anon = app.test_client()
    assert anon.get(f"/claims/{cid}").status_code in (302, 303)
