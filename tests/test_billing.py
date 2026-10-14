"""Phase 3 billing: provider selection, graceful no-keys behavior, webhooks.

All network-free. Stripe events are built locally and signed with a test
webhook secret — stripe.Webhook.construct_event verifies them offline.
"""
import hashlib
import hmac
import inspect
import json
import time

import pytest

from app.auth import register_user
from app.db import get_db
from app.models import (Contribution, FundraisingCampaign, SubscriptionTier,
                        UserSubscription)
from app.payments import Checkout, NullProvider

from app.billing import (StripeProvider, billing_bp, ensure_sample_campaign,
                         ensure_support_tiers, get_provider)

WHSEC = "whsec_test_billing_123"


@pytest.fixture()
def billing_client(app, monkeypatch):
    """Test client with the billing blueprint registered and no Stripe keys."""
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_PUBLISHABLE_KEY", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    if "billing" not in app.blueprints:
        app.register_blueprint(billing_bp)
    return app.test_client()


def _fan(app):
    with app.app_context():
        return register_user("fan2@test.local", "FanPass1!", "Test Fan Two",
                             roles=["collector"])


def _stripe_keys(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake_no_network")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WHSEC)


def _signed_payload(payload: dict, secret: str = WHSEC) -> tuple[bytes, str]:
    """Locally-constructed Stripe event + valid Stripe-Signature header."""
    raw = json.dumps(payload).encode()
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + raw,
                   hashlib.sha256).hexdigest()
    return raw, f"t={ts},v1={sig}"


def _session_completed_event(session_id, payment_intent=None,
                             subscription=None, metadata=None, mode="payment"):
    obj = {"id": session_id, "object": "checkout.session", "mode": mode,
           "customer": "cus_test_1", "metadata": metadata or {}}
    if payment_intent:
        obj["payment_intent"] = payment_intent
    if subscription:
        obj["subscription"] = subscription
    return {"id": "evt_test_1", "object": "event",
            "type": "checkout.session.completed",
            "data": {"object": obj}}


# ---------------------------------------------------------------------------
# Provider selection + graceful degradation
# ---------------------------------------------------------------------------

def test_provider_is_null_without_keys(billing_client, monkeypatch):
    assert get_provider().name == "null"
    assert isinstance(get_provider(), NullProvider)


def test_provider_is_stripe_with_keys(billing_client, monkeypatch):
    _stripe_keys(monkeypatch)
    assert isinstance(get_provider(), StripeProvider)
    assert get_provider().name == "stripe"


def test_null_provider_checkout_has_empty_url():
    co = NullProvider().create_subscription_checkout(
        user_id=1, tier_id=1, success_url="http://x/s", cancel_url="http://x/c")
    assert isinstance(co, Checkout)
    assert co.url == ""
    co2 = NullProvider().create_donation_checkout(
        user_id=None, amount_cents=500, campaign_id=None,
        success_url="http://x/s", cancel_url="http://x/c")
    assert co2.url == ""


def test_stripe_provider_implements_full_interface():
    for method in ("create_subscription_checkout", "cancel_subscription",
                   "create_donation_checkout", "handle_webhook",
                   "refund_contribution"):
        assert callable(getattr(StripeProvider, method)), method


def test_create_order_checkout_contract_signature():
    """Cross-worker contract for the marketplace worker — exact signature."""
    sig = inspect.signature(StripeProvider.create_order_checkout, eval_str=True)
    params = list(sig.parameters.values())
    assert [p.name for p in params] == [
        "self", "user_id", "order_id", "amount_cents", "success_url",
        "cancel_url"]
    assert params[1].kind == inspect.Parameter.KEYWORD_ONLY
    assert sig.return_annotation is Checkout


def test_ensure_support_tiers_idempotent(billing_client, app):
    with app.app_context():
        first = ensure_support_tiers()
        second = ensure_support_tiers()
        db = get_db()
        tiers = db.query(SubscriptionTier).filter_by(audience="magazine",
                                                     is_active=True).all()
    assert len(first) == 2
    assert second == []
    assert len(tiers) == 2
    slugs = {t.slug for t in tiers}
    assert slugs == {"subscriber", "patron"}
    by_slug = {t.slug: t for t in tiers}
    assert by_slug["subscriber"].price_cents == 499
    assert by_slug["patron"].price_cents == 1199
    assert by_slug["subscriber"].perks  # real perks listed


