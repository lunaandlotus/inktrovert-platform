"""BILLING blueprint — phase 3: Stripe-backed monetization.

Three money lanes, one Stripe account, separate flows per lane:
  * subscriptions  (/billing/subscribe/<tier>) — recurring magazine memberships
  * donations      (/billing/donate)            — one-time gifts, donor-set amounts
  * fundraising    (/billing/campaign/<slug>)   — contributions toward a drive

The founder connects keys LATER. Until STRIPE_SECRET_KEY is set, get_provider()
returns the NullProvider and every money route degrades to a tasteful
"coming soon" page — no stack traces, no promises of charges, nothing moves.

Webhook truth: Stripe events keep UserSubscription / Contribution rows honest
(the paywall gates in app/access.py read those rows). With no keys configured
the webhook ignores everything and answers 200.

Stripe test mode only. No real charges while keys are absent — and this module
never fabricates a charge on its own.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from flask import (Blueprint, abort, current_app, flash, jsonify, redirect,
                   render_template, request, url_for)
from sqlalchemy import select

from .auth import get_current_user, require_csrf, role_required
from .db import get_db
from .models import (TIER_AUDIENCES, Contribution, FundraisingCampaign,
                     SubscriptionTier, UserSubscription)
from .payments import Checkout, NullProvider, PaymentProvider, WebhookEvent

billing_bp = Blueprint("billing", __name__, url_prefix="/billing")


class BadWebhookSignature(Exception):
    """Raised by StripeProvider.handle_webhook when the payload fails
    signature verification. Verified-but-unrecognized events return None."""


SAMPLE_CAMPAIGN_SLUG = "founding-drive"

MAGAZINE_TIERS = [
    {
        "name": "Inktrovert Subscriber",
        "slug": "subscriber",
        "price_cents": 499,
        "description": ("The magazine, unlocked. Full-issue reading, the History "
                        "archive, and print-ready issues — plus subscriber-only "
                        "extras as they drop."),
        "perks": [
            "Read every issue as a full magazine online",
            "Full History archive access",
            "Print-ready issues (PDF export)",
            "Early access to new stories and episodes",
            "Subscriber-only flash drops",
        ],
    },
    {
        "name": "Inktrovert Patron",
        "slug": "patron",
        "price_cents": 1199,
        "description": ("For readers who want the magazine to grow. Everything in "
                        "Subscriber, plus behind-the-chair content and event "
                        "presales — you keep the lights on."),
        "perks": [
            "Everything in Inktrovert Subscriber",
            "Behind-the-chair content and artist interviews",
            "Event and convention presales",
            "Name in the annual patron thank-you page",
        ],
    },
]


# ---------------------------------------------------------------------------
# Provider selection — lazy stripe import, graceful with no keys or no package
# ---------------------------------------------------------------------------

def _stripe_lib():
    """The stripe package, or None when it isn't installed."""
    try:
        import stripe
        return stripe
    except ImportError:
        return None


def get_provider() -> PaymentProvider:
    """Live Stripe when STRIPE_SECRET_KEY is set (and the package imports),
    otherwise the null provider — the graceful-degradation path."""
    if os.environ.get("STRIPE_SECRET_KEY", "").strip() and _stripe_lib() is not None:
        return StripeProvider()
    return NullProvider()


def billing_live() -> bool:
    """Template helper: True only when real checkout is possible."""
    return get_provider().name != "null"


