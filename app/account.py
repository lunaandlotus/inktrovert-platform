"""Account blueprint: register / login / logout / profile.

Endpoints (exact names — the app factory and other blueprints link to these):
    account.register   GET/POST /account/register
    account.login      GET/POST /account/login
    account.logout     GET      /account/logout
    account.profile    GET/POST /account/profile  (login required)

Auth mechanics live in app/auth.py — this blueprint only wires them to
routes and templates. No new hashing, session, or CSRF code here.
"""
from __future__ import annotations

from flask import (Blueprint, flash, redirect, render_template, request,
                   url_for)

from .auth import (create_login_session, get_current_user, login_required,
                   logout_current_session, register_user,
                   require_csrf, set_login_cookie, clear_login_cookie,
                   verify_password)
from .db import get_db
from .models import (ClaimRequest, Profile, TeamAffiliation, User,
                     UserSubscription, VALID_ROLES)

account_bp = Blueprint("account", __name__, url_prefix="/account")

# Pro roles offered as checkboxes on the registration form.
# "collector" is always granted and is not offered as a checkbox.
PRO_ROLE_CHOICES = (
    ("tattoo_artist", "Tattoo artist"),
    ("piercer", "Piercer"),
    ("independent_artist", "Independent artist"),
    ("studio_owner", "Studio owner"),
    ("studio_manager", "Studio manager"),
    ("studio_team_member", "Studio team member"),
    ("approved_brand", "Brand / supplier"),
)
PRO_ROLE_NAMES = {name for name, _ in PRO_ROLE_CHOICES}


def _safe_next(value: str | None) -> str | None:
    """Only allow relative redirect targets (no open redirects)."""
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return None


@account_bp.route("/register", methods=["GET", "POST"])
@require_csrf
def register():
    """Create an account. Everyone is a collector; pro roles are optional."""
    if get_current_user() is not None:
        return redirect(url_for("account.profile"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        full_name = (request.form.get("full_name") or "").strip()
        roles = ["collector"] + [
            r for r in request.form.getlist("roles") if r in PRO_ROLE_NAMES
        ]

        if len(password) < 8:
            flash("Passwords need to be at least 8 characters.", "error")
            return render_template("account/register.html",
                                   pro_roles=PRO_ROLE_CHOICES,
                                   email=email, full_name=full_name)

        try:
            user = register_user(email=email, password=password,
                                 full_name=full_name, roles=roles)
        except ValueError as exc:
            msg = str(exc)
            if "already exists" in msg:
                flash("There's already an account for that email. "
                      "Try signing in instead.", "error")
            else:
                flash(f"We couldn't create your account: {msg}", "error")
            return render_template("account/register.html",
                                   pro_roles=PRO_ROLE_CHOICES,
                                   email=email, full_name=full_name)

        token = create_login_session(user)
        flash(f"Welcome aboard{', ' + user.full_name if user.full_name else ''}. "
              "You're signed in.", "success")
        resp = redirect(url_for("account.profile"))
        return set_login_cookie(resp, token)

    return render_template("account/register.html",
                           pro_roles=PRO_ROLE_CHOICES,
                           email="", full_name="")


@account_bp.route("/login", methods=["GET", "POST"])
@require_csrf
def login():
    """Sign in with email + password. Generic error either way."""
    if get_current_user() is not None:
        return redirect(_safe_next(request.args.get("next"))
                        or url_for("account.profile"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        user = get_db().query(User).filter_by(email=email).first()
        if user is None or not user.is_active or \
                not verify_password(user.password_hash, password):
            # One message on purpose: don't say which half was wrong.
            flash("That email and password don't match.", "error")
            return render_template("account/login.html", email=email,
                                   next=request.args.get("next") or "")

        token = create_login_session(user)
        dest = _safe_next(request.args.get("next")) or url_for("public.home")
        resp = redirect(dest)
        return set_login_cookie(resp, token)

    return render_template("account/login.html", email="",
                           next=request.args.get("next") or "")


@account_bp.route("/logout")
def logout():
    """Sign out the current device, clear the cookie, back to the magazine."""
    logout_current_session()
    resp = redirect(url_for("public.home"))
    clear_login_cookie(resp)
    flash("You've been signed out. See you next time.", "success")
    return resp


@account_bp.route("/profile", methods=["GET", "POST"])
@login_required
@require_csrf
def profile():
    """Show the member's account: identity, roles, claims, membership."""
    user = get_current_user()
    db = get_db()

    if request.method == "POST":
        full_name = (request.form.get("full_name") or "").strip()
        user.full_name = full_name
        db.commit()
        flash("Your name's been updated.", "success")
        return redirect(url_for("account.profile"))

    # Re-fetch in this request's session so relationships are fresh.
    db.expire_all()
    claims = (db.query(ClaimRequest)
              .filter_by(user_id=user.id)
              .order_by(ClaimRequest.created_at.desc()).all())
    subscriptions = (db.query(UserSubscription)
                     .filter_by(user_id=user.id)
                     .order_by(UserSubscription.id.desc()).all())

    # Listings this user manages (claimed by them) — entry to /manage/<slug>.
    managed = (db.query(Profile)
               .filter_by(claimed_by_user_id=user.id, is_listed=True)
               .order_by(Profile.display_name.asc()).all())

    # Roster invites + memberships for the artist profiles this user owns.
    my_profile_ids = [p.id for p in managed]
    pending_invites: list[TeamAffiliation] = []
    memberships: list[TeamAffiliation] = []
    if my_profile_ids:
        rows = (db.query(TeamAffiliation)
                .filter(TeamAffiliation.member_profile_id.in_(my_profile_ids),
                        TeamAffiliation.status.in_(("pending", "accepted")))
                .order_by(TeamAffiliation.created_at.desc()).all())
        by_id = {p.id: p for p in
                 db.query(Profile).filter(Profile.id.in_(
                     [a.studio_profile_id for a in rows]
                     + [a.member_profile_id for a in rows])).all()}
        for a in rows:
            studio = by_id.get(a.studio_profile_id)
            member = by_id.get(a.member_profile_id)
            if studio is None or member is None:
                continue
            if a.status == "pending":
                pending_invites.append((a, studio, member))
            else:
                memberships.append((a, studio, member))

    return render_template("account/profile.html",
                           claims=claims,
                           subscriptions=subscriptions,
                           managed=managed,
                           pending_invites=pending_invites,
                           memberships=memberships)