def test_ensure_sample_campaign_idempotent_and_marked(billing_client, app):
    with app.app_context():
        first = ensure_sample_campaign()
        second = ensure_sample_campaign()
        camp = get_db().query(FundraisingCampaign).filter_by(
            slug="founding-drive").one()
    assert first is not None
    assert second is None
    assert camp.status == "active"
    assert "SAMPLE" in camp.description.upper()


# ---------------------------------------------------------------------------
# No-keys routes: honest "coming soon", never a stack trace
# ---------------------------------------------------------------------------

def test_subscribe_tier_coming_soon_without_keys(billing_client, app):
    rv = billing_client.get("/billing/subscribe/subscriber")
    assert rv.status_code == 200
    assert b"Not taking payments yet" in rv.data
    assert b"Nothing was charged" in rv.data
    assert b"Stripe" not in rv.data, "copy must not promise charges"


def test_subscribe_tier_404_unknown_slug(billing_client):
    assert billing_client.get("/billing/subscribe/nope").status_code == 404


def test_donate_get_renders_honest_form(billing_client):
    rv = billing_client.get("/billing/donate")
    assert rv.status_code == 200
    assert b"not accepting donations yet" in rv.data.lower()


def test_donate_post_coming_soon_without_keys(billing_client):
    rv = billing_client.post("/billing/donate",
                             data={"amount": "25", "display_name": "Pat"})
    assert rv.status_code == 200
    assert b"Not taking payments yet" in rv.data


def test_donate_post_rejects_bad_amount(billing_client):
    rv = billing_client.post("/billing/donate", data={"amount": "abc"})
    assert rv.status_code == 200
    assert b"Pick an amount" in rv.data


def test_campaign_page_renders_with_progress(billing_client, app):
    rv = billing_client.get("/billing/campaign/founding-drive")
    assert rv.status_code == 200
    assert b"Founding Drive" in rv.data
    assert b"raised of" in rv.data


def test_campaign_contribute_coming_soon_without_keys(billing_client):
    rv = billing_client.post("/billing/campaign/founding-drive",
                             data={"amount": "10"})
    assert rv.status_code == 200
    assert b"Not taking payments yet" in rv.data


def test_success_and_cancel_pages(billing_client):
    for url in ("/billing/success", "/billing/success?kind=subscription",
                "/billing/success?kind=donation", "/billing/cancel"):
        rv = billing_client.get(url)
        assert rv.status_code == 200, url
    rv = billing_client.get("/billing/cancel")
    assert b"Nothing was charged" in rv.data


def test_manage_requires_login(billing_client):
    rv = billing_client.get("/billing/manage")
    assert rv.status_code == 302
    assert "/account/login" in rv.headers["Location"]


def test_manage_empty_for_new_user(billing_client, app):
    from tests.conftest import login_as
    _fan(app)
    login_as(billing_client, "fan2@test.local", "FanPass1!")
    rv = billing_client.get("/billing/manage")
    assert rv.status_code == 200
    assert b"No subscriptions" in rv.data


# ---------------------------------------------------------------------------
# Webhooks: signature verification + row updates (offline signed events)
# ---------------------------------------------------------------------------

def test_webhook_ignored_without_keys(billing_client):
    rv = billing_client.post("/billing/webhook", data=b"{}",
                             headers={"Stripe-Signature": "t=1,v1=abc"})
    assert rv.status_code == 200
    assert b"ignored" in rv.data


def test_webhook_rejects_bad_signature(billing_client, monkeypatch):
    _stripe_keys(monkeypatch)
    rv = billing_client.post("/billing/webhook", data=b'{"id":"evt_x"}',
                             headers={"Stripe-Signature": "t=1,v1=deadbeef"})
    assert rv.status_code == 400
    assert b"signature" in rv.data


def _seed_contribution(app, ref="cs_test_1", campaign_id=None):
    with app.app_context():
        db = get_db()
        c = Contribution(user_id=None, campaign_id=campaign_id,
                         amount_cents=2500, status="pending",
                         provider="stripe", provider_payment_ref=ref,
                         display_name="Patron One")
        db.add(c)
        db.commit()
        return c.id