class StripeProvider(PaymentProvider):
    """Real rails: Stripe Checkout Sessions, webhooks, cancels, refunds."""

    name = "stripe"

    def _stripe(self):
        import stripe  # noqa: PLC0415 — lazy so the app boots without keys/package
        stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
        return stripe

    # -- interface -----------------------------------------------------------

    def create_subscription_checkout(self, *, user_id: int, tier_id: int,
                                     success_url: str, cancel_url: str) -> Checkout:
        stripe = self._stripe()
        db = get_db()
        tier = db.get(SubscriptionTier, tier_id)
        if tier is None or tier.price_cents is None or tier.price_cents <= 0:
            raise ValueError("tier is not billable")
        meta = {"kind": "subscription", "user_id": str(user_id), "tier_id": str(tier_id)}
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "unit_amount": tier.price_cents,
                    "recurring": {"interval": "month"},
                    "product_data": {"name": f"Inktrovert — {tier.name}"},
                },
                "quantity": 1,
            }],
            metadata=meta,
            # Copy the identity metadata onto the subscription itself so
            # subscription.updated/deleted events can be matched back.
            subscription_data={"metadata": meta},
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return Checkout(url=session.url or "", provider_ref=session.id,
                        provider=self.name)

    def cancel_subscription(self, *, provider_subscription_ref: str) -> bool:
        stripe = self._stripe()
        try:
            sub = stripe.Subscription.retrieve(provider_subscription_ref)
            sub.cancel()
            return True
        except Exception:
            current_app.logger.warning("stripe cancel failed for %s",
                                       provider_subscription_ref)
            return False

    def create_donation_checkout(self, *, user_id: int | None,
                                 amount_cents: int,
                                 campaign_id: int | None,
                                 success_url: str, cancel_url: str) -> Checkout:
        stripe = self._stripe()
        if amount_cents is None or amount_cents < 50:
            raise ValueError("donation must be at least $0.50")
        meta = {"kind": "donation"}
        if user_id is not None:
            meta["user_id"] = str(user_id)
        if campaign_id is not None:
            meta["campaign_id"] = str(campaign_id)
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "unit_amount": amount_cents,
                    "product_data": {"name": "Inktrovert donation"},
                },
                "quantity": 1,
            }],
            metadata=meta,
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return Checkout(url=session.url or "", provider_ref=session.id,
                        provider=self.name)

    def handle_webhook(self, raw_body: bytes, signature: str) -> WebhookEvent | None:
        stripe = self._stripe()
        secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
        try:
            event = stripe.Webhook.construct_event(raw_body, signature, secret)
        except Exception as exc:
            # Bad signature, wrong secret, or malformed payload — the caller
            # answers 400. Nothing is applied.
            raise BadWebhookSignature(str(exc)) from exc
        return _normalize_stripe_event(event)

    def refund_contribution(self, *, provider_payment_ref: str) -> bool:
        stripe = self._stripe()
        try:
            stripe.Refund.create(payment_intent=provider_payment_ref)
            return True
        except Exception:
            current_app.logger.warning("stripe refund failed for %s",
                                       provider_payment_ref)
            return False

    # -- cross-worker contract: B2B marketplace one-time order checkout --------

    def create_order_checkout(self, *, user_id: int | None, order_id: int,
                              amount_cents: int, success_url: str,
                              cancel_url: str) -> Checkout:
        """One-time payment for a marketplace order (phase 5). The owning
        worker handles fulfillment off the 'order.completed' webhook event."""
        stripe = self._stripe()
        if amount_cents is None or amount_cents < 50:
            raise ValueError("order total must be at least $0.50")
        meta = {"kind": "marketplace_order", "order_id": str(order_id)}
        if user_id is not None:
            meta["user_id"] = str(user_id)
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "unit_amount": amount_cents,
                    "product_data": {"name": "Inktrovert marketplace order"},
                },
                "quantity": 1,
            }],
            metadata=meta,
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return Checkout(url=session.url or "", provider_ref=session.id,
                        provider=self.name)


