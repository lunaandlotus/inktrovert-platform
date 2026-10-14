"""Phase 4 — community: reviews, inquiries, and the booking handoff.

Collectors review artist/studio profiles (moderated by the platform owner),
message profiles through inquiries, and request bookings where the pro has
switched platform booking on. All pro-side views are fenced: a user only
ever sees inquiries for profiles they own/manage — or everything, when they
are the platform owner. Pending and hidden reviews never render publicly.

New tables (see models below): inquiry_replies, pro_booking_settings.
Owner admin (platform_owner only): /community/admin/reviews — the review
moderation queue with pending/published/hidden tabs and full per-review
management (view, edit body, publish, hide, delete).
Registration of this blueprint in app/__init__.py is left to the parent.
"""
from __future__ import annotations

from datetime import datetime

from flask import (Blueprint, abort, flash, redirect, render_template,
                   request, url_for)
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .auth import get_current_user, login_required, require_csrf, role_required
from .db import get_db
from .models import Base, BookingInquiry, Profile, Review, User, utcnow

community_bp = Blueprint("community", __name__, url_prefix="/community")


# ---------------------------------------------------------------------------
# Phase 4 models
# ---------------------------------------------------------------------------

class InquiryReply(Base):
    """One message inside a BookingInquiry thread, from either side."""
    __tablename__ = "inquiry_replies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inquiry_id: Mapped[int] = mapped_column(
        ForeignKey("booking_inquiries.id", ondelete="CASCADE"),
        nullable=False, index=True)
    sender_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=utcnow, nullable=False)

    inquiry: Mapped[BookingInquiry] = relationship("BookingInquiry")
    sender: Mapped[User] = relationship("User")


class ProBookingSettings(Base):
    """Per-profile switch for platform booking requests.

    Off by default. When on, collectors can send booking requests that the
    pro confirms or declines from the inbox. Profile.booking_mode mirrors
    the switch so public templates can read it without a join.
    """
    __tablename__ = "pro_booking_settings"
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True)
    platform_booking_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=utcnow, onupdate=utcnow,
                                                 nullable=False)

    profile: Mapped[Profile] = relationship("Profile")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REVIEW_STATUSES = ("pending", "published", "hidden")
INQUIRY_MODE_LABELS = {"inquiry": "Inquiry", "platform": "Booking request",
                       "external": "External"}
INQUIRY_STATUS_LABELS = {"open": "Open", "confirmed": "Confirmed",
                         "declined": "Declined", "closed": "Closed"}


def get_rating_summary(profile_id: int) -> tuple[float, int]:
    """(average rating, published review count) for a profile.

    Only "published" reviews count — pending and hidden ones never shape
    the public number. Returns (0.0, 0) when there are no published reviews.
    """
    db = get_db()
    avg, count = (
        db.query(func.avg(Review.rating), func.count(Review.id))
        .filter(Review.profile_id == profile_id,
                Review.status == "published")
        .one()
    )
    if not count:
        return 0.0, 0
    return round(float(avg), 1), int(count)


def _profile_or_404(slug: str) -> Profile:
    profile = db_query_profile(slug)
    if profile is None:
        abort(404)
    return profile


def db_query_profile(slug: str) -> Profile | None:
    return (get_db().query(Profile)
            .filter_by(slug=slug, is_listed=True).one_or_none())


def _can_manage_profile(user, profile: Profile) -> bool:
    """Profile owner/manager, or the platform owner, may act for the listing.

    Same permission pattern as the manage desk (app/manage.py).
    """
    if user is None or profile is None:
        return False
    if user.has_role("platform_owner"):
        return True
    return (profile.claimed_by_user_id is not None
            and profile.claimed_by_user_id == user.id)


def _pro_inquiry_or_403(inquiry_id: int) -> BookingInquiry:
    """A BookingInquiry the signed-in pro may see, else 403/404."""
    db = get_db()
    inquiry = db.get(BookingInquiry, inquiry_id)
    if inquiry is None:
        abort(404)
    profile = db.get(Profile, inquiry.profile_id)
    if not _can_manage_profile(get_current_user(), profile):
        abort(403)
    return inquiry


def _booking_settings(db, profile: Profile) -> ProBookingSettings:
    settings = db.get(ProBookingSettings, profile.id)
    if settings is None:
        settings = ProBookingSettings(profile_id=profile.id,
                                      platform_booking_enabled=False)
        db.add(settings)
        db.flush()
    return settings