def test_webhook_payment_completion_marks_contribution(
        billing_client, app, monkeypatch):
    _stripe_keys(monkeypatch)
    with app.app_context():
        camp = ensure_sample_campaign()
        camp_id = camp.id
    cid = _seed_contribution(app, campaign_id=camp_id)
    event = _session_completed_event(
        "cs_test_1", payment_intent="pi_test_1",
        metadata={"kind": "donation", "campaign_id": str(camp_id)})
    raw, header = _signed_payload(event)
    rv = billing_client.post("/billing/webhook", data=raw,
                             headers={"Stripe-Signature": header,
                                      "Content-Type": "application/json"})
    assert rv.status_code == 200
    assert b"contribution.completed" in rv.data
    with app.app_context():
        db = get_db()
        c = db.get(Contribution, cid)
        assert c.status == "completed"
        assert c.provider_payment_ref == "pi_test_1"
        camp = db.get(FundraisingCampaign, camp_id)
        assert camp.raised_cents == 2500
        assert "Patron One" in camp.supporter_names


def test_webhook_subscription_checkout_activates_and_unlocks_paywall(
        billing_client, app, monkeypatch):
    _stripe_keys(monkeypatch)
    fan = _fan(app)
    with app.app_context():
        ensure_support_tiers()
        db = get_db()
        tier = db.query(SubscriptionTier).filter_by(slug="subscriber").one()
        tid = tier.id
    from app.access import has_active_magazine_subscription
    with app.app_context():
        assert not has_active_magazine_subscription(
            db.get(type(fan), fan.id))
    event = _session_completed_event(
        "cs_sub_1", subscription="sub_test_1",
        metadata={"kind": "subscription", "user_id": str(fan.id),
                  "tier_id": str(tid)},
        mode="subscription")
    raw, header = _signed_payload(event)
    rv = billing_client.post("/billing/webhook", data=raw,
                             headers={"Stripe-Signature": header,
                                      "Content-Type": "application/json"})
    assert rv.status_code == 200
    assert b"subscription.created" in rv.data
    with app.app_context():
        db = get_db()
        sub = db.query(UserSubscription).filter_by(
            user_id=fan.id, tier_id=tid).one()
        assert sub.status == "active"
        assert sub.provider == "stripe"
        assert sub.provider_subscription_ref == "sub_test_1"
        user = db.get(type(fan), fan.id)
        assert has_active_magazine_subscription(user)


def test_webhook_subscription_deleted_cancels(billing_client, app, monkeypatch):
    _stripe_keys(monkeypatch)
    fan = _fan(app)
    with app.app_context():
        ensure_support_tiers()
        db = get_db()
        tier = db.query(SubscriptionTier).filter_by(slug="subscriber").one()
        db.add(UserSubscription(user_id=fan.id, tier_id=tier.id,
                                status="active", provider="stripe",
                                provider_subscription_ref="sub_gone_1"))
        db.commit()
    event = {"id": "evt_test_2", "object": "event",
             "type": "customer.subscription.deleted",
             "data": {"object": {
                 "id": "sub_gone_1", "object": "subscription",
                 "customer": "cus_test_1", "status": "canceled",
                 "metadata": {"user_id": str(fan.id)}}}}
    raw, header = _signed_payload(event)
    rv = billing_client.post("/billing/webhook", data=raw,
                             headers={"Stripe-Signature": header,
                                      "Content-Type": "application/json"})
    assert rv.status_code == 200
    assert b"subscription.canceled" in rv.data
    with app.app_context():
        sub = get_db().query(UserSubscription).filter_by(
            provider_subscription_ref="sub_gone_1").one()
        assert sub.status == "canceled"
        assert sub.canceled_at is not None


def test_webhook_charge_refunded(billing_client, app, monkeypatch):
    _stripe_keys(monkeypatch)
    cid = _seed_contribution(app, ref="pi_ref_1")
    with app.app_context():
        db = get_db()
        db.get(Contribution, cid).status = "completed"
        db.commit()
    event = {"id": "evt_test_3", "object": "event",
             "type": "charge.refunded",
             "data": {"object": {
                 "id": "ch_test_1", "object": "charge",
                 "payment_intent": "pi_ref_1"}}}
    raw, header = _signed_payload(event)
    rv = billing_client.post("/billing/webhook", data=raw,
                             headers={"Stripe-Signature": header,
                                      "Content-Type": "application/json"})
    assert rv.status_code == 200
    assert b"contribution.refunded" in rv.data
    with app.app_context():
        assert get_db().get(Contribution, cid).status == "refunded"