def _meta_int(meta: dict, key: str) -> int | None:
    try:
        value = int(meta.get(key))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _normalize_stripe_event(event) -> WebhookEvent | None:
    """Map a verified Stripe event to the provider-neutral WebhookEvent."""
    etype = event.get("type", "") or ""
    obj = (event.get("data") or {}).get("object") or {}
    meta = obj.get("metadata") or {}
    user_id = _meta_int(meta, "user_id")
    kind = meta.get("kind", "")

    if etype == "checkout.session.completed":
        mode = obj.get("mode")
        if mode == "subscription" or kind == "subscription":
            return WebhookEvent(
                kind="subscription.created", provider="stripe",
                provider_ref=obj.get("subscription") or obj.get("id", ""),
                user_id=user_id, tier_id=_meta_int(meta, "tier_id"),
                status="active",
                meta={"session_id": obj.get("id", ""),
                      "customer": obj.get("customer", "")},
            )
        if meta.get("order_id") or kind == "marketplace_order":
            # Phase-5 lane: the marketplace worker owns fulfillment.
            return WebhookEvent(
                kind="order.completed", provider="stripe",
                provider_ref=obj.get("payment_intent") or obj.get("id", ""),
                user_id=user_id, status="completed",
                meta={"session_id": obj.get("id", ""),
                      "order_id": meta.get("order_id", "")},
            )
        return WebhookEvent(
            kind="contribution.completed", provider="stripe",
            provider_ref=obj.get("payment_intent") or obj.get("id", ""),
            user_id=user_id, status="completed",
            meta={"session_id": obj.get("id", ""),
                  "campaign_id": meta.get("campaign_id", "")},
        )

    if etype == "customer.subscription.updated":
        return WebhookEvent(
            kind="subscription.updated", provider="stripe",
            provider_ref=obj.get("id", ""),
            user_id=user_id, tier_id=_meta_int(meta, "tier_id"),
            status=obj.get("status", ""),
            meta={"customer": obj.get("customer", ""),
                  "current_period_end": obj.get("current_period_end")},
        )

    if etype == "customer.subscription.deleted":
        return WebhookEvent(
            kind="subscription.canceled", provider="stripe",
            provider_ref=obj.get("id", ""),
            user_id=user_id, tier_id=_meta_int(meta, "tier_id"),
            status="canceled",
            meta={"customer": obj.get("customer", "")},
        )

    if etype == "charge.refunded":
        return WebhookEvent(
            kind="contribution.refunded", provider="stripe",
            provider_ref=obj.get("payment_intent") or obj.get("id", ""),
            status="refunded",
            meta={"charge_id": obj.get("id", "")},
        )

    return None


# ---------------------------------------------------------------------------
# Seeding (idempotent)
# ---------------------------------------------------------------------------

def ensure_support_tiers(db=None) -> list[SubscriptionTier]:
    """Create the default magazine tiers when none are active yet.

    Idempotent: if any active magazine-audience tier exists, nothing happens.
    """
    db = db or get_db()
    existing = db.execute(
        select(SubscriptionTier.id).where(
            SubscriptionTier.audience == "magazine",
            SubscriptionTier.is_active.is_(True),
        )
    ).first()
    if existing:
        return []
    created = []
    for spec in MAGAZINE_TIERS:
        tier = SubscriptionTier(
            name=spec["name"], slug=spec["slug"], audience="magazine",
            kind="recurring", description=spec["description"],
            perks=list(spec["perks"]), price_cents=spec["price_cents"],
            is_active=True,
        )
        db.add(tier)
        created.append(tier)
    db.commit()
    return created


def ensure_sample_campaign(db=None) -> FundraisingCampaign | None:
    """One sample ACTIVE campaign so the fundraise page is never empty.

    Clearly marked as sample content in the description; the founder swaps in
    the real drive. Idempotent (skips when the slug exists).
    """
    db = db or get_db()
    existing = db.execute(
        select(FundraisingCampaign).where(
            FundraisingCampaign.slug == SAMPLE_CAMPAIGN_SLUG)
    ).scalar_one_or_none()
    if existing is not None:
        return None
    campaign = FundraisingCampaign(
        title="Founding Drive",
        slug=SAMPLE_CAMPAIGN_SLUG,
        description=("[SAMPLE CONTENT — the founder replaces this with the real "
                     "founding drive.] Every magazine starts somewhere: this "
                     "drive funds the first print run and the podcast studio "
                     "upgrade so Inktrovert stays independent and reader-funded."),
        goal_cents=1_000_000,  # $10,000
        status="active",
    )
    db.add(campaign)
    db.commit()
    return campaign


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@billing_bp.route("/subscribe/<tier_slug>")
def subscribe_tier(tier_slug: str):
    """Start a subscription checkout — or the coming-soon page with no keys."""
    db = get_db()
    ensure_support_tiers(db)
    tier = db.execute(
        select(SubscriptionTier).where(
            SubscriptionTier.slug == tier_slug,
            SubscriptionTier.audience == "magazine",
        )
    ).scalar_one_or_none()
    if tier is None or not tier.is_active or tier.price_cents is None:
        abort(404)
    provider = get_provider()
    if provider.name == "null":
        return render_template("billing/coming_soon.html", lane="subscriptions",
                               tier=tier)
    user = get_current_user()
    checkout = provider.create_subscription_checkout(
        user_id=user.id if user else 0,
        tier_id=tier.id,
        success_url=url_for("billing.success", _external=True,
                            kind="subscription"),
        cancel_url=url_for("billing.cancel", _external=True),
    )
    if not checkout.url:
        return render_template("billing/coming_soon.html", lane="subscriptions",
                               tier=tier)
    return redirect(checkout.url)


