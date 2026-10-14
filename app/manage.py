"""Profile management — the owner's desk for a claimed listing.

A signed-in user who owns a profile (claimed_by_user_id, or the platform
owner) can:
  * run a studio roster: invite artist profiles (they accept or decline —
    no false claims), cancel invites, remove artists;
  * manage the profile's link list (label + URL: socials, website, shop…).

Artists handle their side from their account page: pending roster invites
(accept/decline) and leaving a studio roster any time.
"""
from __future__ import annotations

from flask import (Blueprint, abort, flash, redirect, render_template,
                   request, url_for)

from .auth import get_current_user, login_required, require_csrf
from .db import get_db
from .models import AFFILIATION_STATUSES, Profile, ProfileLink, TeamAffiliation, utcnow

manage_bp = Blueprint("manage", __name__, url_prefix="/manage")

# Profile kinds that can be invited onto a studio roster.
ARTIST_KINDS = ("tattoo_artist", "piercer", "independent_artist")

STATUS_LABELS = {
    "pending": "Invite pending",
    "accepted": "On the roster",
    "declined": "Declined",
}


def _can_manage_profile(user, profile: Profile) -> bool:
    """Profile owner/manager, or the platform owner, may edit the listing."""
    if user is None or profile is None:
        return False
    if user.has_role("platform_owner"):
        return True
    return (profile.claimed_by_user_id is not None
            and profile.claimed_by_user_id == user.id)


def _get_managed_profile(db, slug: str) -> Profile:
    profile = db.query(Profile).filter_by(slug=slug, is_listed=True).one_or_none()
    if profile is None:
        abort(404)
    if not _can_manage_profile(get_current_user(), profile):
        abort(403)
    return profile


def _affiliation_or_404(db, aff_id: int) -> TeamAffiliation:
    aff = db.get(TeamAffiliation, aff_id)
    if aff is None:
        abort(404)
    return aff


def _normalize_url(url: str) -> str:
    url = (url or "").strip()
    if url and "://" not in url:
        url = "https://" + url
    return url


@manage_bp.get("/<slug>")
@login_required
def dashboard(slug: str):
    """GET /manage/<slug> — roster + links desk for one listing."""
    db = get_db()
    profile = _get_managed_profile(db, slug)

    roster: list[TeamAffiliation] = []
    pending: list[TeamAffiliation] = []
    if profile.kind == "studio":
        affs = (db.query(TeamAffiliation)
                .filter_by(studio_profile_id=profile.id)
                .order_by(TeamAffiliation.status,
                          TeamAffiliation.sort_order,
                          TeamAffiliation.id).all())
        roster = [a for a in affs if a.status == "accepted"]
        pending = [a for a in affs if a.status == "pending"]

    links = (db.query(ProfileLink)
             .filter_by(profile_id=profile.id)
             .order_by(ProfileLink.sort_order, ProfileLink.id).all())

    members_by_id: dict[int, Profile] = {}
    if roster or pending:
        ids = [a.member_profile_id for a in roster + pending]
        members_by_id = {p.id: p for p in
                         db.query(Profile).filter(Profile.id.in_(ids)).all()}

    # Artist search for invites (studio only).
    q = (request.args.get("q") or "").strip()
    candidates: list[Profile] = []
    if profile.kind == "studio" and q:
        like = f"%{q}%"
        taken = {a.member_profile_id for a in
                 db.query(TeamAffiliation)
                 .filter_by(studio_profile_id=profile.id).all()}
        candidates = (
            db.query(Profile)
            .filter(Profile.is_listed.is_(True),
                    Profile.kind.in_(ARTIST_KINDS),
                    Profile.id != profile.id,
                    ~Profile.id.in_(taken) if taken else True,
                    (Profile.display_name.ilike(like)
                     | Profile.city.ilike(like)))
            .order_by(Profile.display_name.asc())
            .limit(20).all()
        )

    return render_template(
        "manage/dashboard.html",
        profile=profile,
        roster=roster,
        pending=pending,
        members_by_id=members_by_id,
        links=links,
        q=q,
        candidates=candidates,
        status_labels=STATUS_LABELS,
    )


