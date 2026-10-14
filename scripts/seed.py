"""Seed the Inktrovert dev database with clearly-labeled sample content.

ALL content created here is sample data for previewing the app — stories
carry author "Seed data", profile bios start with "Sample profile".
Run:  cd ~/workspace/inktrovert-platform && .venv/bin/python scripts/seed.py
Idempotent: exits quietly if the seed owner user already exists.

Seed logins (dev only):
  owner@inktrovert.local     / InktrovertOwner1!   (platform_owner)
  collector@inktrovert.local / InktrovertFan1!     (collector)
  artist@inktrovert.local    / InktrovertPro1!     (tattoo_artist + collector)
"""
from __future__ import annotations

import os
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.auth import ensure_roles, register_user  # noqa: E402
from app.config import Config  # noqa: E402
from app.db import create_all, init_engine, session_scope  # noqa: E402
from app.leads import ingest_lead  # noqa: E402
from app.models import (ClaimRequest, Event, FlashPiece, FundraisingCampaign,  # noqa: E402
                        Issue, NewsletterEdition, PodcastEpisode, PodcastSeries,
                        PortfolioCollection, PortfolioItem, Profile,
                        Story, SubscriptionTier, TeamAffiliation, User, utcnow)

SAMPLE = "Sample profile — created by the seed script for previewing the app. "


def _silent_wav(path: str, seconds: int = 5) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        return
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\x00\x00" * 22050 * seconds)


def main() -> None:
    # App context: register_user()/ensure_roles() use flask.g via get_db().
    from app import create_app  # noqa: E402
    app = create_app()
    with app.app_context():
        _seed()


