"""Public directory — browse and view artist/studio/brand listings.

Phase 2 of the Inktrovert platform. Read-only for the public: browse with
filters (kind, style/specialty, name, location) and view a full listing —
portfolio collections, flash pieces, team affiliations, contact, and booking.
Listing creation and ownership claims live in app/claims.py; editing a
claimed listing is the owner's desk (app/owner.py).
"""
from __future__ import annotations

from flask import Blueprint, abort, render_template, request

from .db import get_db
from .models import (PROFILE_KINDS, Event, Profile, Review, Story,
                     TeamAffiliation, US_STATES, normalize_state)

directory_bp = Blueprint("directory", __name__, url_prefix="/directory")

KIND_LABELS = {
    "tattoo_artist": "Tattoo artist",
    "piercer": "Piercer",
    "independent_artist": "Independent artist",
    "studio": "Studio",
    "brand": "Brand",
}

FLASH_LABELS = {
    "available": "Available",
    "reserved": "Reserved",
    "sold": "Sold",
}


def _filters() -> dict:
    """Trimmed query-string filters for the browse page."""
    return {
        "kind": (request.args.get("kind") or "").strip(),
        "style": (request.args.get("style") or "").strip(),
        "q": (request.args.get("q") or "").strip(),
        "location": (request.args.get("location") or "").strip(),
    }


@directory_bp.get("/")
def browse():
    """GET /directory/ — listed profiles, filterable by kind, style, name, location."""
    db = get_db()
    f = _filters()

    query = db.query(Profile).filter(Profile.is_listed.is_(True))

    if f["kind"] in PROFILE_KINDS:
        query = query.filter(Profile.kind == f["kind"])

    if f["q"]:
        like = f"%{f['q']}%"
        query = query.filter(
            (Profile.display_name.ilike(like)) | (Profile.city.ilike(like))
        )

    if f["location"]:
        like = f"%{f['location']}%"
        query = query.filter(
            (Profile.city.ilike(like)) | (Profile.state.ilike(like))
        )

    profiles = query.order_by(Profile.display_name.asc()).all()

    # Style matches against the specialties list (JSON — filter in Python
    # so this stays portable across SQLite and Postgres).
    if f["style"]:
        needle = f["style"].casefold()
        profiles = [
            p for p in profiles
            if any(needle in (s or "").casefold() for s in (p.specialties or []))
        ]

    return render_template(
        "directory/index.html",
        profiles=profiles,
        filters=f,
        kind_labels=KIND_LABELS,
        kinds=PROFILE_KINDS,
    )


@directory_bp.get("/<slug>")
def profile_detail(slug):
    """GET /directory/<slug> — full listing: portfolio, flash, team, booking, contact."""
    db = get_db()
    profile = (
        db.query(Profile).filter_by(slug=slug, is_listed=True).one_or_none()
    )
    if profile is None:
        abort(404)

    members: list[tuple[Profile, str]] = []   # (profile, role_label) — if a studio
    studios: list[tuple[Profile, str]] = []    # (profile, role_label) — studios they belong to

    if profile.kind == "studio":
        affs = (
            db.query(TeamAffiliation)
            .filter_by(studio_profile_id=profile.id, status="accepted")
            .order_by(TeamAffiliation.sort_order, TeamAffiliation.id)
            .all()
        )
        if affs:
            by_id = {
                p.id: p
                for p in db.query(Profile).filter(
                    Profile.id.in_([a.member_profile_id for a in affs])
                )
            }
            for a in affs:
                member = by_id.get(a.member_profile_id)
                if member is not None and member.is_listed:
                    members.append((member, a.role_label))

    affs = (
        db.query(TeamAffiliation)
        .filter_by(member_profile_id=profile.id, status="accepted")
        .order_by(TeamAffiliation.sort_order, TeamAffiliation.id)
        .all()
    )
    if affs:
        by_id = {
            p.id: p
            for p in db.query(Profile).filter(
                Profile.id.in_([a.studio_profile_id for a in affs])
            )
        }
        for a in affs:
            studio = by_id.get(a.studio_profile_id)
            if studio is not None and studio.is_listed:
                studios.append((studio, a.role_label))

    from .community import get_rating_summary
    rating_summary = get_rating_summary(profile.id)
    published_reviews = (
        db.query(Review)
        .filter_by(profile_id=profile.id, status="published")
        .order_by(Review.created_at.desc()).all()
    )

    return render_template(
        "directory/profile.html",
        profile=profile,
        kind_label=KIND_LABELS.get(profile.kind, profile.kind),
        kind_labels=KIND_LABELS,
        members=members,
        studios=studios,
        flash_labels=FLASH_LABELS,
        rating_summary=rating_summary,
        published_reviews=published_reviews,
    )


