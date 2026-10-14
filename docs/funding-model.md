# Inktrovert magazine funding model — subscribe + donate + fundraise

Her model for the editorial layer (2026-10-14, her words): the magazine/news
section runs on **subscriptions, one-time donations, and fundraising
campaigns/drives** — to cover costs and make profit. This engine belongs to
the magazine section only. It is **separate** from the future studio-side
paid tiers (Professional / Studio Partner), which will plug into the same
tables under a different audience.

Payment rails are **undecided**. Nothing here moves money, talks to a
gateway, or costs anything. All provider wiring lives behind the
`app.payments.PaymentProvider` interface (stubs only).

## The three engines

### 1. Subscribe — recurring tiers with exclusives
- `subscription_tiers` rows with `audience="magazine"`, `kind="recurring"`.
- Exclusives live in the `perks` JSON list (e.g. subscriber-only flash drops,
  early-access windows, behind-the-chair content, event presales, digital
  issues). Content gating checks `user_subscriptions` for an active magazine
  tier — helper to add later: `user_has_active_tier(user, audience="magazine")`.
- `kind="founding"` covers limited founding-supporter drives: a tier sold
  during one campaign window, optionally linked to a `fundraising_campaigns`
  row by convention (add an explicit FK when the flow is built).

### 2. Donate — one-time contributions
- `contributions` rows: `amount_cents`, `status` (pending/completed/refunded/
  failed), optional `user_id` (guests allowed), optional `campaign_id`,
  `message`, `is_anonymous`, `display_name` for the supporter wall.
- Offline money (cash, etc.) is recorded with `provider="manual"` so the
  books stay complete without a gateway.

### 3. Fundraise — campaigns with goals and supporter lists
- `fundraising_campaigns`: `title`, `goal_cents`, `starts_at`/`ends_at`,
  `status` (draft/active/ended), `show_supporter_list`.
- `raised_cents` and `supporter_names` are derived from linked completed
  contributions — no separate bookkeeping table to drift out of sync.
- Typical uses: founding supporter drive at launch, seasonal drives,
  special-project funding (e.g. print issue, event coverage).

## Magazine vs studio tiers

`subscription_tiers.audience` splits the two businesses sharing one table:

| audience   | owner            | examples (later)              |
|------------|------------------|-------------------------------|
| `magazine` | her editorial    | subscriber tiers, founding    |
| `studio`   | platform side    | Professional, Studio Partner  |

Queries for magazine entitlements always filter `audience="magazine"`, so
studio tiers can never leak into editorial exclusives and vice versa.

## Plugging in rails later (checklist)

1. Write `StripeProvider(PaymentProvider)` (or whichever rails she picks) in
   a new module; `register_provider()` it at app startup.
2. Set `PAYMENT_PROVIDER` in config; `get_provider()` is the only call site.
3. Backfill `provider_product_ref` on tiers from the provider dashboard.
4. Add checkout routes returning `provider.create_*_checkout(...).url`,
   and a webhook route verifying signatures then applying
   `handle_webhook(...)` results to `user_subscriptions` /
   `contributions` statuses.
5. Webhook handler is the **only** writer of billing status — never trust
   the browser redirect alone.

## Deliberately not built yet

No checkout routes, no webhook endpoint, no billing cron, no dunning emails,
no price figures (all `price_cents` nullable). The tables, the interface,
and the audience split are the foundation; money moves only after she
chooses rails.
