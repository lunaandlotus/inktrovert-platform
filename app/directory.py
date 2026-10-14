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
from .models import PROFILE_KINDS, Profile, TeamAffiliation

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
            .filter_by(studio_profile_id=profile.id)
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
        .filter_by(member_profile_id=profile.id)
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

    return render_template(
        "directory/profile.html",
        profile=profile,
        kind_label=KIND_LABELS.get(profile.kind, profile.kind),
        kind_labels=KIND_LABELS,
        members=members,
        studios=studios,
        flash_labels=FLASH_LABELS,
    )