@manage_bp.post("/<slug>/roster/invite")
@login_required
@require_csrf
def roster_invite(slug: str):
    """Invite an artist profile onto this studio's roster (starts pending)."""
    db = get_db()
    studio = _get_managed_profile(db, slug)
    if studio.kind != "studio":
        abort(404)

    member_id = request.form.get("member_profile_id", "")
    try:
        member_id = int(member_id)
    except (TypeError, ValueError):
        flash("Pick an artist to invite.", "error")
        return redirect(url_for("manage.dashboard", slug=slug,
                                q=request.form.get("q", "")))

    member = db.get(Profile, member_id)
    if (member is None or not member.is_listed
            or member.kind not in ARTIST_KINDS or member.id == studio.id):
        flash("That artist can't be invited.", "error")
        return redirect(url_for("manage.dashboard", slug=slug))

    existing = (db.query(TeamAffiliation)
                .filter_by(studio_profile_id=studio.id,
                           member_profile_id=member.id).one_or_none())
    if existing is not None:
        if existing.status == "pending":
            flash(f"{member.display_name} already has a pending invite.", "info")
        elif existing.status == "accepted":
            flash(f"{member.display_name} is already on the roster.", "info")
        else:  # declined before — let the studio ask again, fresh
            existing.status = "pending"
            existing.decided_at = None
            existing.invited_by_user_id = get_current_user().id
            existing.role_label = (request.form.get("role_label") or "").strip()
            db.commit()
            flash(f"Invite re-sent to {member.display_name}.", "success")
        return redirect(url_for("manage.dashboard", slug=slug))

    db.add(TeamAffiliation(
        studio_profile_id=studio.id,
        member_profile_id=member.id,
        role_label=(request.form.get("role_label") or "").strip(),
        status="pending",
        invited_by_user_id=get_current_user().id,
    ))
    db.commit()
    flash(f"Invite sent to {member.display_name} — they'll accept or decline it.",
          "success")
    return redirect(url_for("manage.dashboard", slug=slug))


@manage_bp.post("/roster/<int:aff_id>/cancel")
@login_required
@require_csrf
def roster_cancel(aff_id: int):
    """Studio takes back a pending invite. No trace left behind."""
    db = get_db()
    aff = _affiliation_or_404(db, aff_id)
    studio = db.get(Profile, aff.studio_profile_id)
    if not _can_manage_profile(get_current_user(), studio):
        abort(403)
    if aff.status != "pending":
        flash("Only a pending invite can be cancelled.", "error")
        return redirect(url_for("manage.dashboard", slug=studio.slug))
    name = db.get(Profile, aff.member_profile_id).display_name
    db.delete(aff)
    db.commit()
    flash(f"Invite to {name} cancelled.", "success")
    return redirect(url_for("manage.dashboard", slug=studio.slug))


@manage_bp.post("/roster/<int:aff_id>/remove")
@login_required
@require_csrf
def roster_remove(aff_id: int):
    """Studio removes an artist from the roster. Immediate, no approval."""
    db = get_db()
    aff = _affiliation_or_404(db, aff_id)
    studio = db.get(Profile, aff.studio_profile_id)
    if not _can_manage_profile(get_current_user(), studio):
        abort(403)
    name = db.get(Profile, aff.member_profile_id).display_name
    db.delete(aff)
    db.commit()
    flash(f"{name} removed from the roster.", "success")
    return redirect(url_for("manage.dashboard", slug=studio.slug))


def _artist_side_permission(db, aff: TeamAffiliation) -> Profile | None:
    """The member profile, if the signed-in user may act for the artist.

    Returns the member Profile when allowed, else None. Allowed: the user
    who claimed the member profile, or the platform owner.
    """
    user = get_current_user()
    member = db.get(Profile, aff.member_profile_id)
    if member is None:
        return None
    if user.has_role("platform_owner"):
        return member
    if (member.claimed_by_user_id is not None
            and member.claimed_by_user_id == user.id):
        return member
    return None


