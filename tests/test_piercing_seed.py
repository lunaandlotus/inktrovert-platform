"""Piercing coverage: news stories, podcast series, topic tags and filter."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "scripts"))

from app.db import get_db
from app.models import PodcastEpisode, PodcastSeries, Story


def _run_seed(app):
    import seed_content
    import seed_piercing
    with app.app_context():
        seed_content._seed()
        seed_piercing._seed()


def _counts(app):
    with app.app_context():
        db = get_db()
        return (
            db.query(Story).count(),
            db.query(PodcastSeries).count(),
            db.query(PodcastEpisode).count(),
        )


def test_piercing_stories_seeded_with_states(app):
    _run_seed(app)
    with app.app_context():
        db = get_db()
        wanted = {
            "curated-app-conference-2026-las-vegas",
            "curated-h2ocean-25-years-app-conference",
            "curated-new-flower-studio-app-2026-emerald-coast",
            "curated-sanamama-miami-piercing-celebration",
            "curated-camp-app-2026-georgia",
        }
        stories = {
            s.slug: s for s in
            db.query(Story).filter(Story.slug.in_(wanted)).all()
        }
        assert set(stories) == wanted
        assert "curated-app-conference-2026-las-vegas" in stories
        assert stories["curated-app-conference-2026-las-vegas"].state == "NV"
        assert "curated-h2ocean-25-years-app-conference" in stories
        assert stories["curated-h2ocean-25-years-app-conference"].state == "FL"
        assert "curated-new-flower-studio-app-2026-emerald-coast" in stories
        assert stories["curated-new-flower-studio-app-2026-emerald-coast"].state == "CA"
        assert "curated-sanamama-miami-piercing-celebration" in stories
        assert "curated-camp-app-2026-georgia" in stories
        assert stories["curated-camp-app-2026-georgia"].state == "GA"
        # Every piercing story carries source attribution.
        for s in stories.values():
            assert "Curated by Inktrovert" in s.body
            assert s.is_published


def test_piercing_podcast_series_seeded(app):
    _run_seed(app)
    with app.app_context():
        db = get_db()
        series = {s.slug: s for s in db.query(PodcastSeries).all()}
        for slug in ("curated-piercing-wizard",
                     "curated-talking-about-piercing-live",
                     "curated-discussions-in-body-art"):
            assert slug in series, slug
            assert series[slug].topic == "piercing"
            eps = db.query(PodcastEpisode).filter_by(
                series_id=series[slug].id).all()
            assert 2 <= len(eps) <= 4
            for ep in eps:
                assert ep.is_published
                assert "Listen:" in ep.description


def test_topic_backfill_on_existing_series(app):
    _run_seed(app)
    with app.app_context():
        db = get_db()
        topics = {s.slug: s.topic for s in db.query(PodcastSeries).all()}
        assert topics["curated-honest-tattooer"] == "tattoo"
        assert topics["curated-fireside-tattoo"] == "tattoo"
        assert topics["curated-qa-in-the-kitchen"] == "both"


def test_piercing_seed_idempotent(app):
    _run_seed(app)
    before = _counts(app)
    _run_seed(app)
    assert _counts(app) == before


def test_podcasts_topic_filter(client, app):
    _run_seed(app)
    rv = client.get("/podcasts/?topic=piercing")
    assert rv.status_code == 200
    assert b"Piercing Wizard" in rv.data
    assert b"Talking About Piercing Live" in rv.data
    assert b"Discussions in Body Art" in rv.data
    # Tattoo-only shows are filtered out; "both" shows stay.
    assert b"Honest Tattooer" not in rv.data
    assert b"Q&amp;A in the Kitchen" in rv.data or b"Q&A in the Kitchen" in rv.data

    rv = client.get("/podcasts/?topic=tattoo")
    assert rv.status_code == 200
    assert b"Honest Tattooer" in rv.data
    assert b"Piercing Wizard" not in rv.data

    rv = client.get("/podcasts/")
    assert rv.status_code == 200
    assert b"Piercing Wizard" in rv.data
    assert b"Honest Tattooer" in rv.data
    # Topic badges visible on the index.
    assert b"Piercing" in rv.data


def test_invalid_topic_ignored(client, app):
    _run_seed(app)
    rv = client.get("/podcasts/?topic=nonsense")
    assert rv.status_code == 200
    assert b"Piercing Wizard" in rv.data
    assert b"Honest Tattooer" in rv.data