def _parse_amount_dollars(raw: str | None) -> int | None:
    """'25', '25.00', '$25' -> 2500 cents. None when unparseable."""
    if raw is None:
        return None
    text = raw.strip().lstrip("$").replace(",", "")
    try:
        dollars = float(text)
    except ValueError:
        return None
    cents = int(round(dollars * 100))
    return cents if 50 <= cents <= 1_000_000_00 else None


@billing_bp.route("/donate", methods=["GET", "POST"])
@require_csrf
def donate():
    """Donor-entered amount -> Stripe payment checkout (or coming soon)."""
    db = get_db()
    provider = get_provider()
    if request.method == "POST":
        amount_cents = _parse_amount_dollars(request.form.get("amount"))
        message = (request.form.get("message") or "").strip()[:500]
        display_name = (request.form.get("display_name") or "").strip()[:120]
        is_anonymous = request.form.get("anonymous") == "on"
        if amount_cents is None:
            return render_template("billing/donate.html",
                                   error="Pick an amount between $0.50 and $1,000,000.",
                                   live=billing_live())
        if provider.name == "null":
            return render_template("billing/coming_soon.html", lane="donations")
        user = get_current_user()
        contribution = Contribution(
            user_id=user.id if user else None,
            campaign_id=None,
            amount_cents=amount_cents,
            status="pending",
            provider=provider.name,
            message=message,
            is_anonymous=is_anonymous,
            display_name=(display_name or (user.full_name if user else "") or "A reader"),
        )
        checkout = provider.create_donation_checkout(
            user_id=user.id if user else None,
            amount_cents=amount_cents,
            campaign_id=None,
            success_url=url_for("billing.success", _external=True, kind="donation"),
            cancel_url=url_for("billing.cancel", _external=True),
        )
        if not checkout.url:
            return render_template("billing/coming_soon.html", lane="donations")
        contribution.provider_payment_ref = checkout.provider_ref
        db.add(contribution)
        db.commit()
        return redirect(checkout.url)
    return render_template("billing/donate.html", live=billing_live())


@billing_bp.route("/campaign/<slug>", methods=["GET", "POST"])
@require_csrf
def campaign(slug: str):
    """A drive's page: goal progress bar + contribute (or coming soon)."""
    db = get_db()
    ensure_sample_campaign(db)
    campaign = db.execute(
        select(FundraisingCampaign).where(FundraisingCampaign.slug == slug)
    ).scalar_one_or_none()
    if campaign is None:
        abort(404)
    provider = get_provider()
    if request.method == "POST":
        if campaign.status != "active":
            abort(400, "This drive isn't collecting contributions right now.")
        amount_cents = _parse_amount_dollars(request.form.get("amount"))
        message = (request.form.get("message") or "").strip()[:500]
        display_name = (request.form.get("display_name") or "").strip()[:120]
        is_anonymous = request.form.get("anonymous") == "on"
        if amount_cents is None:
            return render_template("billing/campaign.html", campaign=campaign,
                                   supporter_names=campaign.supporter_names,
                                   error="Pick an amount between $0.50 and $1,000,000.",
                                   live=billing_live())
        if provider.name == "null":
            return render_template("billing/coming_soon.html", lane="drives",
                                   campaign=campaign)
        user = get_current_user()
        contribution = Contribution(
            user_id=user.id if user else None,
            campaign_id=campaign.id,
            amount_cents=amount_cents,
            status="pending",
            provider=provider.name,
            message=message,
            is_anonymous=is_anonymous,
            display_name=(display_name or (user.full_name if user else "") or "A reader"),
        )
        checkout = provider.create_donation_checkout(
            user_id=user.id if user else None,
            amount_cents=amount_cents,
            campaign_id=campaign.id,
            success_url=url_for("billing.success", _external=True, kind="drive"),
            cancel_url=url_for("billing.cancel", _external=True),
        )
        if not checkout.url:
            return render_template("billing/coming_soon.html", lane="drives",
                                   campaign=campaign)
        contribution.provider_payment_ref = checkout.provider_ref
        db.add(contribution)
        db.commit()
        return redirect(checkout.url)
    return render_template("billing/campaign.html", campaign=campaign,
                           supporter_names=campaign.supporter_names,
                           live=billing_live())