def _seed() -> None:
    with session_scope() as db:
        ensure_roles(db)
        if db.query(User).filter_by(email="owner@inktrovert.local").one_or_none():
            print("Seed already applied — nothing to do.")
            return

        owner = register_user("owner@inktrovert.local", "InktrovertOwner1!",
                              "Inktrovert Owner", roles=["platform_owner"])
        collector = register_user("collector@inktrovert.local", "InktrovertFan1!",
                                  "Sam Collector", roles=["collector"])
        artist = register_user("artist@inktrovert.local", "InktrovertPro1!",
                               "Maya Reyes", roles=["tattoo_artist", "collector"])

        # --- Editorial: issue + stories ------------------------------------
        issue = Issue(number=1, title="Launch Issue", slug="issue-1-launch",
                      blurb="The first Inktrovert industry issue: openings, "
                            "aftercare science, and fine-line portfolios.",
                      cover_image="img/ph-1.svg", is_published=True,
                      published_at=utcnow())
        db.add(issue)
        db.flush()

        stories = [
            ("Welcome to Inktrovert", "news",
             "Why the industry needed one trusted home for news, discovery, and craft.",
             "This is the seed story body. The real first issue will say it better: "
             "collectors deserve honest discovery, and professionals deserve a "
             "publication that treats the craft seriously.", True),
            ("Aftercare, honestly: what actually helps ink heal", "news",
             "Wash, balm, wrap — what the evidence and the old hands agree on.",
             "Seed body: gentle washing, thin balm layers, and leaving the wrap "
             "on as directed. Your artist's aftercare sheet is the final word.", True),
            ("Studio spotlight: a Casper shop built on referrals", "spotlight",
             "How one small studio keeps its books full without shouting.",
             "Seed body: clean work, honest consults, and follow-through. "
             "The rest is word of mouth.", True),
            ("Draft: interview with a traveling piercer", "interview",
             "Guest spots, sterile technique on the road, and reading a room.",
             "Seed body — unpublished draft.", False),
        ]
        for i, (title, cat, excerpt, body, pub) in enumerate(stories):
            slug = title.lower().replace(":", "").replace(",", "")
            slug = "-".join(slug.split())[:200]
            db.add(Story(
                issue_id=issue.id if pub else None, title=title, slug=slug,
                category=cat, excerpt=excerpt, body=body,
                cover_image="img/ph-2.svg", author_name="Seed data",
                sort_order=i, is_published=pub,
                published_at=utcnow() if pub else None))

        # --- Events ----------------------------------------------------------
        from datetime import timedelta
        db.add(Event(
            title="Rocky Mountain Tattoo Gathering (sample)", slug="rocky-mountain-gathering-sample",
            description="Sample event for previewing the calendar.",
            venue_name="Sample Expo Hall", city="Denver", state="CO",
            starts_at=utcnow() + timedelta(days=60),
            ends_at=utcnow() + timedelta(days=62),
            url="https://example.com", status="approved",
            submitted_by_user_id=owner.id))
        db.add(Event(
            title="Flash day fundraiser (awaiting review)", slug="flash-day-fundraiser-sample",
            description="Sample pending submission.", venue_name="Sample Studio",
            city="Casper", state="WY", starts_at=utcnow() + timedelta(days=30),
            status="pending", submitted_by_user_id=collector.id))

        # --- Directory ---------------------------------------------------------
        studio = Profile(
            kind="studio", display_name="Iron & Bloom Tattoo", slug="iron-bloom-tattoo",
            bio=SAMPLE + "A blackwork and fine-line studio in Casper, Wyoming.",
            city="Casper", state="WY", specialties=["blackwork", "fine line"],
            services=["tattoo", "consultation"], phone="307-555-0110",
            website="https://example.com", booking_mode="external",
            booking_url="https://example.com/book",
            policies="Deposits required for large work. 18+ with ID.",
            claim_status="claimed", verified=True, claimed_by_user_id=artist.id,
            created_by_user_id=owner.id)
        db.add(studio)
        db.flush()

        coll = PortfolioCollection(profile_id=studio.id, title="Healed blackwork",
                                   description="Sample collection.", sort_order=0)
        db.add(coll)
        db.flush()
        for i in range(2):
            db.add(PortfolioItem(collection_id=coll.id, image="img/ph-3.svg",
                                 caption=f"Sample healed piece {i + 1}", sort_order=i))
        db.add(FlashPiece(profile_id=studio.id, title="Moth flash", price_cents=12000,
                          size='4"', status="available", image="img/ph-3.svg"))
        db.add(FlashPiece(profile_id=studio.id, title="Dagger flash", price_cents=15000,
                          size='5"', status="sold", image="img/ph-3.svg"))

        maya = Profile(
            kind="tattoo_artist", display_name="Maya Reyes", slug="maya-reyes",
            bio=SAMPLE + "Fine-line tattoo artist.",
            city="Casper", state="WY", specialties=["fine line", "botanical"],
            services=["tattoo"], claim_status="pending",
            created_by_user_id=artist.id)
        db.add(maya)
        brand = Profile(
            kind="brand", display_name="Steel & Stone Supply Co.",
            slug="steel-stone-supply-co",
            bio=SAMPLE + "Aftercare balms and wash for professionals.",
            city="Denver", state="CO", specialties=["aftercare"],
            services=["wholesale"], claim_status="unclaimed",
            created_by_user_id=owner.id)
        db.add(brand)
        db.flush()
        db.add(TeamAffiliation(studio_profile_id=studio.id,
                               member_profile_id=maya.id, role_label="Resident artist"))

        db.add(ClaimRequest(profile_id=maya.id, user_id=artist.id,
                            claimer_relationship="artist",
                            evidence_text="Sample evidence: I am Maya Reyes; "
                                          "portfolio matches my public work.",
                            status="pending"))

        # --- Story leads -------------------------------------------------------
        ingest_lead(db, headline="Ink brand launches fragrance-free aftercare line",
                    source_url="https://example.com/news/fragrance-free-aftercare",
                    source_name="Sample Industry Wire",
                    suggested_angle="Angle: interview the founder about the formula.")
        ingest_lead(db, headline="Midwest convention announces 2027 dates",
                    source_url="https://example.com/news/midwest-convention-2027",
                    source_name="Sample Industry Wire",
                    suggested_angle="Angle: which Inktrovert artists are attending?")

        # --- Podcasts ------------------------------------------------------------
        _silent_wav(os.path.join(Config.UPLOAD_DIR, "audio", "ep-collectors-1.wav"))
        _silent_wav(os.path.join(Config.UPLOAD_DIR, "audio", "ep-pros-1.wav"))

        s1 = PodcastSeries(title="Ink Stories", slug="ink-stories", audience="collectors",
                           description="Artist stories, interviews, and studio features "
                                       "for collectors.", sort_order=0)
        s2 = PodcastSeries(title="The Professional Chair", slug="the-professional-chair",
                           audience="professionals",
                           description="Industry news and continued learning for artists "
                                       "and piercers: technique, business, craft.",
                           sort_order=1)
        db.add_all([s1, s2])
        db.flush()
        db.add(PodcastEpisode(
            series_id=s1.id, title="How Maya Reyes found fine line",
            slug="how-maya-reyes-found-fine-line", episode_number=1,
            description="Show notes (sample): Maya talks apprenticeship, botanical "
                        "references, and why she draws every day.",
            audio_file="audio/ep-collectors-1.wav", duration_seconds=5,
            related_profile_id=maya.id, is_published=True, published_at=utcnow()))
        db.add(PodcastEpisode(
            series_id=s2.id, title="Sterile technique refresh: what changed this year",
            slug="sterile-technique-refresh", episode_number=1,
            description="Show notes (sample): a continued-learning refresher on "
                        "barrier habits and setup discipline.",
            audio_file="audio/ep-pros-1.wav", duration_seconds=5,
            is_published=True, published_at=utcnow()))

        # --- Newsletter archive ----------------------------------------------------
        db.add(NewsletterEdition(
            subject="Inktrovert #1 — the launch issue (sample)",
            slug="inktrovert-1-launch-sample",
            summary="Sample archived edition.", body="Sample newsletter body.",
            sent_at=utcnow(), is_archived=True))

        # --- Funding stubs (no money moves) ------------------------------------------
        db.add(SubscriptionTier(
            name="Inktrovert Insider", slug="inktrovert-insider", audience="magazine",
            kind="recurring",
            description="Subscriber exclusives for collectors.",
            perks=["Subscriber-only flash drops", "Early-access windows",
                   "Behind-the-chair stories", "Digital issues"],
            price_cents=None, is_active=False))
        db.add(SubscriptionTier(
            name="Collector Circle", slug="collector-circle", audience="magazine",
            kind="recurring",
            description="Everything in Insider, plus presales and special editions.",
            perks=["Everything in Insider", "Event presales", "Special editions"],
            price_cents=None, is_active=False))
        db.add(SubscriptionTier(
            name="Professional (coming later)", slug="professional", audience="studio",
            kind="recurring", description="Studio-side tier — later phase.",
            perks=[], price_cents=None, is_active=False))
        db.add(FundraisingCampaign(
            title="Founding Supporters Drive (sample)", slug="founding-supporters-drive-sample",
            description="Sample campaign for previewing fundraising.",
            goal_cents=500000, status="draft", created_by_user_id=owner.id))

    print("Seed applied.")
    print("  owner@inktrovert.local / InktrovertOwner1!   (platform_owner)")
    print("  collector@inktrovert.local / InktrovertFan1! (collector)")
    print("  artist@inktrovert.local / InktrovertPro1!    (tattoo_artist + collector)")


if __name__ == "__main__":
    main()
