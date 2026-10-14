"""SUPPORT blueprint — the magazine funding engine UI (blueprint only, no money moves).

Inktrovert's editorial layer is funded three ways: subscriptions, one-time
donations, and fundraising drives. Payment rails are UNDECIDED, so every page
here is honest that paid features are "coming soon" — nothing here talks to a
payment gateway, and no page may contain a checkout form or button that
pretends to take money. This engine belongs to the magazine section only;
studio-side tiers (Professional / Studio Partner) come later.

All routes are public — no login required.
"""
from __future__ import annotations

from flask import Blueprint, abort, render_template
from sqlalchemy import select

from .db import get_db
from .models import FundraisingCampaign, SubscriptionTier

support_bp = Blueprint("support", __name__, url_prefix="/support")


@support_bp.route("/")
def index():
    """The three engines, explained plainly."""
    return render_template("support/index.html")


@support_bp.route("/subscribe")
def subscribe():
    """Magazine-audience tiers with perks. Prices show 'To be announced'
    until set. Memberships are not open yet."""
    db = get_db()
    tiers = list(
        db.execute(
            select(SubscriptionTier)
            .where(SubscriptionTier.audience == "magazine")
            .order_by(SubscriptionTier.id)
        ).scalars()
    )
    return render_template("support/subscribe.html", tiers=tiers)


@support_bp.route("/donate")
def donate():
    """One-time donations, explained honestly: not accepted yet."""
    return render_template("support/donate.html")


@support_bp.route("/fundraise")
def fundraise():
    """Fundraising drives, active ones first, with progress bars."""
    db = get_db()
    campaigns = list(
        db.execute(
            select(FundraisingCampaign).order_by(
                # active first, then ended, then drafts; newest first within
                (FundraisingCampaign.status != "active").asc(),
                FundraisingCampaign.created_at.desc(),
            )
        ).scalars()
    )
    return render_template("support/fundraise.html", campaigns=campaigns)


@support_bp.route("/campaigns/<slug>")
def campaign_detail(slug):
    """One drive: title, description, goal/progress, dates, supporter list."""
    db = get_db()
    campaign = db.execute(
        select(FundraisingCampaign).where(FundraisingCampaign.slug == slug)
    ).scalar_one_or_none()
    if campaign is None:
        abort(404)
    # supporter_names respects anonymity: anonymous contributions are
    # simply excluded by the model property.
    return render_template(
        "support/campaign.html",
        campaign=campaign,
        supporter_names=campaign.supporter_names,
    )