# ---------------------------------------------------------------------------
# Artists & Studios by State — state hubs.
#
# The browse page is a directory discovery tool ("Artists & Studios by
# State"). Each state hub does double duty: the directory for that state
# (featured studio, studios, artists) AND that state's news and conventions.
# ---------------------------------------------------------------------------

ARTIST_KINDS = ("tattoo_artist", "piercer", "independent_artist")


def _category_label(category: str) -> str:
    return (category or "").replace("-", " ").title()


def _state_hub(db, code: str) -> dict | None:
    """Everything Inktrovert knows about one US state.

    Returns None for an unknown code. Sections: featured studio (where one
    is designated via Profile.featured_state), studios, artists, news,
    conventions.
    """
    code = (code or "").upper()
    if code not in US_STATES:
        return None
    featured = (
        db.query(Profile)
        .filter(Profile.is_listed.is_(True),
                Profile.featured_state == code)
        .order_by(Profile.display_name.asc())
        .first()
    )
    studios = [
        p for p in db.query(Profile)
        .filter(Profile.is_listed.is_(True),
                Profile.kind == "studio")
        .order_by(Profile.display_name.asc())
        .all()
        if normalize_state(p.state) == code
        and (featured is None or p.id != featured.id)
    ]
    artists = [
        p for p in db.query(Profile)
        .filter(Profile.is_listed.is_(True),
                Profile.kind.in_(ARTIST_KINDS))
        .order_by(Profile.display_name.asc())
        .all()
        if normalize_state(p.state) == code
    ]
    news = (
        db.query(Story)
        .filter(Story.is_published.is_(True),
                Story.state == code)
        .order_by(Story.published_at.desc(), Story.created_at.desc())
        .all()
    )
    conventions = [
        e for e in db.query(Event)
        .filter(Event.status == "approved")
        .order_by(Event.starts_at.asc())
        .all()
        if normalize_state(e.state) == code
    ]
    return {
        "code": code,
        "name": US_STATES[code],
        "featured": featured,
        "studios": studios,
        "artists": artists,
        "news": news,
        "conventions": conventions,
    }


def _states_with_listings(db) -> list[dict]:
    """States that have at least one listed studio or artist, with counts."""
    counts: dict[str, dict] = {}
    for p in db.query(Profile).filter(Profile.is_listed.is_(True)).all():
        code = normalize_state(p.state)
        if not code:
            continue
        entry = counts.setdefault(code, {"studios": 0, "artists": 0})
        if p.kind == "studio":
            entry["studios"] += 1
        elif p.kind in ARTIST_KINDS:
            entry["artists"] += 1
    result = []
    for code in sorted(counts, key=lambda c: US_STATES.get(c, c)):
        entry = counts[code]
        total = entry["studios"] + entry["artists"]
        if total:
            result.append({
                "code": code,
                "name": US_STATES.get(code, code),
                "studios": entry["studios"],
                "artists": entry["artists"],
                "total": total,
            })
    return result


@directory_bp.get("/by-state")
def by_state():
    """Browse: every state with Inktrovert studios/artists, and counts."""
    db = get_db()
    return render_template(
        "directory/by_state.html",
        states=_states_with_listings(db),
    )


@directory_bp.get("/by-state/<code>")
def state_hub(code: str):
    """One state's hub: featured studio, studios, artists, news, conventions."""
    db = get_db()
    hub = _state_hub(db, code)
    if hub is None:
        abort(404)
    return render_template("directory/state_hub.html",
                           category_label=_category_label, **hub)
