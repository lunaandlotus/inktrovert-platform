"""Payment provider interface — stubs only. Rails are undecided.

Every money movement in the magazine funding engine (subscriptions,
donations, campaign contributions) goes through a PaymentProvider. The app
never talks to a gateway directly: when the founder picks rails, the work is
one new provider class plus config — no business-logic rewrites.

Today only NullProvider exists. It records intent on the local rows
(statuses stay "pending") and never touches the network, moves no money,
and costs nothing.

Future provider contract (e.g. StripeProvider later):
  * create_subscription_checkout(...) -> Checkout
  * cancel_subscription(UserSubscription) -> bool
  * create_donation_checkout(...) -> Checkout
  * handle_webhook(raw_body, signature) -> WebhookEvent | None
  * refund_contribution(Contribution) -> bool
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Checkout:
    """What the UI needs to send the supporter to the provider."""
    url: str = ""
    provider_ref: str = ""
    provider: str = "null"


@dataclass
class WebhookEvent:
    """Normalized event from a provider webhook, after signature verification."""
    kind: str = ""  # subscription.created/updated/canceled, contribution.completed/refunded
    provider: str = "null"
    provider_ref: str = ""
    user_id: Optional[int] = None
    tier_id: Optional[int] = None
    contribution_id: Optional[int] = None
    status: str = ""
    meta: dict = field(default_factory=dict)


class PaymentProvider:
    """Interface every real provider must implement."""

    name = "base"

    def create_subscription_checkout(self, *, user_id: int, tier_id: int,
                                     success_url: str, cancel_url: str) -> Checkout:
        raise NotImplementedError

    def cancel_subscription(self, *, provider_subscription_ref: str) -> bool:
        raise NotImplementedError

    def create_donation_checkout(self, *, user_id: Optional[int],
                                 amount_cents: int,
                                 campaign_id: Optional[int],
                                 success_url: str, cancel_url: str) -> Checkout:
        raise NotImplementedError

    def handle_webhook(self, raw_body: bytes, signature: str) -> Optional[WebhookEvent]:
        raise NotImplementedError

    def refund_contribution(self, *, provider_payment_ref: str) -> bool:
        raise NotImplementedError


class NullProvider(PaymentProvider):
    """No-op provider. Safe default: checkout URLs are empty, webhooks are
    ignored, and nothing is ever charged or refunded."""

    name = "null"

    def create_subscription_checkout(self, *, user_id: int, tier_id: int,
                                     success_url: str, cancel_url: str) -> Checkout:
        return Checkout(provider=self.name)

    def cancel_subscription(self, *, provider_subscription_ref: str) -> bool:
        return False

    def create_donation_checkout(self, *, user_id: Optional[int],
                                 amount_cents: int,
                                 campaign_id: Optional[int],
                                 success_url: str, cancel_url: str) -> Checkout:
        return Checkout(provider=self.name)

    def handle_webhook(self, raw_body: bytes, signature: str) -> Optional[WebhookEvent]:
        return None

    def refund_contribution(self, *, provider_payment_ref: str) -> bool:
        return False


_PROVIDERS: dict[str, PaymentProvider] = {"null": NullProvider()}


def register_provider(provider: PaymentProvider) -> None:
    _PROVIDERS[provider.name] = provider


def get_provider(name: str = "null") -> PaymentProvider:
    try:
        return _PROVIDERS[name]
    except KeyError:
        raise ValueError(f"unknown payment provider {name!r}; "
                         f"registered: {sorted(_PROVIDERS)}")
