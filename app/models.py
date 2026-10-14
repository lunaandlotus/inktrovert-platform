"""Inktrovert platform models — multi-tenant: many studios, artists, brands.

Phases 1-2 (built now): accounts + roles, editorial (issues/stories/events/
newsletter), directory profiles + portfolio + flash, claim flow.
Phases 3-5 (models stubbed here so later phases layer on without rewrites):
magazine funding engine — SubscriptionTier/UserSubscription (subscribe),
Contribution (donate), FundraisingCampaign (fundraise) — plus Review +
BookingInquiry (4), SupplyListing (5).
No payments move: price fields are nullable placeholders and all provider
wiring lives behind the app.payments interface (stubs only).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer,
                        String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

VALID_ROLES = (
    "platform_owner",      # runs the platform; publishing + claim approvals
    "collector",           # browses, follows, saves; reviews in phase 4
    "tattoo_artist",
    "piercer",
    "independent_artist",  # not tied to a studio
    "studio_owner",
    "studio_manager",
    "studio_team_member",
    "approved_brand",      # approved supplier/brand accounts
)

# A user may hold several roles (e.g. an artist who is also a collector).
PROFILE_KINDS = ("tattoo_artist", "piercer", "independent_artist", "studio", "brand")


# ---------------------------------------------------------------------------
# US states — state-by-state news coverage.
# Stories carry a 2-letter code in `Story.state`; leads carry a suggested
# code in `StoryLead.suggested_state`; a profile designated as a state's
# featured studio carries the code in `Profile.featured_state`.
# ---------------------------------------------------------------------------

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}

_NAME_TO_CODE = {name.casefold(): code for code, name in US_STATES.items()}


def normalize_state(value: str | None) -> str | None:
    """Turn anything state-like ("WY", "wy", "Wyoming") into a 2-letter code.

    Returns None for blank or unrecognized input — international and
    non-state content simply stays untagged.
    """
    if not value:
        return None
    text = value.strip()
    if len(text) == 2 and text.upper() in US_STATES:
        return text.upper()
    return _NAME_TO_CODE.get(text.casefold())


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    claimed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 nullable=False)

    roles: Mapped[list[Role]] = relationship("Role", secondary="user_roles", lazy="selectin")
    sessions: Mapped[list["LoginSession"]] = relationship("LoginSession", back_populates="user",
                                                          cascade="all, delete-orphan")

    def has_role(self, name: str) -> bool:
        return any(r.name == name for r in self.roles)

    def role_names(self) -> list[str]:
        return [r.name for r in self.roles]


class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                         primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"),
                                         primary_key=True)


class LoginSession(Base):
    """Server-side login sessions; only a SHA-256 of the token is stored."""
    __tablename__ = "login_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                         nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 nullable=False)

    user: Mapped[User] = relationship("User", back_populates="sessions")


# ---------------------------------------------------------------------------
# Phase 1 — Editorial
# ---------------------------------------------------------------------------

STORY_CATEGORIES = ("news", "spotlight", "interview", "product-launch", "recent-work")


class Issue(Base):
    """A digital edition of the Inktrovert magazine."""
    __tablename__ = "issues"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), unique=True, nullable=False)
    blurb: Mapped[str] = mapped_column(Text, default="", nullable=False)
    cover_image: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_free: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 nullable=False)

    stories: Mapped[list["Story"]] = relationship("Story", back_populates="issue",
                                                  order_by="Story.sort_order")


class Story(Base):
    __tablename__ = "stories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    issue_id: Mapped[int | None] = mapped_column(ForeignKey("issues.id", ondelete="SET NULL"),
                                                 nullable=True)
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    slug: Mapped[str] = mapped_column(String(270), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False, default="news")
    excerpt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    cover_image: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    author_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 nullable=False)
    # US state this story is about, as a 2-letter code (see US_STATES).
    # Nullable: international stories, national trends, and older stories
    # stay untagged and appear in the issue overview.
    state: Mapped[str | None] = mapped_column(String(2), nullable=True, index=True)

    issue: Mapped[Issue | None] = relationship("Issue", back_populates="stories")

    @property
    def state_name(self) -> str | None:
        return US_STATES.get(self.state) if self.state else None


class Event(Base):
    """Industry events calendar. Submissions need owner approval."""
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    slug: Mapped[str] = mapped_column(String(270), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    venue_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    city: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    state: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    # pending / approved / rejected
    submitted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id",
                                                                        ondelete="SET NULL"),
                                                             nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 nullable=False)


class NewsletterEdition(Base):
    """Archive of sent newsletter editions (sending itself is out of scope)."""
    __tablename__ = "newsletter_editions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject: Mapped[str] = mapped_column(String(250), nullable=False)
    slug: Mapped[str] = mapped_column(String(270), unique=True, nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 nullable=False)


LEAD_STATUSES = ("new", "reviewing", "promoted", "discarded")


class StoryLead(Base):
    """A story lead in the owner's inbox.

    Daily findings from the external gathering job land here as draft leads:
    headline, source link, date found, and a suggested angle. The owner
    reviews them, promotes the good ones to full stories, or discards the
    rest. Dedupe: `url_hash` (SHA-256 of the normalized source URL) is
    unique, so the same link can never be suggested twice; headline matching
    is a secondary soft check in app.leads.
    """
    __tablename__ = "story_leads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    headline: Mapped[str] = mapped_column(String(300), nullable=False)
    source_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    found_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 nullable=False)
    suggested_angle: Mapped[str] = mapped_column(Text, default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # US state the gathered item is about, as a 2-letter code (see US_STATES).
    # Captured at ingest so the daily news gathering feeds state-tagged leads;
    # carried onto the story when the lead is promoted.
    suggested_state: Mapped[str | None] = mapped_column(String(2), nullable=True)

    @property
    def suggested_state_name(self) -> str | None:
        return US_STATES.get(self.suggested_state) if self.suggested_state else None
    # new / reviewing / promoted / discarded
    status: Mapped[str] = mapped_column(String(20), default="new", nullable=False, index=True)
    promoted_story_id: Mapped[int | None] = mapped_column(
        ForeignKey("stories.id", ondelete="SET NULL"), nullable=True)
    submitted_by: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 onupdate=utcnow, nullable=False)

    promoted_story: Mapped[Story | None] = relationship("Story",
                                                        foreign_keys=[promoted_story_id])


# ---------------------------------------------------------------------------
# Phase 2 — Directory profiles + portfolio + flash
# ---------------------------------------------------------------------------

FLASH_STATUSES = ("available", "reserved", "sold")
CLAIM_STATUSES = ("unclaimed", "pending", "claimed")


class Profile(Base):
    """A public listing: an artist, a studio, or a brand."""
    __tablename__ = "profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)  # PROFILE_KINDS
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), unique=True, nullable=False)
    bio: Mapped[str] = mapped_column(Text, default="", nullable=False)
    city: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    state: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    country: Mapped[str] = mapped_column(String(60), default="USA", nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    specialties: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    services: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    phone: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    email: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    website: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    # Phase 4 hook: how collectors book. "platform" or "external".
    booking_mode: Mapped[str] = mapped_column(String(20), default="external", nullable=False)
    booking_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    policies: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Claim state. verified = owner-confirmed badge shown publicly.
    claim_status: Mapped[str] = mapped_column(String(20), default="unclaimed", nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    claimed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id",
                                                                      ondelete="SET NULL"),
                                                           nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id",
                                                                      ondelete="SET NULL"),
                                                           nullable=True)
    is_listed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Featured promotion: homepage showcase, state-page features, etc.
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Designated featured studio for a US state page, as a 2-letter code
    # (see US_STATES). Shown at the top of that state's hub page.
    featured_state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 onupdate=utcnow, nullable=False)

    collections: Mapped[list["PortfolioCollection"]] = relationship(
        "PortfolioCollection", back_populates="profile", cascade="all, delete-orphan",
        order_by="PortfolioCollection.sort_order")
    flash: Mapped[list["FlashPiece"]] = relationship(
        "FlashPiece", back_populates="profile", cascade="all, delete-orphan")
    links: Mapped[list["ProfileLink"]] = relationship(
        "ProfileLink", back_populates="profile", cascade="all, delete-orphan",
        order_by="ProfileLink.sort_order, ProfileLink.id")


class PortfolioCollection(Base):
    __tablename__ = "portfolio_collections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"),
                                            nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    profile: Mapped[Profile] = relationship("Profile", back_populates="collections")
    items: Mapped[list["PortfolioItem"]] = relationship(
        "PortfolioItem", back_populates="collection", cascade="all, delete-orphan",
        order_by="PortfolioItem.sort_order")


class PortfolioItem(Base):
    __tablename__ = "portfolio_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("portfolio_collections.id",
                                                          ondelete="CASCADE"),
                                               nullable=False, index=True)
    image: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    caption: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    collection: Mapped[PortfolioCollection] = relationship("PortfolioCollection",
                                                           back_populates="items")


class FlashPiece(Base):
    __tablename__ = "flash_pieces"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"),
                                            nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="available", nullable=False)
    image: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 nullable=False)

    profile: Mapped[Profile] = relationship("Profile", back_populates="flash")


AFFILIATION_STATUSES = ("pending", "accepted", "declined")


class TeamAffiliation(Base):
    """An artist profile affiliated with a studio profile.

    Invites start as "pending": the studio asks, the artist accepts or
    declines. Only "accepted" rows show on public profiles. A declined or
    cancelled invite leaves no public trace.
    """
    __tablename__ = "team_affiliations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    studio_profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"),
                                                   nullable=False, index=True)
    member_profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"),
                                                   nullable=False, index=True)
    role_label: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # pending / accepted / declined
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    invited_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id",
                                                                      ondelete="SET NULL"),
                                                           nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("studio_profile_id", "member_profile_id",
                                       name="uq_team_affiliation"),)


class ProfileLink(Base):
    """A labelled link on an artist/studio/brand profile — Instagram,
    Facebook, TikTok, website, shop, booking page, whatever they want to
    share. Owners add and remove them any time."""
    __tablename__ = "profile_links"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"),
                                            nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 nullable=False)

    profile: Mapped[Profile] = relationship("Profile", back_populates="links")


class ClaimRequest(Base):
    """A user asking to take ownership of a profile listing."""
    __tablename__ = "claim_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"),
                                            nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                         nullable=False, index=True)
    # owner / manager / team_member / artist / brand_rep
    # (attribute named claimer_relationship: a plain `relationship` attribute
    # would shadow sqlalchemy.orm.relationship in the class body)
    claimer_relationship: Mapped[str] = mapped_column("relationship", String(40),
                                                     nullable=False)
    evidence_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    evidence_file: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    # pending / approved / rejected
    reviewer_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    profile: Mapped[Profile] = relationship("Profile")
    user: Mapped[User] = relationship("User")


# ---------------------------------------------------------------------------
# Magazine funding engine — subscribe + donate + fundraise.
#
# Her model for the editorial layer (2026-10-14): subscriptions, one-time
# donations, and fundraising campaigns/drives cover costs and make profit.
# This engine belongs to the magazine/news section ONLY — it is distinct
# from the future studio-side paid tiers (audience="studio", e.g.
# Professional / Studio Partner), which plug into the same tables later.
# Payment rails are undecided: amounts are nullable placeholders, statuses
# are workflow states, and every money movement goes through the
# app.payments provider interface (stubs only — nothing real, no network).
# ---------------------------------------------------------------------------

# SubscriptionTier.audience: "magazine" (her editorial section) or "studio".
TIER_AUDIENCES = ("magazine", "studio")


class SubscriptionTier(Base):
    """A paid tier. Magazine tiers carry the subscriber exclusives
    (subscriber-only flash drops, early access, behind-the-chair content,
    event presales, digital issues). Studio tiers come later."""
    __tablename__ = "subscription_tiers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    audience: Mapped[str] = mapped_column(String(20), nullable=False)  # TIER_AUDIENCES
    # recurring / founding (founding = limited drive tied to a campaign)
    kind: Mapped[str] = mapped_column(String(20), default="recurring", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    perks: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)  # TBD
    # Provider-side product/price ids, filled when rails are chosen.
    provider_product_ref: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 nullable=False)


class UserSubscription(Base):
    """A user's holding of a tier. Billing state mirrors the provider;
    the provider is the source of truth once rails exist."""
    __tablename__ = "user_subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                         nullable=False, index=True)
    tier_id: Mapped[int] = mapped_column(ForeignKey("subscription_tiers.id",
                                                    ondelete="CASCADE"),
                                         nullable=False)
    # inactive / trialing / active / past_due / canceled
    status: Mapped[str] = mapped_column(String(20), default="inactive", nullable=False)
    provider: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    provider_customer_ref: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    provider_subscription_ref: Mapped[str] = mapped_column(String(200), default="",
                                                            nullable=False)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                                nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tier: Mapped[SubscriptionTier] = relationship("SubscriptionTier")
    user: Mapped[User] = relationship("User")


class FundraisingCampaign(Base):
    """A fundraising drive: founding supporter campaigns, seasonal drives,
    special projects. Has a goal and a public supporter list."""
    __tablename__ = "fundraising_campaigns"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    goal_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # draft / active / ended
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    show_supporter_list: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id",
                                                                      ondelete="SET NULL"),
                                                           nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 nullable=False)

    contributions: Mapped[list["Contribution"]] = relationship(
        "Contribution", back_populates="campaign", cascade="all, delete-orphan")

    @property
    def raised_cents(self) -> int:
        return sum(c.amount_cents or 0 for c in self.contributions
                   if c.status == "completed")

    @property
    def supporter_names(self) -> list[str]:
        names = [c.display_name for c in self.contributions
                 if c.status == "completed" and not c.is_anonymous and c.display_name]
        seen = set()
        return [n for n in names if not (n in seen or seen.add(n))]


class Contribution(Base):
    """A one-time donation. May stand alone or count toward a campaign.
    Offline/manual contributions (cash, etc.) can be recorded with
    provider="manual" so the books stay complete."""
    __tablename__ = "contributions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"),
                                                nullable=True, index=True)
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("fundraising_campaigns.id", ondelete="SET NULL"),
        nullable=True, index=True)
    amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # pending / completed / refunded / failed
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    provider: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    provider_payment_ref: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 nullable=False)

    campaign: Mapped[FundraisingCampaign | None] = relationship("FundraisingCampaign",
                                                                back_populates="contributions")
    user: Mapped[User | None] = relationship("User")


class Review(Base):
    """Phase 4: collector reviews of profiles, with moderation."""
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"),
                                            nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                         nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    # pending / published / hidden
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 nullable=False)


class BookingInquiry(Base):
    """Phase 4: collector reaches out; mode = platform booking or external redirect."""
    __tablename__ = "booking_inquiries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"),
                                            nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                         nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    mode: Mapped[str] = mapped_column(String(20), default="inquiry", nullable=False)
    # inquiry / platform / external
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 nullable=False)


# ---------------------------------------------------------------------------
# Podcasts — part of the magazine/editorial layer.
#
# Two series: one for collectors (artist stories, interviews, studio
# features), one for artists/pros (industry news + continued learning:
# technique, business, professional education). Episodes can later gate
# behind subscriptions; audio storage is abstracted (local uploads for dev,
# provider path later). Episodes link to related stories and profiles.
# ---------------------------------------------------------------------------

PODCAST_AUDIENCES = ("collectors", "professionals")

# What the show is about: tattoo, piercing, or both. Nullable — older rows
# stay untagged; the piercing seed backfills the curated series.
PODCAST_TOPICS = ("tattoo", "piercing", "both")


class PodcastSeries(Base):
    __tablename__ = "podcast_series"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), unique=True, nullable=False)
    # collectors / professionals
    audience: Mapped[str] = mapped_column(String(20), nullable=False)
    # tattoo / piercing / both (see PODCAST_TOPICS)
    topic: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    cover_image: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 nullable=False)

    episodes: Mapped[list["PodcastEpisode"]] = relationship(
        "PodcastEpisode", back_populates="series", cascade="all, delete-orphan",
        order_by="PodcastEpisode.episode_number")


class PodcastEpisode(Base):
    __tablename__ = "podcast_episodes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("podcast_series.id",
                                                      ondelete="CASCADE"),
                                           nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    slug: Mapped[str] = mapped_column(String(270), unique=True, nullable=False)
    episode_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # show notes
    # Relative path under the uploads dir (e.g. "audio/ep1.mp3").
    audio_file: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    related_story_id: Mapped[int | None] = mapped_column(
        ForeignKey("stories.id", ondelete="SET NULL"), nullable=True)
    related_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                          nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 nullable=False)

    series: Mapped[PodcastSeries] = relationship("PodcastSeries", back_populates="episodes")
    related_story: Mapped[Story | None] = relationship("Story",
                                                       foreign_keys=[related_story_id])
    related_profile: Mapped[Profile | None] = relationship(
        "Profile", foreign_keys=[related_profile_id])


class SupplyListing(Base):
    """Phase 5: verified B2B supply marketplace (pros sell to pros)."""
    __tablename__ = "supply_listings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seller_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                                nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    # aftercare / balm / needles / ink / machines / disposables / stencil / other
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    # draft / listed / sold / removed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 nullable=False)


# ---------------------------------------------------------------------------
# Books — magazine/editorial layer, same standing as podcasts.
#
# Shelves: textbooks (training manuals for artists/pros), artist books
# (flash books & monographs published by artists, for collectors), guides
# (reference/technique/history), and business (running the shop).
# Crafts: tattoo / piercing / business. Audiences mirror podcasts:
# collectors (enthusiasts) vs professionals (working artists/piercers).
# Audiobook flags are set ONLY for verified audio editions.
# ---------------------------------------------------------------------------

BOOK_CRAFTS = ("tattoo", "piercing", "business")
BOOK_AUDIENCES = ("collectors", "professionals")
BOOK_KINDS = ("guide", "artist", "textbook")


class Book(Base):
    __tablename__ = "books"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    slug: Mapped[str] = mapped_column(String(270), unique=True, nullable=False)
    author: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    publisher: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    isbn: Mapped[str] = mapped_column(String(30), default="", nullable=False)
    # tattoo / piercing / business
    craft: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # collectors / professionals
    audience: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # guide / artist / textbook
    kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # 1-2 plainspoken sentences on why it matters to tattooists/piercers.
    why_relevant: Mapped[str] = mapped_column(Text, default="", nullable=False)
    cover_image: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    buy_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    # Set ONLY when a real audio edition was verified to exist.
    has_audiobook: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    audiobook_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 nullable=False)


class TextbookNotify(Base):
    """Email signups for Angie Valentin's coming-soon apprentice textbook."""
    __tablename__ = "textbook_notify"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 nullable=False)