# ---------------------------------------------------------------------------
# Owner admin ("this needs to be editable by me.")
# ---------------------------------------------------------------------------

def _owner_client(billing_client, owner_user):
    from tests.conftest import login_as
    login_as(billing_client, "owner@test.local", "OwnerPass1!")
    return billing_client


def _collector_client(billing_client, collector_user):
    from tests.conftest import login_as
    login_as(billing_client, "fan@test.local", "FanPass1!")
    return billing_client


def test_admin_routes_require_owner(billing_client, collector_user):
    for url in ("/billing/admin", "/billing/admin/campaigns",
                "/billing/admin/tiers", "/billing/admin/contributions"):
        rv = billing_client.get(url)
        assert rv.status_code == 302, url  # anonymous -> login
        assert "/account/login" in rv.headers["Location"]
    oc = _collector_client(billing_client, collector_user)
    for url in ("/billing/admin", "/billing/admin/campaigns",
                "/billing/admin/tiers", "/billing/admin/contributions"):
        assert oc.get(url).status_code == 403, url  # stranger denied


def test_admin_index_owner_ok(billing_client, owner_user):
    oc = _owner_client(billing_client, owner_user)
    rv = oc.get("/billing/admin")
    assert rv.status_code == 200
    assert b"Manage drives" in rv.data
    assert b"Manage tiers" in rv.data
    assert b"View contributions" in rv.data


def _campaign_payload(**over):
    data = {"title": "Spring Print Run", "slug": "", "description": "Print it.",
            "goal_dollars": "5000.00", "status": "active",
            "starts_at": "2026-11-01", "ends_at": "2026-12-31",
            "show_supporter_list": "on"}
    data.update(over)
    return data


def test_owner_can_create_and_edit_campaign(billing_client, app, owner_user):
    oc = _owner_client(billing_client, owner_user)
    rv = oc.post("/billing/admin/campaigns/new", data=_campaign_payload(),
                 follow_redirects=False)
    assert rv.status_code == 302
    with app.app_context():
        db = get_db()
        camp = db.query(FundraisingCampaign).filter_by(
            title="Spring Print Run").one()
        assert camp.slug == "spring-print-run"
        assert camp.goal_cents == 500_000
        assert camp.status == "active"
        assert camp.starts_at.strftime("%Y-%m-%d") == "2026-11-01"
        assert camp.ends_at.strftime("%Y-%m-%d") == "2026-12-31"
        assert camp.show_supporter_list is True
        cid = camp.id
    rv = oc.post(f"/billing/admin/campaigns/{cid}/edit",
                 data=_campaign_payload(title="Spring Print Run (2nd)",
                                        goal_dollars="7500",
                                        status="ended"),
                 follow_redirects=False)
    assert rv.status_code == 302
    with app.app_context():
        camp = get_db().get(FundraisingCampaign, cid)
        assert camp.title == "Spring Print Run (2nd)"
        assert camp.goal_cents == 750_000
        assert camp.status == "ended"


def test_owner_campaign_create_requires_title(billing_client, owner_user):
    oc = _owner_client(billing_client, owner_user)
    rv = oc.post("/billing/admin/campaigns/new",
                 data=_campaign_payload(title=""))
    assert rv.status_code == 200
    assert b"A title is required" in rv.data


def test_owner_cannot_delete_campaign_with_contributions(
        billing_client, app, owner_user):
    oc = _owner_client(billing_client, owner_user)
    oc.post("/billing/admin/campaigns/new", data=_campaign_payload())
    with app.app_context():
        db = get_db()
        camp = db.query(FundraisingCampaign).filter_by(
            title="Spring Print Run").one()
        cid = camp.id
        db.add(Contribution(campaign_id=cid, amount_cents=1000,
                            status="completed", display_name="Pat"))
        db.commit()
    rv = oc.post(f"/billing/admin/campaigns/{cid}/delete",
                 follow_redirects=True)
    assert rv.status_code == 200
    assert b"can&#39;t be deleted" in rv.data or b"can't be deleted" in rv.data
    with app.app_context():
        assert get_db().get(FundraisingCampaign, cid) is not None


