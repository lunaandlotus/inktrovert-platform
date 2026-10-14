"""Claim flow — find a listing, add a missing one, or claim ownership.

A signed-in user can:
  * search existing listings and file a claim on one (/claims/start),
  * create a listing that isn't here yet and automatically file a claim
    on it (/claims/new),
  * check the review status of their own claims (/claims and /claims/<id>).

Approval/rejection stays with the platform owner (app/owner.py); this
blueprint only files and tracks claims.
"""
from __future__ import annotations

import re

from flask import (Blueprint, abort, flash, redirect, render_template,
                   request, url_for)

from .auth import get_current_user, login_required, require_csrf
from .db import get_db
from .directory import KIND_LABELS
from .models import PROFILE_KINDS, ClaimRequest, Profile

claims_bp = Blueprint("claims", __name__, url_prefix="/claims")

RELATIONSHIP_CHOICES = (
    ("owner", "Owner"),
    ("manager", "Manager"),
    ("team_member", "Team member"),
    ("artist", "Artist"),
    ("brand_rep", "Brand representative"),
)
RELATIONSHIP_LABELS = dict(RELATIONSHIP_CHOICES)

CLAIM_STATUS_LABELS = {
    "pending": "Pending review",
    "approved": "Approved",
    "rejected": "Not approved",
}


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug or "listing"


def _unique_slug(db, base: str) -> str:
    slug, n = base, 2
    while db.query(Profile).filter_by(slug=slug).first() is not None:
        slug = f"{base}-{n}"
        n += 1
    return slug


def _csv_list(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


@claims_bp.get("/")
@login_required
def index():
    """GET /claims/ — explainer plus the signed-in user's own claim requests."""
    db = get_db()
    user = get_current_user()
    claims = (
        db.query(ClaimRequest)
        .filter_by(user_id=user.id)
        .order_by(ClaimRequest.created_at.desc())
        .all()
    )
    return render_template(
        "claims/index.html",
        claims=claims,
        status_labels=CLAIM_STATUS_LABELS,
        relationship_labels=RELATIONSHIP_LABELS,
    )


@claims_bp.get("/start")
def start():
    """GET /claims/start — search listings to claim, or create a missing one."""
    db = get_db()
    q = (request.args.get("q") or "").strip()
    results: list[Profile] = []
    if q:
        like = f"%{q}%"
        results = (
            db.query(Profile)
            .filter(Profile.is_listed.is_(True))
            .filter(
                (Profile.display_name.ilike(like))
                | (Profile.city.ilike(like))
                | (Profile.state.ilike(like))
            )
            .order_by(Profile.display_name.asc())
            .all()
        )
    return render_template("claims/start.html", q=q, results=results)


@claims_bp.route("/new", methods=["GET", "POST"])
@login_required
@require_csrf
def new_listing():
    """GET/POST /claims/new — add a missing listing and claim it in one step.

    The new profile is created with claim_status="pending" and a pending
    ClaimRequest is auto-filed for the creator.
    """
    if request.method == "POST":
        db = get_db()
        user = get_current_user()

        kind = (request.form.get("kind") or "").strip()
        display_name = (request.form.get("display_name") or "").strip()
        claimer_relationship = (request.form.get("claimer_relationship") or "").strip()

        errors: list[str] = []
        if kind not in PROFILE_KINDS:
            errors.append("Choose what kind of listing this is.")
        if not display_name:
            errors.append("Give the listing a name.")
        if claimer_relationship not in RELATIONSHIP_LABELS:
            errors.append("Tell us how you're connected to this listing.")

        if errors:
            for error in errors:
                flash(error, "error")
            return (
                render_template(
                    "claims/new.html",
                    form=request.form,
                    kind_labels=KIND_LABELS,
                    relationship_choices=RELATIONSHIP_CHOICES,
                ),
                400,
            )

        profile = Profile(
            kind=kind,
            display_name=display_name,
            slug=_unique_slug(db, _slugify(display_name)),
            bio=(request.form.get("bio") or "").strip(),
            city=(request.form.get("city") or "").strip(),
            state=(request.form.get("state") or "").strip(),
            specialties=_csv_list(request.form.get("specialties")),
            services=_csv_list(request.form.get("services")),
            claim_status="pending",
            is_listed=True,
            created_by_user_id=user.id,
        )
        db.add(profile)
        db.flush()  # assign profile.id before the claim row

        claim = ClaimRequest(
            profile_id=profile.id,
            user_id=user.id,
            claimer_relationship=claimer_relationship,
            evidence_text=(request.form.get("evidence_text") or "").strip(),
            status="pending",
        )
        db.add(claim)
        db.commit()

        flash("Listing created — your claim is in for review.", "success")
        return redirect(url_for("claims.claim_status", claim_id=claim.id))

    return render_template(
        "claims/new.html",
        form=None,
        kind_labels=KIND_LABELS,
        relationship_choices=RELATIONSHIP_CHOICES,
    )


@claims_bp.route("/for/<int:profile_id>", methods=["GET", "POST"])
@login_required
@require_csrf
def claim_profile(profile_id: int):
    """GET/POST /claims/for/<profile_id> — file a claim on an existing listing.

    One pending claim per user per profile: a repeat visit goes straight
    to the existing claim's status page.
    """
    db = get_db()
    user = get_current_user()

    profile = db.get(Profile, profile_id)
    if profile is None or not profile.is_listed:
        abort(404)

    existing = (
        db.query(ClaimRequest)
        .filter_by(profile_id=profile.id, user_id=user.id, status="pending")
        .one_or_none()
    )
    if existing is not None:
        return redirect(url_for("claims.claim_status", claim_id=existing.id))

    if request.method == "POST":
        claimer_relationship = (request.form.get("claimer_relationship") or "").strip()
        evidence_text = (request.form.get("evidence_text") or "").strip()

        if claimer_relationship not in RELATIONSHIP_LABELS:
            flash("Choose how you're connected to this listing.", "error")
            return (
                render_template(
                    "claims/claim_form.html",
                    profile=profile,
                    relationship_choices=RELATIONSHIP_CHOICES,
                ),
                400,
            )

        claim = ClaimRequest(
            profile_id=profile.id,
            user_id=user.id,
            claimer_relationship=claimer_relationship,
            evidence_text=evidence_text,
            status="pending",
        )
        db.add(claim)
        db.commit()

        flash("Claim submitted — the platform team will review it shortly.", "success")
        return redirect(url_for("claims.claim_status", claim_id=claim.id))

    return render_template(
        "claims/claim_form.html",
        profile=profile,
        relationship_choices=RELATIONSHIP_CHOICES,
    )


@claims_bp.get("/<int:claim_id>")
@login_required
def claim_status(claim_id: int):
    """GET /claims/<claim_id> — status of one claim. Owners only; 403 otherwise."""
    db = get_db()
    user = get_current_user()

    claim = db.get(ClaimRequest, claim_id)
    if claim is None:
        abort(404)
    if claim.user_id != user.id:
        abort(403)

    return render_template(
        "claims/detail.html",
        claim=claim,
        status_labels=CLAIM_STATUS_LABELS,
        relationship_labels=RELATIONSHIP_LABELS,
    )
