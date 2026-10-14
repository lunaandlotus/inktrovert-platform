"""Support pages: subscribe/donate/fundraise stubs — honest, no money moves."""
import pytest

from app.models import Contribution, FundraisingCampaign, SubscriptionTier, utcnow


def _seed_support(app):
    from app.db import get_db
    with app.app_context():
        db = get_db()
        db.add(SubscriptionTier(
            name="Insider", slug="insider", audience="magazine",
            kind="recurring", description="Subscriber exclusives.",
            perks=["Flash drops", "Early access"], price_cents=None,
            is_active=False))
        db.add(SubscriptionTier(
            name="Professional", slug="professional", audience="studio",
            kind="recurring", description="Later phase.", perks=[],
            price_cents=None, is_active=False))
        camp = FundraisingCampaign(
            title="Founding Drive", slug="founding-drive",
            description="Help launch the magazine.", goal_cents=100000,
            status="active")
        db.add(camp)
        db.flush()
        db.add(Contribution(campaign_id=camp.id, amount_cents=25000,
                            status="completed", display_name="Patron One"))
        db.add(Contribution(campaign_id=camp.id, amount_cents=25000,
                            status="completed", is_anonymous=True,
                            display_name=""))
        db.add(Contribution(campaign_id=camp.id, amount_cents=5000,
                            status="pending", display_name="Pending Pat"))
        db.commit()


def test_support_index_explains_three_engines(client, app):
    _seed_support(app)
    rv = client.get("/support/")
    assert rv.status_code == 200
    assert b"Subscribe" in rv.data
    assert b"Donate" in rv.data
    assert b"Fundraise" in rv.data


def test_subscribe_lists_magazine_tiers_only(client, app):
    _seed_support(app)
    rv = client.get("/support/subscribe")
    assert rv.status_code == 200
    assert b"Insider" in rv.data
    assert b"Flash drops" in rv.data
    assert b"To be announced" in rv.data  # price_cents None
    # studio-audience tier card excluded (its description is the marker);
    # the "For studios" explanatory section still mentions it by name.
    assert b"Later phase." not in rv.data
    assert b"For studios" in rv.data
    assert b"aren't open yet" in rv.data


def test_donate_has_no_checkout_form(client, app):
    _seed_support(app)
    rv = client.get("/support/donate")
    assert rv.status_code == 200
    assert b"not accepting donations yet" in rv.data
    assert b"<form" not in rv.data


def test_fundraise_progress_and_supporters(client, app):
    _seed_support(app)
    rv = client.get("/support/fundraise")
    assert rv.status_code == 200
    assert b"Founding Drive" in rv.data
    rv2 = client.get("/support/campaigns/founding-drive")
    assert rv2.status_code == 200
    assert b"Patron One" in rv2.data
    assert b"Pending Pat" not in rv2.data  # pending excluded
    # anonymous contributor has no visible name row
    assert rv2.data.count(b"Anonymous") <= 1


def test_unknown_campaign_404(client, app):
    _seed_support(app)
    assert client.get("/support/campaigns/nope").status_code == 404
