"""Podcasts — magazine/editorial layer listening pages.

Two series live here:
  * collectors    — artist stories, interviews, studio features
  * professionals — industry news + continued learning
                    (technique, business, professional education)

Listening is public — no login required. Episodes are structured for
future subscriber-only gating (models carry is_published/flags already);
audio is served from the uploads dir (dev-local, provider path later).
"""
from __future__ import annotations

from flask import Blueprint, abort, render_template, request, url_for
from sqlalchemy import case

from .db import get_db
from .models import PODCAST_AUDIENCES, PODCAST_TOPICS, PodcastEpisode, PodcastSeries

podcast_bp = Blueprint("podcasts", __name__, url_prefix="/podcasts")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _series_by_slug(series_slug: str) -> PodcastSeries:
    """Active series or 404."""
    db = get_db()
    series = (
        db.query(PodcastSeries)
        .filter_by(slug=series_slug, is_active=True)
        .first()
    )
    if series is None:
        abort(404)
    return series


def _published_episodes(series: PodcastSeries):
    """Newest-first published episodes for one series."""
    db = get_db()
    return (
        db.query(PodcastEpisode)
        .filter_by(series_id=series.id, is_published=True)
        .order_by(
            PodcastEpisode.published_at.desc().nullslast(),
            PodcastEpisode.episode_number.desc(),
        )
        .all()
    )


def _audience_label(audience: str) -> str:
    return "Collectors" if audience == "collectors" else "Professionals"


def _topic_label(topic: str | None) -> str:
    return {"tattoo": "Tattoo", "piercing": "Piercing",
            "both": "Tattoo + Piercing"}.get(topic or "", "")


def _audio_url(episode: PodcastEpisode) -> str | None:
    if episode.audio_file:
        return url_for("uploaded_file", filename=episode.audio_file)
    return None


def _format_duration(seconds: int | None) -> str:
    if not seconds:
        return ""
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


@podcast_bp.app_template_filter("duration")
def duration_filter(seconds: int | None) -> str:
    return _format_duration(seconds)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@podcast_bp.get("/")
def index():
    """All active series, collectors first, each with its latest 3 episodes.

    ?topic=tattoo|piercing filters to shows about that craft ("both" shows
    appear under either filter).
    """
    topic = request.args.get("topic", "").strip().lower() or None
    if topic not in PODCAST_TOPICS:
        topic = None
    db = get_db()
    q = db.query(PodcastSeries).filter_by(is_active=True)
    if topic:
        q = q.filter(PodcastSeries.topic.in_([topic, "both"]))
    series = (
        q.order_by(
            # Collectors series first, then professionals; stable order within.
            case(
                {aud: i for i, aud in enumerate(PODCAST_AUDIENCES)},
                value=PodcastSeries.audience,
            ),
            PodcastSeries.sort_order,
            PodcastSeries.title,
        )
        .all()
    )
    previews = [
        {"series": s, "episodes": _published_episodes(s)[:3]} for s in series
    ]
    return render_template(
        "podcasts/index.html",
        previews=previews,
        audience_label=_audience_label,
        topic_label=_topic_label,
        active_topic=topic,
        audio_url=_audio_url,
    )


@podcast_bp.get("/<series_slug>")
def series_detail(series_slug: str):
    """One series with every published episode, newest first."""
    series = _series_by_slug(series_slug)
    episodes = _published_episodes(series)
    return render_template(
        "podcasts/series.html",
        series=series,
        episodes=episodes,
        audience_label=_audience_label,
        audio_url=_audio_url,
    )


@podcast_bp.get("/<series_slug>/<episode_slug>")
def episode_detail(series_slug: str, episode_slug: str):
    """Player, show notes, episode number, related story/profile links."""
    series = _series_by_slug(series_slug)
    db = get_db()
    episode = (
        db.query(PodcastEpisode)
        .filter_by(
            series_id=series.id,
            slug=episode_slug,
            is_published=True,
        )
        .first()
    )
    if episode is None:
        abort(404)
    return render_template(
        "podcasts/episode.html",
        series=series,
        episode=episode,
        audience_label=_audience_label,
        audio_url=_audio_url,
    )
