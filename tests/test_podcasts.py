"""Podcasts: series/episode models and public listening pages."""
import pytest

from app.models import PodcastEpisode, PodcastSeries, utcnow


def _seed_podcasts(app):
    from app.db import get_db
    with app.app_context():
        db = get_db()
        s1 = PodcastSeries(title="Ink Stories", slug="ink-stories",
                           audience="collectors", description="For collectors.",
                           sort_order=0)
        s2 = PodcastSeries(title="Pro Chair", slug="pro-chair",
                           audience="professionals", description="For pros.",
                           sort_order=1)
        db.add_all([s1, s2])
        db.flush()
        db.add(PodcastEpisode(
            series_id=s1.id, title="Episode One", slug="episode-one",
            episode_number=1, description="Show notes here.",
            audio_file="audio/ep1.wav", duration_seconds=300,
            is_published=True, published_at=utcnow()))
        db.add(PodcastEpisode(
            series_id=s1.id, title="Draft Episode", slug="draft-episode",
            episode_number=2, description="Not yet.",
            is_published=False))
        db.commit()


def test_series_index_lists_both_series(client, app):
    _seed_podcasts(app)
    rv = client.get("/podcasts/")
    assert rv.status_code == 200
    assert b"Ink Stories" in rv.data
    assert b"Pro Chair" in rv.data


def test_series_detail_shows_only_published(client, app):
    _seed_podcasts(app)
    rv = client.get("/podcasts/ink-stories")
    assert rv.status_code == 200
    assert b"Episode One" in rv.data
    assert b"Draft Episode" not in rv.data


def test_episode_detail_has_player_and_notes(client, app):
    _seed_podcasts(app)
    rv = client.get("/podcasts/ink-stories/episode-one")
    assert rv.status_code == 200
    assert b"<audio" in rv.data
    assert b"Show notes here." in rv.data
    assert b"audio/ep1.wav" in rv.data


def test_unknown_series_404(client, app):
    _seed_podcasts(app)
    assert client.get("/podcasts/nope").status_code == 404


def test_duration_filter(app):
    f = app.jinja_env.filters["duration"]
    assert f(300) == "5:00"
    assert f(3661) == "1:01:01"
    assert f(None) == ""
