"""Access control for the magazine paywall.

Her rule (2026-10-14, her words): "going back to archives and through old
magazines is subscription only" / "print is subscription only and viewing
as full magazine online is subscription only."

The split:
  FREE (the funnel): individual stories/articles, full magazine search,
      issue covers as teasers.
  SUBSCRIBER-ONLY: viewing an issue as a full magazine online, print/PDF
      export of an issue, the History archive (public gets teasers:
      covers visible, content locked).

The platform owner always has access. This gate is modeled now and plugs
into phase-3 subscriptions: the day real tiers go live and supporters hold
active magazine-audience rows, the gates open for them with zero view
changes.
"""
from __future__ import annotations

from .db import get_db
from .models import Issue, SubscriptionTier, UserSubscription


def has_active_magazine_subscription(user) -> bool:
    """True for the platform owner or anyone holding an active magazine tier."""
    if user is None:
        return False
    if user.has_role("platform_owner"):
        return True
    db = get_db()
    return (
        db.query(UserSubscription)
        .join(SubscriptionTier, UserSubscription.tier_id == SubscriptionTier.id)
        .filter(
            UserSubscription.user_id == user.id,
            UserSubscription.status == "active",
            SubscriptionTier.audience == "magazine",
        )
        .first()
        is not None
    )


def can_view_issue(user, issue) -> bool:
    """Full-magazine online viewing is subscriber-only (any issue)."""
    if issue is None or not issue.is_published:
        return False
    return has_active_magazine_subscription(user)


def can_view_story(user, story) -> bool:
    """Individual stories/articles are free — they're the funnel."""
    return story is not None and story.is_published


def can_print_issue(user, issue) -> bool:
    """Print/PDF export of an issue is subscriber-only."""
    return can_view_issue(user, issue)


def can_view_history(user) -> bool:
    """The full History archive is subscriber-only; public gets teasers."""
    return has_active_magazine_subscription(user)


def current_issue(db=None):
    """The latest published issue (shown as a teaser cover when locked)."""
    db = db or get_db()
    return (
        db.query(Issue)
        .filter_by(is_published=True)
        .order_by(Issue.number.desc())
        .first()
    )


def archive_teaser_context(db=None) -> dict:
    """What the public archive teaser shows: covers/titles, content locked."""
    db = db or get_db()
    issues = (
        db.query(Issue)
        .filter_by(is_published=True)
        .order_by(Issue.number.desc())
        .all()
    )
    return {"issues": issues}
