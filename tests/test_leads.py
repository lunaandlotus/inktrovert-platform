"""Story leads inbox: ingest, dedupe, review, promote, discard."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app import leads
from app.models import Story, StoryLead


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()


def make_lead(db, **kw):
    lead, reason = leads.ingest_lead(db, **kw)
    assert reason is None
    return lead


def test_ingest_creates_new_lead(db):
    lead, reason = leads.ingest_lead(
        db, headline="Ink brand launches vegan aftercare",
        source_url="https://example.com/news/aftercare?utm_source=rss",
        source_name="Example News", suggested_angle="Angle: interview the founder.")
    assert reason is None
    assert lead.status == "new"
    assert lead.source_name == "Example News"
    assert lead.submitted_by == "daily-gather-job"


def test_ingest_requires_headline_and_url(db):
    with pytest.raises(ValueError):
        leads.ingest_lead(db, headline="", source_url="https://example.com/x")
    with pytest.raises(ValueError):
        leads.ingest_lead(db, headline="Hi", source_url="")


def test_duplicate_url_skipped_even_with_tracking_params(db):
    first = make_lead(db, headline="Story one", source_url="https://example.com/a?utm_source=rss")
    # Same canonical link, different tracking params -> duplicate_url
    existing, reason = leads.ingest_lead(
        db, headline="Story one (updated)", source_url="https://example.com/a?fbclid=xyz")
    assert reason == "duplicate_url"
    assert existing.id == first.id
    assert db.query(StoryLead).count() == 1


def test_duplicate_headline_skipped_on_different_url(db):
    first = make_lead(db, headline="Big Convention Announced!", source_url="https://a.com/1")
    existing, reason = leads.ingest_lead(
        db, headline="big convention announced", source_url="https://b.com/2")
    assert reason == "duplicate_headline"
    assert existing.id == first.id
    assert db.query(StoryLead).count() == 1


def test_discarded_headline_may_return_via_new_link(db):
    lead = make_lead(db, headline="Old angle", source_url="https://a.com/1")
    leads.discard_lead(db, lead, note="not our beat")
    fresh, reason = leads.ingest_lead(db, headline="Old angle", source_url="https://b.com/9")
    assert reason is None
    assert fresh.id != lead.id


def test_bulk_ingest_reports_created_and_skipped(db):
    make_lead(db, headline="Existing", source_url="https://a.com/1")
    result = leads.ingest_leads(db, [
        {"headline": "Fresh find", "source_url": "https://c.com/1",
         "source_name": "Wire", "suggested_angle": "Do a spotlight."},
        {"headline": "Existing", "source_url": "https://a.com/1"},
        {"headline": "existing!", "source_url": "https://d.com/5"},
    ])
    assert len(result["created"]) == 1
    assert {s["reason"] for s in result["skipped"]} == {"duplicate_url", "duplicate_headline"}


def test_review_status_flow(db):
    lead = make_lead(db, headline="To review", source_url="https://a.com/1")
    leads.set_lead_status(db, lead, "reviewing")
    assert lead.status == "reviewing"
    with pytest.raises(ValueError):
        leads.set_lead_status(db, lead, "bogus")


def test_promote_creates_unpublished_story_and_links(db):
    lead = make_lead(db, headline="Promote me", source_url="https://a.com/1",
                     source_name="Wire", suggested_angle="Great angle here.")
    story = leads.promote_lead(db, lead, category="spotlight", author_name="Inktrovert")
    assert isinstance(story, Story)
    assert story.title == "Promote me"
    assert story.category == "spotlight"
    assert story.is_published is False
    assert "https://a.com/1" in story.body
    assert lead.status == "promoted"
    assert lead.promoted_story_id == story.id
    # Idempotent: promoting again returns the same story, no duplicate.
    assert leads.promote_lead(db, lead).id == story.id
    assert db.query(Story).count() == 1


def test_promote_rejects_bad_category(db):
    lead = make_lead(db, headline="Nope", source_url="https://a.com/1")
    with pytest.raises(ValueError):
        leads.promote_lead(db, lead, category="bogus")


def test_discard_keeps_note(db):
    lead = make_lead(db, headline="Discard me", source_url="https://a.com/1")
    leads.discard_lead(db, lead, note="duplicate of print issue")
    assert lead.status == "discarded"
    assert "duplicate of print issue" in lead.notes


def test_inbox_counts(db):
    make_lead(db, headline="One", source_url="https://a.com/1")
    make_lead(db, headline="Two", source_url="https://a.com/2")
    lead3 = make_lead(db, headline="Three", source_url="https://a.com/3")
    leads.discard_lead(db, lead3)
    counts = leads.inbox_counts(db)
    assert counts["new"] == 2
    assert counts["discarded"] == 1
    assert counts["reviewing"] == 0


def test_normalize_url_strips_tracking_and_case(db):
    a = leads.normalize_url("HTTPS://Example.COM/News/?utm_source=rss&b=2&B=1")
    b = leads.normalize_url("https://example.com/News?B=1&b=2")
    assert a == b
    assert "utm_source" not in a