@billing_bp.route("/success")
def success():
    """Stripe sent them back after paying. We say thanks; the webhook is what
    actually records the money."""
    kind = request.args.get("kind", "")
    return render_template("billing/success.html", kind=kind)


@billing_bp.route("/cancel")
def cancel():
    """They backed out at Stripe. Nothing was charged."""
    return render_template("billing/cancel.html")


@billing_bp.route("/manage", methods=["GET", "POST"])
@require_csrf
def manage():
    """A supporter views their subscriptions and can cancel one."""
    user = get_current_user()
    if user is None:
        return redirect(url_for("account.login", next=request.path))
    db = get_db()
    message = None
    if request.method == "POST":
        sub_id = request.form.get("subscription_id", "")
        sub = db.get(UserSubscription, sub_id) if sub_id.isdigit() else None
        if sub is None or sub.user_id != user.id:
            abort(404)
        provider = get_provider()
        canceled = False
        if sub.provider_subscription_ref:
            canceled = provider.cancel_subscription(
                provider_subscription_ref=sub.provider_subscription_ref)
        # Trust but verify: even if the provider call fails (no keys, network
        # hiccup), record the local truth honestly — Stripe stays the source
        # of truth once keys are live; the webhook reconciles.
        if canceled or provider.name == "null":
            sub.status = "canceled"
            sub.canceled_at = datetime.now(timezone.utc)
            db.commit()
            message = (f"{sub.tier.name} canceled. It stays active until the end "
                       "of the current billing period.")
        else:
            message = ("We couldn't reach the payment provider just now — try "
                       "again in a bit.")
    subs = list(db.execute(
        select(UserSubscription).where(UserSubscription.user_id == user.id)
        .order_by(UserSubscription.id.desc())
    ).scalars())
    return render_template("billing/manage.html", subscriptions=subs,
                           message=message, live=billing_live())


@billing_bp.route("/webhook", methods=["POST"])
def webhook():
    """Stripe webhook. Verified events update local rows; anything else is
    ignored. Always answers 200 for verified/ignored traffic, 400 for bad
    signatures."""
    raw = request.get_data()
    signature = request.headers.get("Stripe-Signature", "")
    provider = get_provider()
    if provider.name == "null":
        # No keys configured: nothing to verify against; ignore quietly.
        return jsonify({"status": "ignored",
                        "reason": "no payment provider configured"}), 200
    try:
        event = provider.handle_webhook(raw, signature)
    except BadWebhookSignature:
        return jsonify({"status": "error",
                        "reason": "invalid webhook signature"}), 400
    if event is None:
        # Verified signature, but an event type we don't act on.
        return jsonify({"status": "ignored",
                        "reason": "unrecognized event type"}), 200
    _apply_webhook_event(event)
    return jsonify({"status": "ok", "kind": event.kind}), 200


def _apply_webhook_event(event: WebhookEvent) -> None:
    """Keep UserSubscription / Contribution rows truthful from Stripe events."""
    db = get_db()
    now = datetime.now(timezone.utc)

    if event.kind == "subscription.created":
        if event.user_id and event.tier_id:
            sub = db.execute(
                select(UserSubscription).where(
                    UserSubscription.user_id == event.user_id,
                    UserSubscription.tier_id == event.tier_id,
                    UserSubscription.provider_subscription_ref == event.provider_ref,
                )
            ).scalar_one_or_none()
            if sub is None:
                sub = UserSubscription(user_id=event.user_id, tier_id=event.tier_id)
                db.add(sub)
            sub.status = "active"
            sub.provider = event.provider
            sub.provider_customer_ref = event.meta.get("customer", "")
            sub.provider_subscription_ref = event.provider_ref
            sub.started_at = sub.started_at or now
            db.commit()

    elif event.kind in ("subscription.updated", "subscription.canceled"):
        sub = db.execute(
            select(UserSubscription).where(
                UserSubscription.provider_subscription_ref == event.provider_ref)
        ).scalar_one_or_none()
        if sub is not None:
            stripe_status = (event.status or "").lower()
            sub.status = stripe_status if stripe_status in (
                "active", "trialing", "past_due", "canceled") else sub.status
            if event.kind == "subscription.canceled":
                sub.status = "canceled"
                sub.canceled_at = now
            epoch = event.meta.get("current_period_end")
            try:
                if epoch:
                    sub.current_period_end = datetime.fromtimestamp(
                        int(epoch), tz=timezone.utc)
            except (TypeError, ValueError):
                pass
            db.commit()

    elif event.kind == "contribution.completed":
        contribution = _find_contribution(db, event)
        if contribution is not None:
            contribution.status = "completed"
            db.commit()

    elif event.kind == "contribution.refunded":
        contribution = _find_contribution(db, event)
        if contribution is not None:
            contribution.status = "refunded"
            db.commit()

    elif event.kind == "order.completed":
        # Phase-5 lane: hand fulfillment to the marketplace module.
        try:
            from .market import mark_order_paid_by_id
            order_id = (event.meta or {}).get("order_id")
            if order_id:
                mark_order_paid_by_id(int(order_id), event.provider_ref)
        except Exception:
            current_app.logger.exception("order.completed handoff failed: %s",
                                         (event.meta or {}).get("order_id"))
        current_app.logger.info("marketplace order.completed: %s",
                                event.meta.get("order_id"))


