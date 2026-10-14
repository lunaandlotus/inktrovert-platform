"""Seed REAL, verified piercing coverage for the Inktrovert platform.

Piercing gets equal footing with tattoo: real piercing-industry news and
real, currently-active piercing podcasts. Everything here was verified via
web research on 2026-10-14: real shows with real episode titles and real
external links, real industry news with real dates and source attribution.
Nothing is invented. Every item carries visible source attribution.

Excluded as unverifiable (deliberately NOT seeded):
  * A standalone "Piercing Bible podcast" by Elayne Angel — no such show
    exists; she appeared as a guest on the Piercing Wizard Podcast instead.
  * "The PWS Podcast" (Scott Wilkinson) — only one episode found, no sign
    of an ongoing show.
  * "PAC TV" (NeilMed) — claimed weekly episodes but no recent ones could
    be verified.
  * UKAPP 2026 as a news story — only mentioned inside a podcast episode
    title; no verifiable event details found.

Run:  cd ~/workspace/inktrovert-platform && .venv/bin/python scripts/seed_piercing.py
Idempotent: every item is keyed by unique slug; re-runs add only what's missing.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import session_scope  # noqa: E402
from app.models import Issue, PodcastEpisode, PodcastSeries, Story, utcnow  # noqa: E402


def _dt(y: int, m: int, d: int):
    return datetime(y, m, d, tzinfo=timezone.utc)


def _attrib(name: str, url: str) -> str:
    return (f'<p class="meta">Source: <a href="{url}" target="_blank" '
            f'rel="noopener">{name}</a> · Curated by Inktrovert</p>')


AUTHOR = "Inktrovert curation"

# ---------------------------------------------------------------------------
# Piercing news: (slug, title, excerpt, body_paragraphs, sources, pub_date,
#                state)
# ---------------------------------------------------------------------------
PIERCING_STORIES = [
    (
        "curated-app-conference-2026-las-vegas",
        "The APP Conference took over Las Vegas, June 7–12",
        "Hundreds of piercers, 75+ hours of classes, and the industry's "
        "biggest week at Planet Hollywood.",
        [
            "The Association of Professional Piercers held its annual "
            "Conference & Exposition June 7–12 at Planet Hollywood in Las "
            "Vegas — a full week built around one thing: piercing, done "
            "right.",
            "The education program is the heart of it: more than 75 hours "
            "of courses from some of the most experienced piercers in the "
            "industry, from fundamentals for apprentices to advanced "
            "technique, studio business, and health and safety. Roundtables "
            "and group meetings run alongside for the networking the "
            "industry runs on.",
            "The expo floor is where the jewelry lives — manufacturers and "
            "vendors showing new designs, tools, and supplies. Open to "
            "professional and apprentice piercers, studio owners, jewelry "
            "specialists, front-counter staff, and health inspectors; no "
            "APP membership required. Next up: June 27–July 2, 2027.",
        ],
        [("Association of Professional Piercers",
          "https://safepiercing.org/appconference/")],
        None,
        "NV",
    ),
    (
        "curated-h2ocean-25-years-app-conference",
        "H2Ocean marks 25 years of piercing aftercare — and 22 with the APP",
        "The original piercing aftercare spray celebrates a quarter century, "
        "two decades of it beside the APP.",
        [
            "H2Ocean celebrated its 25th anniversary in 2026 — a quarter "
            "century as the world's first piercing aftercare spray, the "
            "product that created the category.",
            "The milestone came with a second number: 22 consecutive years "
            "supporting the Association of Professional Piercers Conference "
            "& Exposition in Las Vegas, including 20 years as an official "
            "APP corporate member sponsor. 'Reaching 25 years as the "
            "world's first piercing aftercare spray is a remarkable "
            "milestone,' said inventor and CEO Eddie Kolos.",
            "Two decades of showing up is what industry infrastructure "
            "looks like — the aftercare aisle of every serious studio owes "
            "something to this spray.",
        ],
        [("EINPresswire",
          "https://lifestyle.thenyctimes.com/story/763808/h2ocean-celebrates-25-years-as-the-worlds-first-piercing-aftercare-marks-22nd-year-supporting-the-app-conference/")],
        _dt(2026, 7, 13),
        "FL",
    ),
    (
        "curated-new-flower-studio-app-2026-emerald-coast",
        "Long Beach's New Flower Studio brings the APP home — and a fall "
        "jewelry palette",
        "Back from the 2026 APP Conference with an 'Emerald Coast' color "
        "story for fall.",
        [
            "New Flower Studio in Long Beach sent its piercers to the 2026 "
            "APP Conference in Las Vegas in June — no surprise from a shop "
            "whose corporate culture, in its own words, is safety-driven, "
            "with APP membership to match.",
            "Back home, the studio's piercers did what good curators do: "
            "they built a Fall 2026 body jewelry color palette, 'Emerald "
            "Coast,' starting with turquoise — a stone they note for its "
            "calming associations — now displayed on the studio's shelves. "
            "Earlier in the year they debuted 'Coral Solstice' for summer.",
            "Studios that treat jewelry like fashion houses treat "
            "collections are winning the curation era — and this is what it "
            "looks like in practice.",
        ],
        [("New Flower Studio",
          "https://newflowerstudio.com/nfw/tag/body-art/")],
        None,
        "CA",
    ),
    (
        "curated-sanamama-miami-piercing-celebration",
        "Miami's SANAMAMA throws a piercing party with 100+ new earring styles",
        "A spiritual fine-jewelry house launches in-house piercing in Bay "
        "Harbour Islands.",
        [
            "SANAMAMA launched its new in-house piercing offering on "
            "September 27 with a Piercing Celebration in Bay Harbour "
            "Islands, Florida — alongside more than 100 new earring styles "
            "designed, in the house's words, to elevate your consciousness.",
            "It's a sign of where piercing is headed: fine-jewelry and "
            "fashion houses bringing piercing in-house, treating the "
            "service as part of a jewelry wardrobe rather than a separate "
            "errand.",
            "When the jewelry brands start hiring piercers, the line between "
            "'piercing studio' and 'jewelry house' gets very interesting.",
        ],
        [("World Red Eye",
          "https://worldredeye.com/2026/09/miamis-spiritual-fine-jewelry-store-sanamamas-first-piercing-celebration/")],
        _dt(2026, 9, 27),
        "FL",
    ),
    (
        "curated-camp-app-2026-georgia",
        "Camp APP: the members' retreat heads to Georgia this October",
        "The APP's member retreat follows the June conference — education, "
        "without the expo floor.",
        [
            "After the big June conference in Las Vegas, the Association of "
            "Professional Piercers keeps the education going: Camp APP, "
            "the members' retreat, lands in Georgia this October.",
            "Where the conference is a full exposition with hundreds of "
            "attendees, the retreat format is smaller and member-focused — "
            "a second annual touchpoint for piercers investing in their "
            "continuing education.",
            "Three APP educational events a year, plus scholarships for the "
            "main conference — the professionalization of piercing keeps "
            "compounding.",
        ],
        [("New Flower Studio",
          "https://newflowerstudio.com/nfw/request-a-speaker/")],
        None,
        "GA",
    ),
]

# ---------------------------------------------------------------------------
# Piercing podcasts: (series_slug, title, audience, topic, description,
#                    show_url, episodes)
# episodes: (title, released, blurb, listen_url)
# ---------------------------------------------------------------------------
PIERCING_PODCASTS = [
    (
        "curated-piercing-wizard",
        "Piercing Wizard Podcast",
        "professionals",
        "piercing",
        "Ryan Ouellette and Lola Slider of Precision Body Arts (Nashua, NH) "
        "talk piercing technique, sterilization, aftercare science, jewelry, "
        "and shop life — pro-level conversation with personality. External "
        "show, curated by Inktrovert.",
        "https://piercing-wizard-podcast.pinecast.co/",
        [
            ("281 - Beaches, Castles, and Classrooms - Benelux + UKAPP 2026", None,
             "Ryan and Lola on the Benelux and UKAPP 2026 events — "
             "piercing education across Europe.",
             "https://piercing-wizard-podcast.pinecast.co/"),
            ("280 - Sneaky Recordings & Second Hand Jewelry", None,
             "Shop ethics, secondhand jewelry, and the conversations "
             "piercers have when clients aren't listening.",
             "https://piercing-wizard-podcast.pinecast.co/"),
            ("279 - Jordan Jones and me, Lola recaps Vegas", None,
             "Lola recaps Vegas with Jordan Jones — the APP Conference "
             "through a piercer's eyes.",
             "https://piercing-wizard-podcast.pinecast.co/"),
        ],
    ),
    (
        "curated-talking-about-piercing-live",
        "Talking About Piercing Live",
        "collectors",
        "piercing",
        "DaVo of Axiom Body Piercing (Des Moines, IA — piercing since 1994) "
        "and his apprentice Scott answer viewer piercing questions live "
        "every Sunday, with a weekly round-up and jewelry picks. External "
        "show, curated by Inktrovert.",
        "https://axiompiercing.com",
        [
            ("Talking About Piercing Live EP44 - Wore Out the Soles of My "
             "Party Vans", _dt(2026, 10, 4),
             "DaVo and Scott answer piercing questions, plus the weekly "
             "round-up, jewelry pick of the week, and trending piercing "
             "topics.",
             "https://www.youtube.com/watch?v=qhkTBaTGGlQ"),
            ("Talking About Piercing Live EP42 - DaVo Solo", _dt(2026, 9, 20),
             "DaVo flies solo answering piercing questions — weekly "
             "round-up, jewelry pick, and songs of the week.",
             "https://www.youtube.com/watch?v=PayaDgLNcQw"),
        ],
    ),
    (
        "curated-discussions-in-body-art",
        "Discussions in Body Art",
        "professionals",
        "piercing",
        "Body art educator John Johnson (APP, safepiercing.org) delivers "
        "short-form sessions on body art safety — codes, infection "
        "prevention, and the piercer-regulator relationship. External show, "
        "curated by Inktrovert.",
        "https://www.buzzsprout.com/2302835",
        [
            ("Biohazard Symbol", _dt(2026, 8, 26),
             "What the biohazard symbol means for your communications "
             "program — short, practical safety education.",
             "https://www.buzzsprout.com/2302835"),
            ("Acronym City part 6", _dt(2026, 6, 9),
             "TAG, IFU, AEC, SPD, PCD — decoding the acronyms of body art "
             "safety, part six.",
             "https://www.buzzsprout.com/2302835"),
        ],
    ),
]

# Topic backfill for the already-seeded curated series.
TOPIC_TAGS = {
    "tattoo": [
        "curated-honest-tattooer",
        "curated-how-much-for-a-sleeve",
        "curated-fireside-tattoo",
        "curated-business-of-tattooing",
    ],
    "both": [
        # DaVo/Axiom (piercing) + Skin Kitchen Tattoo (tattoo) panel.
        "curated-qa-in-the-kitchen",
    ],
}


def main() -> None:
    from app import create_app  # noqa: E402
    app = create_app()
    with app.app_context():
        _seed()


def _seed() -> None:
    added = {"stories": 0, "series": 0, "episodes": 0}
    with session_scope() as db:
        # --- Piercing news goes into the current real-news issue ----------
        issue = db.query(Issue).filter_by(
            slug="issue-2-the-current-fall-2026").one_or_none()
        base_order = 0
        if issue is not None:
            base_order = db.query(Story).filter_by(
                issue_id=issue.id).count()

        for i, (slug, title, excerpt, paras, sources, pub, state) in enumerate(
                PIERCING_STORIES):
            if db.query(Story).filter_by(slug=slug).one_or_none():
                continue
            body = "".join(f"<p>{p}</p>" for p in paras)
            body += "".join(_attrib(n, u) for n, u in sources)
            db.add(Story(
                issue_id=issue.id if issue else None,
                title=title, slug=slug, category="news",
                excerpt=excerpt, body=body, cover_image="img/ph-2.svg",
                author_name=AUTHOR, sort_order=base_order + i,
                is_published=True, published_at=pub, state=state))
            added["stories"] += 1

        # --- Piercing podcast series --------------------------------------
        for slug, title, audience, topic, desc, show_url, episodes in PIERCING_PODCASTS:
            series = db.query(PodcastSeries).filter_by(slug=slug).one_or_none()
            if series is None:
                series = PodcastSeries(
                    title=title, slug=slug, audience=audience, topic=topic,
                    description=desc + f" Find it here: {show_url}",
                    is_active=True, sort_order=10)
                db.add(series)
                db.flush()
                added["series"] += 1
            elif not series.topic:
                series.topic = topic
            n = len(episodes)
            for j, (ep_title, released, blurb, listen_url) in enumerate(episodes):
                ep_slug = f"{slug}-ep-{n - j}"
                if db.query(PodcastEpisode).filter_by(slug=ep_slug).one_or_none():
                    continue
                notes = f"External episode from {title}."
                if released:
                    notes += f" Released {released.strftime('%B %d, %Y')}."
                notes += f"\n\n{blurb}\n\nListen: {listen_url}"
                db.add(PodcastEpisode(
                    series_id=series.id, title=ep_title, slug=ep_slug,
                    episode_number=n - j,
                    description=notes, audio_file="",
                    related_story_id=None, related_profile_id=None,
                    is_published=True, published_at=released))
                added["episodes"] += 1

        # --- Topic backfill for previously seeded curated series ----------
        for topic, slugs in TOPIC_TAGS.items():
            for s in slugs:
                series = db.query(PodcastSeries).filter_by(slug=s).one_or_none()
                if series is not None and not series.topic:
                    series.topic = topic

    print(f"Piercing seed done: {added['stories']} stories, "
          f"{added['series']} podcast series, {added['episodes']} episodes added.")


if __name__ == "__main__":
    main()
