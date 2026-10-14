"""Editorial: public pages, archive paywall gate, print paths, history."""
import pytest

from app.models import Event, Issue, Story, utcnow


def _seed_magazine(app):
    from app.db import get_db
    with app.app_context():
        db = get_db()
        old = Issue(number=9, title="Older Issue", slug="older-issue",
                    blurb="From the archive.", is_published=True,
                    published_at=utcnow())
        new = Issue(number=10, title="Current Issue", slug="current-issue",
                    blurb="Fresh off the press.", is_published=True,
                    published_at=utcnow())
        db.add_all([old, new])
        db.flush()
        db.add(Story(title="Old story", slug="old-story", category="news",
                     excerpt="Archive excerpt.", body="Archive body.",
                     issue_id=old.id, is_published=True,
                     published_at=utcnow()))
        db.add(Story(title="New story", slug="new-story", category="news",
                     excerpt="Fresh excerpt.", body="Fresh body.",
                     issue_id=new.id, is_published=True,
                     published_at=utcnow()))
        db.add(Story(title="Lone story", slug="lone-story", category="news",
                     excerpt="Standalone.", body="Standalone body.",
                     is_published=True, published_at=utcnow()))
        db.commit()
        return old, new


def test_home_renders(client):
    assert client.get("/").status_code == 200


def _grant_magazine_subscription(app, user):
    """Give a user an active magazine-audience subscription (test helper)."""
    from app.db import get_db
    from app.models import SubscriptionTier, UserSubscription
    with app.app_context():
        db = get_db()
        tier = SubscriptionTier(name="Test Insider", slug="test-insider",
                                audience="magazine", is_active=True)
        db.add(tier)
        db.flush()
        db.add(UserSubscription(user_id=user.id, tier_id=tier.id,
                                status="active"))
        db.commit()


def test_all_stories_are_free_funnel(client, app):
    _seed_magazine(app)
    assert b"Archive body" in client.get("/stories/old-story").data
    assert b"Fresh body" in client.get("/stories/new-story").data
    assert b"Standalone body" in client.get("/stories/lone-story").data


def test_full_issue_view_is_subscriber_only(client, app):
    _seed_magazine(app)
    for slug in ("current-issue", "older-issue"):
        rv = client.get(f"/issues/{slug}")
        assert rv.status_code == 200  # teaser page, not 404
        assert b"subscribe" in rv.data.lower()
        assert b"Archive body" not in rv.data
        assert b"Fresh body" not in rv.data


def test_subscriber_can_view_full_issue(collector_client, collector_user, app):
    _seed_magazine(app)
    _grant_magazine_subscription(app, collector_user)
    rv = collector_client.get("/issues/older-issue")
    assert b"Archive body" in rv.data or b"Old story" in rv.data


def test_owner_bypasses_paywall(owner_client, app):
    _seed_magazine(app)
    rv = owner_client.get("/issues/older-issue")
    assert b"Archive body" in rv.data or b"Old story" in rv.data


def test_history_teaser_for_public_full_for_subscriber(client, collector_client,
                                                       collector_user, app):
    _seed_magazine(app)
    rv = client.get("/history")
    assert rv.status_code == 200
    assert b"Older Issue" in rv.data  # teaser: covers/titles visible
    _grant_magazine_subscription(app, collector_user)
    rv2 = collector_client.get("/history")
    assert rv2.status_code == 200


def test_print_view_and_pdf_are_subscriber_only(client, collector_client,
                                                collector_user, app):
    _seed_magazine(app)
    # public: locked out of print — no PDF bytes, teaser/redirect instead
    assert not client.get("/issues/current-issue/print.pdf").data.startswith(b"%PDF")
    assert b"Fresh body" not in client.get("/issues/current-issue/print").data
    # subscriber: PDF renders
    _grant_magazine_subscription(app, collector_user)
    pdf = collector_client.get("/issues/current-issue/print.pdf")
    assert pdf.status_code == 200
    assert pdf.content_type == "application/pdf"
    assert pdf.data[:4] == b"%PDF"
    assert collector_client.get("/issues/current-issue/print").status_code == 200


def test_event_submit_creates_pending(client, app):
    from app.db import get_db
    rv = client.post("/events/submit", data={
        "title": "Sample meetup", "city": "Casper", "state": "WY",
        "description": "A test event.",
    }, follow_redirects=True)
    assert rv.status_code == 200
    with app.app_context():
        ev = get_db().query(Event).filter_by(title="Sample meetup").one()
        assert ev.status == "pending"


def test_newsletter_archive_and_search(client):
    assert client.get("/newsletter").status_code == 200
    rv = client.get("/search?q=story")
    assert rv.status_code == 200
    rv2 = client.get("/search?q=story&scope=magazine")
    assert rv2.status_code == 200


def test_owner_can_publish_story(owner_client, app):
    rv = owner_client.post("/owner/stories/new", data={
        "title": "Owner published story", "category": "news",
        "excerpt": "Excerpt here.", "body": "Body here.",
        "is_published": "on",
    }, follow_redirects=True)
    assert rv.status_code == 200
    from app.db import get_db
    with app.app_context():
        s = get_db().query(Story).filter_by(title="Owner published story").one()
        assert s.is_published
        assert s.slug


def test_owner_leads_inbox(owner_client, app):
    from app.leads import ingest_lead
    from app.db import get_db
    with app.app_context():
        ingest_lead(get_db(), headline="Test lead headline",
                    source_url="https://example.com/test-lead-1")
    rv = owner_client.get("/owner/leads")
    assert rv.status_code == 200
    assert b"Test lead headline" in rv.data