def _find_contribution(db, event: WebhookEvent) -> Contribution | None:
    """Match a payment webhook to its pending Contribution row by either the
    payment intent ref or the checkout session id (stored as the ref at
    checkout time, then swapped to the payment intent when known)."""
    refs = [r for r in (event.provider_ref, event.meta.get("session_id")) if r]
    for ref in refs:
        row = db.execute(
            select(Contribution).where(Contribution.provider_payment_ref == ref)
        ).scalar_one_or_none()
        if row is not None:
            if event.provider_ref and row.provider_payment_ref != event.provider_ref:
                row.provider_payment_ref = event.provider_ref
            return row
    return None


@billing_bp.app_context_processor
def _billing_template_helpers():
    return {"billing_live": billing_live}


# ---------------------------------------------------------------------------
# Owner admin — "this needs to be editable by me." (founder, 2026-10-14)
#
# Full CRUD for campaigns and support tiers, read-only contributions with a
# provider-wired refund action. Owner-only; lives under /billing/admin/ so the
# owner dashboard can link straight in.
# ---------------------------------------------------------------------------

import re as _re  # noqa: E402

TIER_KINDS = ("recurring", "founding")
CAMPAIGN_STATUSES = ("draft", "active", "ended")


def _slugify(text: str, maxlen: int = 200) -> str:
    slug = _re.sub(r"[^a-z0-9]+", "-", (text or "").casefold()).strip("-")[:maxlen]
    return slug or "item"


def _unique_slug(model, base: str, exclude_id: int | None = None) -> str:
    db = get_db()
    slug, n = base, 2
    while True:
        q = db.query(model).filter_by(slug=slug)
        if exclude_id is not None:
            q = q.filter(model.id != exclude_id)
        if q.one_or_none() is None:
            return slug
        slug = f"{base}-{n}"
        n += 1


def _parse_date(value: str | None) -> datetime | None:
    try:
        return datetime.strptime((value or "").strip(), "%Y-%m-%d").replace(
            tzinfo=timezone.utc)
    except ValueError:
        return None


def _dollars_to_cents(raw: str | None) -> int | None:
    """'25', '25.00', '$25' -> 2500. None when blank/unparseable/negative."""
    if raw is None or not raw.strip():
        return None
    try:
        cents = int(round(float(raw.strip().lstrip("$").replace(",", "")) * 100))
    except ValueError:
        return None
    return cents if cents >= 0 else None


def _cents_to_dollars(cents: int | None) -> str:
    return f"{(cents or 0) / 100:.2f}"


@billing_bp.route("/admin")
@role_required("platform_owner")
def admin_index():
    db = get_db()
    return render_template(
        "billing/admin/index.html",
        campaign_count=db.query(FundraisingCampaign).count(),
        tier_count=db.query(SubscriptionTier).count(),
        contribution_count=db.query(Contribution).count(),
        live=billing_live(),
    )


# -- campaigns ---------------------------------------------------------------

@billing_bp.route("/admin/campaigns")
@role_required("platform_owner")
def admin_campaigns():
    db = get_db()
    campaigns = list(db.execute(
        select(FundraisingCampaign).order_by(FundraisingCampaign.id.desc())
    ).scalars())
    return render_template("billing/admin/campaigns.html", campaigns=campaigns)


