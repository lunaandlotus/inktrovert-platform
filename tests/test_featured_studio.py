"""Featured studio seed: Luna & Lotus + Angie Valentin + homepage showcase."""
import os
import sys

from app.db import get_db
from app.models import Profile, TeamAffiliation


def _seed_studio(app):
    sys.path.insert(
        0,
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "scripts"),
    )
    import seed_studio
    with app.app_context():
        seed_studio._seed()


def test_studio_profile_seeded_claimed_verified_featured(app):
    _seed_studio(app)
    with app.app_context():
        db = get_db()
        studio = db.query(Profile).filter_by(slug="luna-lotus-piercing-ink").one()
        assert studio.kind == "studio"
        assert studio.display_name == "Luna & Lotus Piercing & Ink"
        assert studio.verified is True
        assert studio.claim_status == "claimed"
        assert studio.is_featured is True
        assert studio.is_listed is True
        assert studio.city == "Casper"
        assert studio.state == "WY"
        assert studio.phone == "307-215-1727"
        assert studio.email == "angie@lunaandlotus.ink"
        assert studio.website == "https://www.lunaandlotus.ink"
        assert studio.booking_url == "https://www.lunaandlotus.ink"
        assert studio.latitude is not None and studio.longitude is not None


def test_artist_profile_and_roster_affiliation(app):
    _seed_studio(app)
    with app.app_context():
        db = get_db()
        artist = db.query(Profile).filter_by(slug="angie-valentin").one()
        studio = db.query(Profile).filter_by(slug="luna-lotus-piercing-ink").one()
        assert artist.kind == "tattoo_artist"
        assert artist.verified is True
        assert artist.claim_status == "claimed"
        aff = (
            db.query(TeamAffiliation)
            .filter_by(studio_profile_id=studio.id,
                       member_profile_id=artist.id)
            .one()
        )
        assert "Owner" in aff.role_label


def test_homepage_shows_featured_studio_showcase(client, app):
    _seed_studio(app)
    rv = client.get("/")
    assert rv.status_code == 200
    assert b"Featured studio" in rv.data
    assert b"Luna &amp; Lotus" in rv.data
    assert b"First on Inktrovert" in rv.data


def test_studio_profile_page_renders(client, app):
    _seed_studio(app)
    rv = client.get("/directory/luna-lotus-piercing-ink")
    assert rv.status_code == 200
    assert b"Luna &amp; Lotus" in rv.data


def test_seed_idempotent(app):
    _seed_studio(app)
    _seed_studio(app)
    with app.app_context():
        db = get_db()
        assert db.query(Profile).filter_by(slug="luna-lotus-piercing-ink").count() == 1
        assert db.query(Profile).filter_by(slug="angie-valentin").count() == 1