def _users_by_id(db, user_ids: set[int]) -> dict[int, User]:
    if not user_ids:
        return {}
    return {u.id: u for u in
            db.query(User).filter(User.id.in_(user_ids)).all()}


def _display_name(users: dict[int, User], user_id: int) -> str:
    user = users.get(user_id)
    if user is None:
        return "A collector"
    return user.full_name or "A collector"


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------

@community_bp.route("/profiles/<slug>/review", methods=["GET", "POST"])
@login_required
def review(slug: str):
    """Collector writes (or updates) a review of a profile. Enters "pending"."""
    db = get_db()
    profile = _profile_or_404(slug)
    user = get_current_user()
    existing = (db.query(Review)
                .filter_by(profile_id=profile.id, user_id=user.id)
                .one_or_none())

    if request.method == "POST":
        try:
            rating = int(request.form.get("rating", "") or 0)
        except (TypeError, ValueError):
            rating = 0
        body = (request.form.get("body") or "").strip()
        if rating not in (1, 2, 3, 4, 5):
            flash("Pick a rating between 1 and 5 stars.", "error")
            return redirect(url_for("community.review", slug=slug))
        if not body:
            flash("Write a few words about your experience.", "error")
            return redirect(url_for("community.review", slug=slug))

        if existing is None:
            db.add(Review(profile_id=profile.id, user_id=user.id,
                          rating=rating, body=body, status="pending"))
            db.commit()
            flash(f"Thanks — your review of {profile.display_name} is in "
                  "the moderation queue.", "success")
        else:
            # One review per user per profile: update in place and re-moderate.
            existing.rating = rating
            existing.body = body
            existing.status = "pending"
            db.commit()
            flash("Review updated — it's back in the moderation queue.",
                  "success")
        return redirect(url_for("community.reviews", slug=slug))

    return render_template("community/review_form.html",
                           profile=profile, existing=existing)


@community_bp.get("/profiles/<slug>/reviews")
def reviews(slug: str):
    """Public reviews page. Only "published" reviews ever show."""
    db = get_db()
    profile = _profile_or_404(slug)
    published = (db.query(Review)
                 .filter_by(profile_id=profile.id, status="published")
                 .order_by(Review.created_at.desc()).all())
    avg, count = get_rating_summary(profile.id)
    users = _users_by_id(db, {r.user_id for r in published})
    my_review = None
    user = get_current_user()
    if user is not None:
        my_review = (db.query(Review)
                     .filter_by(profile_id=profile.id, user_id=user.id)
                     .one_or_none())
    return render_template(
        "community/reviews.html",
        profile=profile, reviews=published, avg=avg, count=count,
        users=users, display_name=_display_name, my_review=my_review,
    )


@community_bp.get("/moderate")
@role_required("platform_owner")
def moderate():
    """Legacy entry point — the moderation queue now lives in the admin
    section below. Kept as a redirect so old links don't break."""
    return redirect(url_for("community.admin_reviews", status="pending"))


@community_bp.post("/moderate/<int:review_id>/approve")
@role_required("platform_owner")
@require_csrf
def review_approve(review_id: int):
    db = get_db()
    review = db.get(Review, review_id)
    if review is None:
        abort(404)
    review.status = "published"
    db.commit()
    flash("Review published.", "success")
    return redirect(url_for("community.admin_reviews", status="pending"))


@community_bp.post("/moderate/<int:review_id>/reject")
@role_required("platform_owner")
@require_csrf
def review_reject(review_id: int):
    db = get_db()
    review = db.get(Review, review_id)
    if review is None:
        abort(404)
    review.status = "hidden"
    db.commit()
    flash("Review rejected — it stays hidden.", "info")
    return redirect(url_for("community.admin_reviews", status="pending"))


# ---------------------------------------------------------------------------
# Owner admin — review management ("editable by me")
# ---------------------------------------------------------------------------

ADMIN_REVIEW_STATUSES = ("pending", "published", "hidden")


def _admin_review_or_404(review_id: int) -> Review:
    review = get_db().get(Review, review_id)
    if review is None:
        abort(404)
    return review