@manage_bp.post("/roster/<int:aff_id>/accept")
@login_required
@require_csrf
def roster_accept(aff_id: int):
    """The invited artist accepts a studio roster invite."""
    db = get_db()
    aff = _affiliation_or_404(db, aff_id)
    if _artist_side_permission(db, aff) is None:
        abort(403)
    if aff.status != "pending":
        flash("That invite isn't pending any more.", "error")
        return redirect(url_for("account.profile"))
    aff.status = "accepted"
    aff.decided_at = utcnow()
    db.commit()
    studio = db.get(Profile, aff.studio_profile_id)
    flash(f"You're on the roster at {studio.display_name}.", "success")
    return redirect(url_for("account.profile"))


@manage_bp.post("/roster/<int:aff_id>/decline")
@login_required
@require_csrf
def roster_decline(aff_id: int):
    """The invited artist declines. The invite is recorded, not shown."""
    db = get_db()
    aff = _affiliation_or_404(db, aff_id)
    if _artist_side_permission(db, aff) is None:
        abort(403)
    if aff.status != "pending":
        flash("That invite isn't pending any more.", "error")
        return redirect(url_for("account.profile"))
    aff.status = "declined"
    aff.decided_at = utcnow()
    db.commit()
    flash("Invite declined — no hard feelings.", "success")
    return redirect(url_for("account.profile"))


@manage_bp.post("/roster/<int:aff_id>/leave")
@login_required
@require_csrf
def roster_leave(aff_id: int):
    """The artist leaves a studio roster on their own, any time."""
    db = get_db()
    aff = _affiliation_or_404(db, aff_id)
    member = _artist_side_permission(db, aff)
    if member is None:
        abort(403)
    if aff.status != "accepted":
        flash("You're not on that roster.", "error")
        return redirect(url_for("account.profile"))
    studio = db.get(Profile, aff.studio_profile_id)
    db.delete(aff)
    db.commit()
    flash(f"You've left the roster at {studio.display_name}.", "success")
    return redirect(url_for("account.profile"))


@manage_bp.post("/<slug>/links/add")
@login_required
@require_csrf
def link_add(slug: str):
    """Add a link/social to the profile's link list."""
    db = get_db()
    profile = _get_managed_profile(db, slug)

    label = (request.form.get("label") or "").strip()
    url = _normalize_url(request.form.get("url"))
    if not label or not url:
        flash("Give the link a label and a URL.", "error")
        return redirect(url_for("manage.dashboard", slug=slug))
    if not (url.startswith("http://") or url.startswith("https://")):
        flash("That doesn't look like a web address.", "error")
        return redirect(url_for("manage.dashboard", slug=slug))

    max_sort = (db.query(ProfileLink.sort_order)
                .filter_by(profile_id=profile.id)
                .order_by(ProfileLink.sort_order.desc()).first())
    db.add(ProfileLink(
        profile_id=profile.id, label=label, url=url,
        sort_order=(max_sort[0] + 1) if max_sort else 0,
    ))
    db.commit()
    flash(f"“{label}” added to {profile.display_name}'s links.", "success")
    return redirect(url_for("manage.dashboard", slug=slug))


@manage_bp.post("/links/<int:link_id>/remove")
@login_required
@require_csrf
def link_remove(link_id: int):
    """Remove a link from the profile's link list."""
    db = get_db()
    link = db.get(ProfileLink, link_id)
    if link is None:
        abort(404)
    profile = db.get(Profile, link.profile_id)
    if not _can_manage_profile(get_current_user(), profile):
        abort(403)
    label = link.label
    db.delete(link)
    db.commit()
    flash(f"“{label}” removed.", "success")
    return redirect(url_for("manage.dashboard", slug=profile.slug))
