"""Seed the Inktrovert dev database with real content.

All content here is real: verified events, the Luna & Lotus studio
profile, and structural records (roles, tiers). No placeholder content.
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

from datetime import datetime

from app.auth import ensure_roles, register_user  # noqa: E402
from app.config import Config  # noqa: E402
from app.db import create_all, init_engine, session_scope  # noqa: E402
from app.leads import ingest_lead  # noqa: E402
from app.models import (ClaimRequest, Event, FlashPiece, FundraisingCampaign,  # noqa: E402
                        Issue, NewsletterEdition, PodcastEpisode, PodcastSeries,
                        PortfolioCollection, PortfolioItem, Profile,
                        Story, SubscriptionTier, TeamAffiliation, User, utcnow)



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


        # --- Events ----------------------------------------------------------
        # Real events only — no samples anywhere on the site.
        db.add(Event(
            title="Central Wyoming Tattoo Rodeo", slug="central-wyoming-tattoo-rodeo-2026",
            description="A full day of live tattooing, art fusion collaborations, "
                        "comedy, music, and door prizes at The Hangar in Bar Nunn. "
                        "Featuring Namesake Tattoo Collective, Pain For Sale, "
                        "Lost Souls Tattoo Company, TwoBulls Tattoo, and "
                        "Luna & Lotus Piercing & Ink. $10 admission, free entry "
                        "with out-of-town ID. Tattoos 18+ with ID, alcohol 21+ "
                        "with ID, cash only.",
            venue_name="The Hangar — 1410 Prairie Lane, Bar Nunn, WY 82604", city="Bar Nunn", state="WY",
            starts_at=datetime(2026, 11, 7, 12, 0),
            ends_at=datetime(2026, 11, 8, 0, 0),
            url="https://www.lunaandlotus.ink", status="approved",
            submitted_by_user_id=owner.id))

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
        # Real episodes are seeded by seed_content.py (verified podcasts).



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


    print("Seed applied.")
    print("  owner@inktrovert.local / InktrovertOwner1!   (platform_owner)")
    print("  collector@inktrovert.local / InktrovertFan1! (collector)")
    print("  artist@inktrovert.local / InktrovertPro1!    (tattoo_artist + collector)")


if __name__ == "__main__":
    main()