@community_bp.get("/admin/reviews")
@role_required("platform_owner")
def admin_reviews():
    """Owner moderation queue with pending / published / hidden tabs."""
    db = get_db()
    status = request.args.get("status", "pending")
    if status not in ADMIN_REVIEW_STATUSES:
        status = "pending"
    counts = {s: db.query(Review).filter_by(status=s).count()
              for s in ADMIN_REVIEW_STATUSES}
    order = (Review.created_at.asc() if status == "pending"
             else Review.created_at.desc())
    rows = (db.query(Review).filter_by(status=status)
            .order_by(order).all())
    profiles = {p.id: p for p in db.query(Profile).filter(
        Profile.id.in_([r.profile_id for r in rows])).all()} if rows else {}
    users = _users_by_id(db, {r.user_id for r in rows})
    return render_template(
        "community/admin/reviews.html", status=status, counts=counts,
        reviews=rows, profiles=profiles, users=users,
        display_name=_display_name, statuses=ADMIN_REVIEW_STATUSES,
    )


@community_bp.route("/admin/reviews/<int:review_id>",
                    methods=["GET", "POST"])
@role_required("platform_owner")
def admin_review_detail(review_id: int):
    """View any review, edit its body, publish / hide / delete it."""
    db = get_db()
    review = _admin_review_or_404(review_id)
    profile = db.get(Profile, review.profile_id)
    users = _users_by_id(db, {review.user_id})

    if request.method == "POST":
        body = (request.form.get("body") or "").strip()
        if not body:
            flash("The review needs some text to keep.", "error")
            return redirect(url_for("community.admin_review_detail",
                                    review_id=review.id))
        review.body = body
        db.commit()
        flash("Review updated.", "success")
        return redirect(url_for("community.admin_review_detail",
                                review_id=review.id))

    return render_template(
        "community/admin/review_detail.html", review=review, profile=profile,
        users=users, display_name=_display_name,
    )


@community_bp.post("/admin/reviews/<int:review_id>/publish")
@role_required("platform_owner")
@require_csrf
def admin_review_publish(review_id: int):
    review = _admin_review_or_404(review_id)
    review.status = "published"
    get_db().commit()
    flash("Review published — it's live on the profile page.", "success")
    return redirect(url_for("community.admin_review_detail",
                            review_id=review.id))


@community_bp.post("/admin/reviews/<int:review_id>/hide")
@role_required("platform_owner")
@require_csrf
def admin_review_hide(review_id: int):
    review = _admin_review_or_404(review_id)
    review.status = "hidden"
    get_db().commit()
    flash("Review hidden — it's off the public page but not deleted. "
          "You can publish it again any time.", "info")
    return redirect(url_for("community.admin_review_detail",
                            review_id=review.id))


@community_bp.post("/admin/reviews/<int:review_id>/delete")
@role_required("platform_owner")
@require_csrf
def admin_review_delete(review_id: int):
    review = _admin_review_or_404(review_id)
    if request.form.get("confirm") != "yes":
        flash("Tick the confirmation box to delete — deletes can't be undone.",
              "error")
        return redirect(url_for("community.admin_review_detail",
                                review_id=review.id))
    db = get_db()
    db.delete(review)
    db.commit()
    flash("Review deleted permanently.", "info")
    return redirect(url_for("community.admin_reviews", status="hidden"))


# ---------------------------------------------------------------------------
# Inquiries
# ---------------------------------------------------------------------------

@community_bp.route("/profiles/<slug>/inquire", methods=["GET", "POST"])
@login_required
def inquire(slug: str):
    """Collector sends a plain inquiry to a profile. mode="inquiry"."""
    db = get_db()
    profile = _profile_or_404(slug)
    user = get_current_user()

    if request.method == "POST":
        message = (request.form.get("message") or "").strip()
        if not message:
            flash("Write your message first.", "error")
            return redirect(url_for("community.inquire", slug=slug))
        inquiry = BookingInquiry(profile_id=profile.id, user_id=user.id,
                                 message=message, mode="inquiry",
                                 status="open")
        db.add(inquiry)
        db.commit()
        flash(f"Message sent to {profile.display_name}. They'll reply here.",
              "success")
        return redirect(url_for("community.my_inquiry_thread",
                                inquiry_id=inquiry.id))

    return render_template("community/inquire.html", profile=profile)


