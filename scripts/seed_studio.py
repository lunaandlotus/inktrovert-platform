"""Seed the FIRST real studio on Inktrovert: Luna & Lotus Piercing & Ink.

Creates, idempotently (checked by slug):
  - Studio profile "Luna & Lotus Piercing & Ink" (claimed + verified + featured)
  - Artist profile "Angie Valentin" (claimed + verified)
  - TeamAffiliation linking Angie to the studio roster (accepted)

Run:  cd ~/workspace/inktrovert-platform && .venv/bin/python scripts/seed_studio.py
Also wired into the seed-on-boot chain in app/__init__.py (after seed_content).
Idempotent: skips anything whose slug already exists; never duplicates.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import session_scope  # noqa: E402
from app.models import Profile, TeamAffiliation, User  # noqa: E402

STUDIO_SLUG = "luna-lotus-piercing-ink"
ARTIST_SLUG = "angie-valentin"
OWNER_EMAIL = "owner@inktrovert.local"

STUDIO_BIO = """Luna & Lotus is Angie Valentin's tattoo and piercing studio in Casper, Wyoming. Custom tattoos, professional piercings, honest advice — walk-ins welcome, appointments come first.

You'll find us at 1925 Oxford Lane, inside Wind Blown Beauty Salon & Spa.

Hours: Tuesday 3–6 PM, Wednesday 12:30–3:30 PM, Thursday 3–6 PM. Closed Sunday, Monday, Friday, and Saturday.

Tattoos are custom work at $175 an hour with a $50 deposit. You need to be 15 or older — never under 15.

Piercing: ear lobes from age 6, most piercings from 12, navel from 13, nipples 18 and up. Minors need a parent or guardian present with ID and notarized consent.

See our work and book at lunaandlotus.ink."""

STUDIO_SERVICES = [
    "Custom tattoos — $175/hr, $50 deposit",
    "Ear lobe piercing — ages 6+",
    "Piercing — ages 12+ (helix, conch, tragus, daith, rook, nostril, eyebrow & more)",
    "Navel piercing — ages 13+",
    "Nipple piercing — ages 18+",
    "Tattoos — ages 15+ with parent/guardian consent",
]

STUDIO_POLICIES = (
    "Minors: a parent or legal guardian must be present for the entire procedure, "
    "with government ID for both minor and guardian, plus a notarized consent form. "
    "Tattoos never under age 15. Deposits are non-refundable."
)

ARTIST_BIO = """Angie Valentin is the owner of Luna & Lotus Piercing & Ink in Casper, Wyoming — a professional tattoo artist and body piercer. Her work is custom, her standards are high, and her chair is a welcoming place. Custom tattoos and piercings done right, with aftercare you'll actually understand."""


def _seed() -> None:
    added = {"profiles": 0, "affiliations": 0}
    with session_scope() as db:
        owner = db.query(User).filter_by(email=OWNER_EMAIL).one_or_none()

        studio = db.query(Profile).filter_by(slug=STUDIO_SLUG).one_or_none()
        if studio is None:
            studio = Profile(
                kind="studio",
                display_name="Luna & Lotus Piercing & Ink",
                slug=STUDIO_SLUG,
                bio=STUDIO_BIO,
                city="Casper",
                state="WY",
                country="USA",
                latitude=42.83003,
                longitude=-106.35121,
                specialties=["Custom tattoos", "Body piercing"],
                services=STUDIO_SERVICES,
                phone="307-215-1727",
                email="angie@lunaandlotus.ink",
                website="https://www.lunaandlotus.ink",
                booking_mode="external",
                booking_url="https://www.lunaandlotus.ink",
                policies=STUDIO_POLICIES,
                claim_status="claimed",
                verified=True,
                claimed_by_user_id=owner.id if owner else None,
                created_by_user_id=owner.id if owner else None,
                is_listed=True,
                is_featured=True,
            )
            db.add(studio)
            db.flush()
            added["profiles"] += 1

        artist = db.query(Profile).filter_by(slug=ARTIST_SLUG).one_or_none()
        if artist is None:
            artist = Profile(
                kind="tattoo_artist",
                display_name="Angie Valentin",
                slug=ARTIST_SLUG,
                bio=ARTIST_BIO,
                city="Casper",
                state="WY",
                country="USA",
                specialties=["Custom tattoos", "Body piercing"],
                services=[
                    "Custom tattoos — $175/hr, $50 deposit",
                    "Body piercing — all ages per studio policy",
                ],
                phone="307-215-1727",
                email="angie@lunaandlotus.ink",
                website="https://www.lunaandlotus.ink",
                booking_mode="external",
                booking_url="https://www.lunaandlotus.ink",
                claim_status="claimed",
                verified=True,
                claimed_by_user_id=owner.id if owner else None,
                created_by_user_id=owner.id if owner else None,
                is_listed=True,
                is_featured=False,
            )
            db.add(artist)
            db.flush()
            added["profiles"] += 1

        affiliation = (
            db.query(TeamAffiliation)
            .filter_by(studio_profile_id=studio.id, member_profile_id=artist.id)
            .one_or_none()
        )
        if affiliation is None:
            db.add(TeamAffiliation(
                studio_profile_id=studio.id,
                member_profile_id=artist.id,
                role_label="Owner — Tattoo Artist & Piercer",
                sort_order=0,
            ))
            added["affiliations"] += 1

    print(f"Studio seed done: {added['profiles']} profiles, "
          f"{added['affiliations']} affiliations added.")


def main() -> None:
    from app import create_app  # noqa: E402
    app = create_app()
    with app.app_context():
        _seed()


if __name__ == "__main__":
    main()