def _campaign_form_context(campaign: FundraisingCampaign | None):
    return {
        "campaign": campaign,
        "is_new": campaign is None or campaign.id is None,
        "statuses": CAMPAIGN_STATUSES,
    }


@billing_bp.route("/admin/campaigns/new", methods=["GET", "POST"])
@require_csrf
@role_required("platform_owner")
def admin_campaign_new():
    db = get_db()
    campaign = FundraisingCampaign(status="draft", show_supporter_list=True)
    if request.method == "POST":
        _apply_campaign_form(campaign, exclude_id=None)
        error = _validate_campaign(campaign)
        if error:
            flash(error, "error")
        else:
            db.add(campaign)
            db.commit()
            flash(f"Drive “{campaign.title}” created.", "success")
            return redirect(url_for("billing.admin_campaigns"))
    return render_template("billing/admin/campaign_form.html",
                           **_campaign_form_context(campaign))


@billing_bp.route("/admin/campaigns/<int:campaign_id>/edit",
                  methods=["GET", "POST"])
@require_csrf
@role_required("platform_owner")
def admin_campaign_edit(campaign_id: int):
    db = get_db()
    campaign = db.get(FundraisingCampaign, campaign_id)
    if campaign is None:
        abort(404)
    if request.method == "POST":
        _apply_campaign_form(campaign, exclude_id=campaign.id)
        error = _validate_campaign(campaign)
        if error:
            flash(error, "error")
        else:
            db.commit()
            flash(f"Drive “{campaign.title}” saved.", "success")
            return redirect(url_for("billing.admin_campaigns"))
    return render_template("billing/admin/campaign_form.html",
                           **_campaign_form_context(campaign))


def _apply_campaign_form(campaign: FundraisingCampaign,
                         exclude_id: int | None) -> None:
    form = request.form
    campaign.title = (form.get("title") or "").strip()
    raw_slug = (form.get("slug") or "").strip()
    campaign.slug = _unique_slug(
        FundraisingCampaign, _slugify(raw_slug or campaign.title),
        exclude_id=exclude_id)
    campaign.description = (form.get("description") or "").strip()
    campaign.goal_cents = _dollars_to_cents(form.get("goal_dollars"))
    campaign.starts_at = _parse_date(form.get("starts_at"))
    campaign.ends_at = _parse_date(form.get("ends_at"))
    status = (form.get("status") or "draft").strip()
    campaign.status = status if status in CAMPAIGN_STATUSES else "draft"
    campaign.show_supporter_list = "show_supporter_list" in form


def _validate_campaign(campaign: FundraisingCampaign) -> str | None:
    if not campaign.title:
        return "A title is required."
    return None


@billing_bp.route("/admin/campaigns/<int:campaign_id>/delete", methods=["POST"])
@require_csrf
@role_required("platform_owner")
def admin_campaign_delete(campaign_id: int):
    db = get_db()
    campaign = db.get(FundraisingCampaign, campaign_id)
    if campaign is None:
        abort(404)
    if campaign.contributions:
        flash("That drive has contributions on record, so it can't be deleted. "
              "Set it to “ended” instead — the history stays intact.", "error")
        return redirect(url_for("billing.admin_campaigns"))
    db.delete(campaign)
    db.commit()
    flash(f"Drive “{campaign.title}” deleted.", "success")
    return redirect(url_for("billing.admin_campaigns"))


# -- tiers -------------------------------------------------------------------

@billing_bp.route("/admin/tiers")
@role_required("platform_owner")
def admin_tiers():
    db = get_db()
    tiers = list(db.execute(
        select(SubscriptionTier).order_by(SubscriptionTier.id)
    ).scalars())
    return render_template("billing/admin/tiers.html", tiers=tiers)


def _tier_form_context(tier: SubscriptionTier | None):
    return {
        "tier": tier,
        "is_new": tier is None or tier.id is None,
        "audiences": TIER_AUDIENCES,
        "kinds": TIER_KINDS,
    }


@billing_bp.route("/admin/tiers/new", methods=["GET", "POST"])
@require_csrf
@role_required("platform_owner")
def admin_tier_new():
    db = get_db()
    tier = SubscriptionTier(audience="magazine", kind="recurring",
                            is_active=False, perks=[])
    if request.method == "POST":
        _apply_tier_form(tier, exclude_id=None)
        error = _validate_tier(tier)
        if error:
            flash(error, "error")
        else:
            db.add(tier)
            db.commit()
            flash(f"Tier “{tier.name}” created.", "success")
            return redirect(url_for("billing.admin_tiers"))
    return render_template("billing/admin/tier_form.html",
                           **_tier_form_context(tier))