@community_bp.get("/inbox")
@login_required
def inbox():
    """Pro inbox: inquiries for profiles the user owns/manages.

    Never leaks across pros — the query is fenced to the signed-in user's
    claimed profiles (the platform owner sees everything).
    """
    db = get_db()
    user = get_current_user()
    query = db.query(BookingInquiry)
    if not user.has_role("platform_owner"):
        query = (query.join(Profile,
                            BookingInquiry.profile_id == Profile.id)
                 .filter(Profile.claimed_by_user_id == user.id))
    inquiries = query.order_by(BookingInquiry.created_at.desc()).all()
    profiles = {p.id: p for p in db.query(Profile).filter(
        Profile.id.in_([i.profile_id for i in inquiries])).all()} if inquiries else {}
    users = _users_by_id(db, {i.user_id for i in inquiries})
    return render_template("community/inbox.html", inquiries=inquiries,
                           profiles=profiles, users=users,
                           display_name=_display_name,
                           mode_labels=INQUIRY_MODE_LABELS,
                           status_labels=INQUIRY_STATUS_LABELS)


@community_bp.route("/inbox/<int:inquiry_id>", methods=["GET", "POST"])
@login_required
def inbox_thread(inquiry_id: int):
    """Pro reads a thread and replies. Replies notify the thread inline."""
    db = get_db()
    user = get_current_user()
    inquiry = _pro_inquiry_or_403(inquiry_id)
    profile = db.get(Profile, inquiry.profile_id)

    if request.method == "POST":
        body = (request.form.get("body") or "").strip()
        if not body:
            flash("Write your reply first.", "error")
            return redirect(url_for("community.inbox_thread",
                                    inquiry_id=inquiry.id))
        db.add(InquiryReply(inquiry_id=inquiry.id, sender_user_id=user.id,
                            body=body))
        db.commit()
        flash("Reply sent — the collector sees it in their inbox.", "success")
        return redirect(url_for("community.inbox_thread",
                                inquiry_id=inquiry.id))

    replies = (db.query(InquiryReply)
               .filter_by(inquiry_id=inquiry.id)
               .order_by(InquiryReply.created_at.asc()).all())
    sender_ids = {inquiry.user_id} | {r.sender_user_id for r in replies}
    users = _users_by_id(db, sender_ids)
    return render_template(
        "community/inbox_thread.html", inquiry=inquiry, profile=profile,
        replies=replies, users=users, display_name=_display_name,
        mode_labels=INQUIRY_MODE_LABELS, status_labels=INQUIRY_STATUS_LABELS,
    )


@community_bp.post("/inbox/<int:inquiry_id>/close")
@login_required
@require_csrf
def inbox_close(inquiry_id: int):
    inquiry = _pro_inquiry_or_403(inquiry_id)
    inquiry.status = "closed"
    get_db().commit()
    flash("Thread closed.", "info")
    return redirect(url_for("community.inbox_thread", inquiry_id=inquiry.id))


@community_bp.post("/inbox/<int:inquiry_id>/confirm")
@login_required
@require_csrf
def inbox_confirm(inquiry_id: int):
    """Pro confirms a platform booking request from the thread."""
    inquiry = _pro_inquiry_or_403(inquiry_id)
    if inquiry.mode != "platform" or inquiry.status != "open":
        flash("Only an open booking request can be confirmed.", "error")
        return redirect(url_for("community.inbox_thread",
                                inquiry_id=inquiry.id))
    inquiry.status = "confirmed"
    get_db().commit()
    flash("Booking confirmed.", "success")
    return redirect(url_for("community.inbox_thread", inquiry_id=inquiry.id))


@community_bp.post("/inbox/<int:inquiry_id>/decline")
@login_required
@require_csrf
def inbox_decline(inquiry_id: int):
    """Pro declines a platform booking request from the thread."""
    inquiry = _pro_inquiry_or_403(inquiry_id)
    if inquiry.mode != "platform" or inquiry.status != "open":
        flash("Only an open booking request can be declined.", "error")
        return redirect(url_for("community.inbox_thread",
                                inquiry_id=inquiry.id))
    inquiry.status = "declined"
    get_db().commit()
    flash("Booking declined.", "info")
    return redirect(url_for("community.inbox_thread", inquiry_id=inquiry.id))


@community_bp.get("/my-inquiries")
@login_required
def my_inquiries():
    """Collector sees only their own threads."""
    db = get_db()
    user = get_current_user()
    inquiries = (db.query(BookingInquiry)
                 .filter_by(user_id=user.id)
                 .order_by(BookingInquiry.created_at.desc()).all())
    profiles = {p.id: p for p in db.query(Profile).filter(
        Profile.id.in_([i.profile_id for i in inquiries])).all()} if inquiries else {}
    return render_template("community/my_inquiries.html", inquiries=inquiries,
                           profiles=profiles, mode_labels=INQUIRY_MODE_LABELS,
                           status_labels=INQUIRY_STATUS_LABELS)