def _tier_payload(**over):
    data = {"name": "Insider", "slug": "", "audience": "magazine",
            "kind": "recurring", "description": "The inner circle.",
            "perks": "Early access\nFlash drops\n", "price_dollars": "9.99",
            "is_active": "on"}
    data.update(over)
    return data


def test_owner_can_create_and_edit_tier(billing_client, app, owner_user):
    oc = _owner_client(billing_client, owner_user)
    rv = oc.post("/billing/admin/tiers/new", data=_tier_payload(),
                 follow_redirects=False)
    assert rv.status_code == 302
    with app.app_context():
        db = get_db()
        tier = db.query(SubscriptionTier).filter_by(name="Insider").one()
        assert tier.slug == "insider"
        assert tier.audience == "magazine"
        assert tier.kind == "recurring"
        assert tier.perks == ["Early access", "Flash drops"]
        assert tier.price_cents == 999
        assert tier.is_active is True
        tid = tier.id
    rv = oc.post(f"/billing/admin/tiers/{tid}/edit",
                 data=_tier_payload(name="Insider Plus", price_dollars="14.50",
                                    audience="studio"),
                 follow_redirects=False)
    assert rv.status_code == 302
    with app.app_context():
        tier = get_db().get(SubscriptionTier, tid)
        assert tier.name == "Insider Plus"
        assert tier.price_cents == 1450
        assert tier.audience == "studio"


def test_owner_cannot_delete_tier_with_subscribers(
        billing_client, app, owner_user):
    oc = _owner_client(billing_client, owner_user)
    oc.post("/billing/admin/tiers/new", data=_tier_payload())
    with app.app_context():
        db = get_db()
        tier = db.query(SubscriptionTier).filter_by(name="Insider").one()
        tid = tier.id
        db.add(UserSubscription(user_id=owner_user.id, tier_id=tid,
                                status="active"))
        db.commit()
    rv = oc.post(f"/billing/admin/tiers/{tid}/delete", follow_redirects=True)
    assert rv.status_code == 200
    assert b"can&#39;t be deleted" in rv.data or b"can't be deleted" in rv.data
    with app.app_context():
        assert get_db().get(SubscriptionTier, tid) is not None


def test_owner_can_delete_empty_tier(billing_client, app, owner_user):
    oc = _owner_client(billing_client, owner_user)
    oc.post("/billing/admin/tiers/new", data=_tier_payload())
    with app.app_context():
        tid = get_db().query(SubscriptionTier).filter_by(
            name="Insider").one().id
    rv = oc.post(f"/billing/admin/tiers/{tid}/delete", follow_redirects=False)
    assert rv.status_code == 302
    with app.app_context():
        assert get_db().get(SubscriptionTier, tid) is None


def test_admin_contributions_list_and_graceful_refund(
        billing_client, app, owner_user):
    oc = _owner_client(billing_client, owner_user)
    cid = _seed_contribution(app, ref="pi_admin_1")
    with app.app_context():
        db = get_db()
        db.get(Contribution, cid).status = "completed"
        db.commit()
    rv = oc.get("/billing/admin/contributions")
    assert rv.status_code == 200
    assert b"Patron One" in rv.data
    # No Stripe keys: refund must be graceful, status untouched.
    rv = oc.post(f"/billing/admin/contributions/{cid}/refund",
                 follow_redirects=True)
    assert rv.status_code == 200
    assert b"aren&#39;t connected" in rv.data or b"aren't connected" in rv.data
    with app.app_context():
        assert get_db().get(Contribution, cid).status == "completed"


def test_admin_refund_only_completed(billing_client, app, owner_user):
    oc = _owner_client(billing_client, owner_user)
    cid = _seed_contribution(app, ref="cs_pending_1")  # status=pending
    rv = oc.post(f"/billing/admin/contributions/{cid}/refund",
                 follow_redirects=True)
    assert rv.status_code == 200
    assert b"Only completed contributions" in rv.data


def test_webhook_unrecognized_event_ignored(billing_client, monkeypatch):
    _stripe_keys(monkeypatch)
    event = {"id": "evt_test_9", "object": "event",
             "type": "invoice.paid", "data": {"object": {"id": "in_1"}}}
    raw, header = _signed_payload(event)
    rv = billing_client.post("/billing/webhook", data=raw,
                             headers={"Stripe-Signature": header,
                                      "Content-Type": "application/json"})
    assert rv.status_code == 200
    assert b"ignored" in rv.data
