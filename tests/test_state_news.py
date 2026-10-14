"""State-by-state news: state tags, search filter, state hubs, leads."""
import pytest

from app import db as _db
from app import leads
from app.models import Event, Issue, Profile, Story, normalize_state


def _story(db, slug, title, state=None, published=True):
    s = Story(title=title, slug=slug, category="news", excerpt="e", body="b",
              is_published=published, state=state)
    db.add(s)
    db.commit()
    return s


def _profile(db, name, kind, state, **kw):
    p = Profile(display_name=name,
                slug=name.lower().replace(" ", "-").replace("&", "and"),
                kind=kind, city="Testville", state=state, is_listed=True,
                **kw)
    db.add(p)
    db.commit()
    return p


@pytest.fixture()
def state_data(app):
    """CA news + studio + artist, NY news, one untagged story."""
    with app.app_context():
        db = _db.get_db()
        try:
            _story(db, "ca-expo", "California Expo News", state="CA")
            _story(db, "ny-con", "New York Convention News", state="NY")
            _story(db, "global-trends", "Worldwide Ink Trends")
            _profile(db, "Golden Studio", "studio", "California")
            _profile(db, "Cali Artist", "tattoo_artist", "CA")
            _profile(db, "Empire Studio", "studio", "New York")
            yield db
        finally:
            _db.close_db()


def test_normalize_state():
    assert normalize_state("WY") == "WY"
    assert normalize_state("wy") == "WY"
    assert normalize_state("Wyoming") == "WY"
    assert normalize_state("  new york ") == "NY"
    assert normalize_state("Hong Kong") is None
    assert normalize_state("") is None
    assert normalize_state(None) is None


def test_search_filters_stories_by_state(client, state_data):
    rv = client.get("/search?q=&state=CA&scope=magazine")
    assert rv.status_code == 200
    assert b"California Expo News" in rv.data
    assert b"New York Convention News" not in rv.data
    assert b"Worldwide Ink Trends" not in rv.data


def test_search_state_filter_covers_directory(client, state_data):
    rv = client.get("/search?q=&state=NY&scope=directory")
    assert rv.status_code == 200
    assert b"Empire Studio" in rv.data
    assert b"Golden Studio" not in rv.data
    assert b"Cali Artist" not in rv.data


def test_search_state_with_query(client, state_data):
    rv = client.get("/search?q=expo&state=CA")
    assert rv.status_code == 200
    assert b"California Expo News" in rv.data


def test_by_state_browse_lists_states(client, state_data):
    rv = client.get("/directory/by-state")
    assert rv.status_code == 200
    assert b"Artists &amp; Studios by State" in rv.data
    assert b"California" in rv.data
    assert b"New York" in rv.data


def test_state_hub_sections(client, state_data):
    rv = client.get("/directory/by-state/CA")
    assert rv.status_code == 200
    assert b"Golden Studio" in rv.data
    assert b"Cali Artist" in rv.data
    assert b"California Expo News" in rv.data
    assert b"Empire Studio" not in rv.data


def test_state_hub_featured_studio_first(client, app):
    with app.app_context():
        db = _db.get_db()
        try:
            _profile(db, "Desert Rose Ink", "studio", "Nevada",
                     featured_state="NV")
            _profile(db, "Silver State Studio", "studio", "NV")
            db.commit()
        finally:
            _db.close_db()
    rv = client.get("/directory/by-state/NV")
    assert rv.status_code == 200
    assert b"Featured studio" in rv.data
    assert b"Desert Rose Ink" in rv.data
    body = rv.data.decode()
    # Featured shows before the regular studios section.
    assert body.index("Desert Rose Ink") < body.index("Silver State Studio")


def test_state_hub_404_for_unknown_code(client):
    assert client.get("/directory/by-state/XX").status_code == 404


def test_issue_overview_then_by_state(client, app):
    with app.app_context():
        db = _db.get_db()
        try:
            issue = Issue(title="Test Issue", slug="test-issue-state",
                          is_published=True, number=99)
            db.add(issue)
            db.commit()
            s1 = _story(db, "intl-story", "International Story")
            s1.issue_id = issue.id
            s2 = _story(db, "tx-story", "Texas Story", state="TX")
            s2.issue_id = issue.id
            db.commit()
        finally:
            _db.close_db()
    # Log in as owner to pass the subscriber paywall.
    from tests.conftest import _make_user, login_as
    _make_user(app, "owner2@test.local", "OwnerPass1!", "O",
               roles=["platform_owner"])
    login_as(client, "owner2@test.local", "OwnerPass1!")
    rv = client.get("/issues/test-issue-state")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "The overview" in body
    assert "News by state" in body
    assert "International Story" in body
    assert "Texas Story" in body
    # Overview comes before the state breakdown.
    assert body.index("International Story") < body.index("Texas")


def test_ingest_lead_captures_suggested_state(app):
    from sqlalchemy.orm import Session
    with app.app_context():
        db = _db.get_db()
        try:
            lead, reason = leads.ingest_lead(
                db, headline="Reno shop opens", source_url="https://example.com/reno",
                suggested_state="Nevada")
            assert reason is None
            assert lead.suggested_state == "NV"
            lead2, _ = leads.ingest_lead(
                db, headline="Paris expo", source_url="https://example.com/paris",
                suggested_state="France")
            assert lead2.suggested_state is None
        finally:
            _db.close_db()


def test_promote_carries_state_to_story(app):
    with app.app_context():
        db = _db.get_db()
        try:
            lead, _ = leads.ingest_lead(
                db, headline="Casper flash day", source_url="https://example.com/casper",
                suggested_state="WY")
            story = leads.promote_lead(db, lead, category="news")
            assert story.state == "WY"
        finally:
            _db.close_db()


def test_state_columns_exist(app):
    """The nullable state columns exist on stories, leads, and profiles."""
    from sqlalchemy import inspect
    from app.db import get_engine
    engine = get_engine()
    for table, col in (("stories", "state"),
                       ("story_leads", "suggested_state"),
                       ("profiles", "featured_state")):
        cols = {c["name"] for c in inspect(engine).get_columns(table)}
        assert col in cols, f"{table}.{col} missing"