@community_bp.route("/my-inquiries/<int:inquiry_id>", methods=["GET", "POST"])
@login_required
def my_inquiry_thread(inquiry_id: int):
    """Collector reads their own thread and can reply in it."""
    db = get_db()
    user = get_current_user()
    inquiry = db.get(BookingInquiry, inquiry_id)
    if inquiry is None or inquiry.user_id != user.id:
        abort(404)
    profile = db.get(Profile, inquiry.profile_id)

    if request.method == "POST":
        body = (request.form.get("body") or "").strip()
        if not body:
            flash("Write your message first.", "error")
            return redirect(url_for("community.my_inquiry_thread",
                                    inquiry_id=inquiry.id))
        db.add(InquiryReply(inquiry_id=inquiry.id, sender_user_id=user.id,
                            body=body))
        db.commit()
        flash("Message sent.", "success")
        return redirect(url_for("community.my_inquiry_thread",
                                inquiry_id=inquiry.id))

    replies = (db.query(InquiryReply)
               .filter_by(inquiry_id=inquiry.id)
               .order_by(InquiryReply.created_at.asc()).all())
    sender_ids = {inquiry.user_id} | {r.sender_user_id for r in replies}
    users = _users_by_id(db, sender_ids)
    return render_template(
        "community/my_inquiry_thread.html", inquiry=inquiry, profile=profile,
        replies=replies, users=users, display_name=_display_name,
        mode_labels=INQUIRY_MODE_LABELS, status_labels=INQUIRY_STATUS_LABELS,
    )


# ---------------------------------------------------------------------------
# Booking handoff
# ---------------------------------------------------------------------------

@community_bp.route("/profiles/<slug>/book", methods=["GET", "POST"])
@login_required
def book(slug: str):
    """Collector requests a booking (date, time, service notes).

    Only available when the pro switched platform booking on; otherwise the
    collector is steered to the inquiry form.
    """
    db = get_db()
    profile = _profile_or_404(slug)
    user = get_current_user()
    settings = _booking_settings(db, profile)
    if not settings.platform_booking_enabled:
        flash("Platform booking isn't switched on for this profile — "
              "send them an inquiry instead.", "info")
        return redirect(url_for("community.inquire", slug=slug))

    if request.method == "POST":
        date = (request.form.get("date") or "").strip()
        time = (request.form.get("time") or "").strip()
        notes = (request.form.get("notes") or "").strip()
        if not date:
            flash("Pick a date for your booking request.", "error")
            return redirect(url_for("community.book", slug=slug))
        when = date + (f" at {time}" if time else "")
        message = f"Booking request — {when}".strip()
        if notes:
            message += f"\n\n{notes}"
        inquiry = BookingInquiry(profile_id=profile.id, user_id=user.id,
                                 message=message, mode="platform",
                                 status="open")
        db.add(inquiry)
        db.commit()
        flash(f"Booking request sent to {profile.display_name}. "
              "They'll confirm or decline it here.", "success")
        return redirect(url_for("community.my_inquiry_thread",
                                inquiry_id=inquiry.id))

    return render_template("community/book.html", profile=profile)


@community_bp.post("/profiles/<slug>/booking-settings")
@login_required
@require_csrf
def booking_settings(slug: str):
    """Owner/manager toggles platform booking requests for a profile."""
    db = get_db()
    profile = _profile_or_404(slug)
    if not _can_manage_profile(get_current_user(), profile):
        abort(403)
    settings = _booking_settings(db, profile)
    enabled = request.form.get("enabled") in ("on", "1", "true", "yes")
    settings.platform_booking_enabled = enabled
    # Mirror the switch on the profile so public templates read it directly.
    profile.booking_mode = "platform" if enabled else "external"
    db.commit()
    if enabled:
        flash("Platform booking requests switched on — collectors can "
              "request bookings you'll confirm or decline from your inbox.",
              "success")
    else:
        flash("Platform booking requests switched off — collectors can "
              "still reach you through inquiries.", "info")
    return redirect(request.form.get("next") or
                    url_for("manage.dashboard", slug=slug))