@billing_bp.route("/admin/tiers/<int:tier_id>/edit", methods=["GET", "POST"])
@require_csrf
@role_required("platform_owner")
def admin_tier_edit(tier_id: int):
    db = get_db()
    tier = db.get(SubscriptionTier, tier_id)
    if tier is None:
        abort(404)
    if request.method == "POST":
        _apply_tier_form(tier, exclude_id=tier.id)
        error = _validate_tier(tier)
        if error:
            flash(error, "error")
        else:
            db.commit()
            flash(f"Tier “{tier.name}” saved.", "success")
            return redirect(url_for("billing.admin_tiers"))
    return render_template("billing/admin/tier_form.html",
                           **_tier_form_context(tier))


def _apply_tier_form(tier: SubscriptionTier, exclude_id: int | None) -> None:
    form = request.form
    tier.name = (form.get("name") or "").strip()
    raw_slug = (form.get("slug") or "").strip()
    tier.slug = _unique_slug(
        SubscriptionTier, _slugify(raw_slug or tier.name),
        exclude_id=exclude_id)
    audience = (form.get("audience") or "magazine").strip()
    tier.audience = audience if audience in TIER_AUDIENCES else "magazine"
    kind = (form.get("kind") or "recurring").strip()
    tier.kind = kind if kind in TIER_KINDS else "recurring"
    tier.description = (form.get("description") or "").strip()
    tier.perks = [line.strip() for line in (form.get("perks") or "").splitlines()
                  if line.strip()]
    price = _dollars_to_cents(form.get("price_dollars"))
    tier.price_cents = price  # None = "to be announced"
    tier.is_active = "is_active" in form


def _validate_tier(tier: SubscriptionTier) -> str | None:
    if not tier.name:
        return "A name is required."
    return None


@billing_bp.route("/admin/tiers/<int:tier_id>/delete", methods=["POST"])
@require_csrf
@role_required("platform_owner")
def admin_tier_delete(tier_id: int):
    db = get_db()
    tier = db.get(SubscriptionTier, tier_id)
    if tier is None:
        abort(404)
    held = db.query(UserSubscription).filter_by(tier_id=tier.id).count()
    if held:
        flash("That tier has subscriber records, so it can't be deleted. "
              "Turn off “active” instead — the history stays intact.", "error")
        return redirect(url_for("billing.admin_tiers"))
    db.delete(tier)
    db.commit()
    flash(f"Tier “{tier.name}” deleted.", "success")
    return redirect(url_for("billing.admin_tiers"))


# -- contributions (read-only + refund) ----------------------------------------

@billing_bp.route("/admin/contributions")
@role_required("platform_owner")
def admin_contributions():
    db = get_db()
    contributions = list(db.execute(
        select(Contribution).order_by(Contribution.created_at.desc(),
                                     Contribution.id.desc())
    ).scalars())
    return render_template("billing/admin/contributions.html",
                           contributions=contributions, live=billing_live())


@billing_bp.route("/admin/contributions/<int:contribution_id>/refund",
                  methods=["POST"])
@require_csrf
@role_required("platform_owner")
def admin_contribution_refund(contribution_id: int):
    db = get_db()
    contribution = db.get(Contribution, contribution_id)
    if contribution is None:
        abort(404)
    if contribution.status != "completed":
        flash("Only completed contributions can be refunded.", "error")
        return redirect(url_for("billing.admin_contributions"))
    provider = get_provider()
    if provider.name == "null" or not contribution.provider_payment_ref:
        flash("Payment rails aren't connected, so there's nothing to refund "
              "through. No money moved.", "error")
        return redirect(url_for("billing.admin_contributions"))
    if provider.refund_contribution(
            provider_payment_ref=contribution.provider_payment_ref):
        contribution.status = "refunded"
        db.commit()
        flash(f"Refunded ${float(contribution.amount_cents or 0) / 100:.2f} "
              f"to {contribution.display_name or 'the donor'}.", "success")
    else:
        flash("The payment provider didn't complete the refund — try again "
              "in a bit.", "error")
    return redirect(url_for("billing.admin_contributions"))
