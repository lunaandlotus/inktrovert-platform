"""Seed REAL, verified curated content for the Inktrovert platform.

Everything here was verified via web research on 2026-10-14: real podcast
shows with real episode titles and real external links, real industry news
with real dates and source attribution, and real 2026 trend reporting.
Nothing is invented. Every item carries visible source attribution.

Curated items are labeled "Inktrovert curation" (stories) or
"Curated by Inktrovert" (podcasts). The original sample seed content from
scripts/seed.py is left untouched.

Run:  cd ~/workspace/inktrovert-platform && .venv/bin/python scripts/seed_content.py
Idempotent: every item is keyed by unique slug; re-runs add only what's missing.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import session_scope  # noqa: E402
from app.models import (Issue, PodcastEpisode, PodcastSeries, Profile, Story,  # noqa: E402
                        utcnow)


def _dt(y: int, m: int, d: int):
    return datetime(y, m, d, tzinfo=timezone.utc)


def _attrib(name: str, url: str) -> str:
    return (f'<p class="meta">Source: <a href="{url}" target="_blank" '
            f'rel="noopener">{name}</a> · Curated by Inktrovert</p>')


AUTHOR = "Inktrovert curation"

# ---------------------------------------------------------------------------
# Stories: (slug, title, category, excerpt, body_paragraphs, sources, pub_date)
# sources = list of (name, url); pub_date may be None when no article date
# could be verified (then the body notes when it was verified).
# ---------------------------------------------------------------------------
STORIES = [
    (
        "curated-hong-kong-tattoo-con-ai-try-on",
        "Hong Kong's Tattoo Con brings AI try-on machines to the show floor",
        "news",
        "Oh My Ink's AI tattoo try-on tech headlines the Hong Kong China "
        "International Tattoo Exhibition, Oct 16–18.",
        [
            "The 2026 Hong Kong China International Tattoo Exhibition runs "
            "October 16–18 at SoHo House Hong Kong, 10 a.m. to 10 p.m. daily "
            "across two floors — and it's co-organized by Oh My Ink, the Hong "
            "Kong art-tech company behind what it calls the world's first AI "
            "tattoo try-on, together with G-S CHINA.",
            "Five to six try-on machines will sit on the show floor. Artists "
            "from Hong Kong, Korea, Japan, Spain, Serbia, France, Indonesia, "
            "and the UK are on the lineup, there's a same-day competition, "
            "and exhibiting artists can upload their flash to the machines "
            "ahead of the convention. Oh My Ink won the SunEvision Startup "
            "Program 2026.",
            "Whether AI try-on is a gimmick or a genuine consult tool, it's "
            "now sharing a floor with working conventions — worth watching.",
        ],
        [("Colorado News Desk",
          "http://news.coloradonewsdesk.com/story/621549/oh-my-ink-the-arttech-company-behind-the-worlds-first-ai-tattoo-tryon-coorganizes-hong-kong-tattoo-con-with-gs-china.html")],
        _dt(2026, 8, 27),
    ),
    (
        "curated-london-show-mystery-tattoo-win",
        "He got a tattoo without seeing the design — and won Best of Friday",
        "news",
        "Bibek Raut let his artist tattoo his thigh completely blind at the "
        "Big London Tattoo Show. Eleven hours later, it took the top prize.",
        [
            "Bibek Raut walked into the Big London Tattoo Show competition "
            "and agreed to be tattooed without seeing a single line of the "
            "design first. 'I'll make a tattoo that will suit you,' his "
            "artist told him — and Raut said all right.",
            "Eleven hours in the chair later, the thigh piece won Best of "
            "Friday. The artist, Abhishek Shakya of Reading Mystic Tattoo "
            "Lounge — Raut's shop since 2018 — also took second place in the "
            "Ornamental category, while Zamyang Yeshi took second in the "
            "Asian-inspired category.",
            "Shakya started tattooing 14 years ago on friends and family in "
            "Kathmandu, where tattooing wasn't seen as a viable career. "
            "Raut's verdict: 'When you die you take tattoos with you. And "
            "I've got the winning tattoo.'",
        ],
        [("Brody Mag",
          "https://brodymag.pp.ua/p/a%3A8208043513560%3Aartist-wins-tattoo-show-award-051606000")],
        _dt(2026, 10, 14),
    ),
    (
        "curated-golden-state-expo-2026-scaled-back",
        "Golden State Tattoo Expo scales back to 'the core' in a tough economy",
        "news",
        "Nikko Hurtado's Pasadena expo slimmed down for 2026 — 300 artists, "
        "17 categories, and an honest conversation about the economy.",
        [
            "The Golden State Tattoo Expo's 2026 edition in Pasadena was "
            "deliberately smaller than usual. Host Nikko Hurtado put it "
            "plainly, pointing to the American economy as the reason the "
            "show slimmed down to what he called 'the core': 300 artists, "
            "down from the roomier editions of years past.",
            "It was still a full convention: CAM Supply Inc., Sullen "
            "Clothing, acts from Freakshow Deluxe, donations to the Pasadena "
            "Humane Society, celebrity appearances, and competition across "
            "17 categories — Best Color Realism, Best Black and Gray, Large "
            "Scale Coverage, Best of Day, Best of Show — with carved-bear "
            "trophies for the winners.",
            "Hurtado didn't tattoo at the show; he worked the floor "
            "representing his rEvolution ink line, with artists collaborating "
            "on large color pieces using his ink. 'It's hard to predict "
            "what shows are going to do well,' he said — an honest read on "
            "where the convention circuit stands.",
        ],
        [("iNKPPL Tattoo Magazine",
          "https://inkppl.com/en/magazine/ink-people/golden-state-tattoo-expo-2026-an-industry-in-transition")],
        _dt(2026, 10, 6),
    ),
    (
        "curated-ink-different-bay-area-apprenticeship",
        "Ink Different brings its tattoo apprenticeship to the Bay Area",
        "news",
        "A structured apprenticeship program lands in Union City with 15-year "
        "veteran Paco Ruelas mentoring.",
        [
            "Ink Different Tattoos has opened a new apprenticeship location "
            "in Union City, California, in partnership with Only 4Ever "
            "Tattoo Studio — a five-star Bay Area shop founded in 2023.",
            "Leading the program is Paco Ruelas, with more than 15 years "
            "behind the machine across Japanese, geometric, dotwork, "
            "neo-traditional, and tribal styles.",
            "The pitch: a clear, structured path into professional tattooing "
            "in one of the country's most diverse markets — an 'AI-proof "
            "creative career,' as the announcement puts it.",
        ],
        [("EINPresswire",
          "https://www.einnews.com/pr_news/947501332/ink-different-tattoos-expands-in-san-francisco-through-partnership-with-union-city-s-only-4ever-tattoo-studio")],
        _dt(2026, 10, 8),
    ),
    (
        "curated-flower-city-tattoo-convention-2026",
        "Flower City Tattoo Convention returns to Rochester, Nov 20–22",
        "news",
        "The 5th annual brings 400+ artists, Ink Master names, and a lifetime "
        "achievement award to the Floreano Convention Center.",
        [
            "The 5th Annual Flower City Tattoo Convention takes over "
            "Rochester, New York, November 20–22 at the Floreano Convention "
            "Center, with over 400 tattoo artists and professional piercers "
            "from the US and abroad.",
            "This year's lineup includes Ink Master artists Laura Marie, "
            "Jimmy Snaz, Kyle Mackenzie, Cleen Rock One, and Jordi Pla — and "
            "a special highlight: the Flower City Lifetime Achievement Award "
            "goes to Joel 'Doc' Yeager for decades of work in the Rochester "
            "tattoo community.",
            "Beyond the tattooing: sideshow performances, human suspension "
            "demos, live MMA and pro wrestling, and vendors all weekend. "
            "Kids 15 and under are free with a paying adult; first "
            "responders, military, and veterans get half off at the door. "
            "Hours are noon–11pm Fri–Sat, noon–9pm Sunday.",
        ],
        [("World Tattoo Events",
          "https://www.worldtattooevents.com/event/flower-city-tattoo-convention-2026")],
        None,
    ),
    (
        "curated-china-tattoo-convention-2026",
        "China Tattoo Convention turns 20 in Hangzhou, Nov 6–8",
        "news",
        "The 20th anniversary edition brings contests, seminars, and a full "
        "equipment expo to the Hangzhou Platinum Hanjue Hotel.",
        [
            "The China Tattoo Convention celebrates its 20th anniversary "
            "November 6–8 at the Hangzhou Platinum Hanjue Hotel, with artists "
            "and professionals from around the globe.",
            "Alongside the tattoo contests, live seminars, art exhibitions, "
            "and music, the event runs a full trade expo: tattoo equipment, "
            "cosmetic tattooing, tattoo removal tech, piercing products, "
            "studio tools, and software. This year's official poster art is "
            "by Cristopher Mendez Alfaro.",
        ],
        [("World Tattoo Events",
          "https://www.worldtattooevents.com/event/china-tattoo-art-festival-2026")],
        None,
    ),
    (
        "curated-malaga-tattoo-convention-2026",
        "Málaga Tattoo Convention takes over Picasso's birthplace, Dec 11–13",
        "news",
        "Three days of live tattooing and industry brands at the FYCMA "
        "exhibition center.",
        [
            "The Málaga Tattoo Convention runs December 11–13 at FYCMA, the "
            "Palacio de Ferias y Congresos de Málaga — one of the city's "
            "leading exhibition venues.",
            "Three days of national and international artists, live "
            "tattooing, studios, and specialized industry brands, in the "
            "birthplace of Pablo Picasso — a fitting backdrop for tattooing "
            "presented as contemporary art.",
        ],
        [("World Tattoo Events",
          "https://www.worldtattooevents.com/event/malaga-tattoo-convention-2026")],
        None,
    ),
    (
        "curated-icons-prodigies-venice-2026",
        "Icons & Prodigies brings 50 icons and 250 prodigies to Venice, "
        "Nov 14–15",
        "news",
        "The pioneers and the next generation share one floor in Venezia.",
        [
            "The Icons & Prodigies Tattoo Convention lands in Venice, Italy, "
            "November 14–15, built around a deliberate pairing: 50 "
            "international 'icons' — pioneers across 10 tattoo styles — "
            "alongside 250 'prodigies' carrying the craft forward.",
            "It's a mentorship-shaped lineup: the artists who marked an era, "
            "and the new generation working in their footsteps or breaking "
            "new ground.",
        ],
        [("World Tattoo Events",
          "https://www.worldtattooevents.com/event/icons-prodigies-tattoo-convention-venice-2026")],
        None,
    ),
    (
        "curated-rise-of-ink-vietnam-2026",
        "Rise of Ink launches in Ho Chi Minh City, Nov 18–19",
        "news",
        "A first-edition convention with 24 competition categories, including "
        "several never seen before.",
        [
            "The Rise of Ink Tattoo Convention launches November 18–19 at "
            "the Luxury Palace in Ho Chi Minh City, Vietnam, with hundreds "
            "of local and international artists.",
            "The hook: 24 competition categories, several of them brand new "
            "to the circuit — Best of Grey, Best of Day Micro, Catholic "
            "tattoo, stone tattoo — with three Best of Show prizes on the "
            "line.",
        ],
        [("World Tattoo Events",
          "https://www.worldtattooevents.com/event/rise-of-ink-tattoo-convention-2026")],
        None,
    ),
    (
        "curated-rita-wilson-back-tattoo",
        "Rita Wilson's matching back tattoo, at 69",
        "spotlight",
        "A giant cross, a son with the same ink, and a new single about "
        "getting stranger with age.",
        [
            "Rita Wilson debuted a giant cross tattoo across her back on "
            "Instagram — matching ink her son Chet Hanks wears in a similar "
            "shape, each filled with different patterns.",
            "The post doubled as promotion for her single 'Stranger With "
            "Age.' Her caption: 'STRANGER WITH AGE? Who? Me? I'm lovin' "
            "it!' — and in an interview with Melissa Rivers she tied it "
            "together: doing things you never did before because you don't "
            "care anymore, liberated from what age says you should do.",
            "The comments filled up fast — Reese Witherspoon, Brandi "
            "Carlile, and plenty of regular folks cheering her on.",
        ],
        [("Entertainment Weekly",
          "https://ew.com/tom-hanks-wife-rita-wilson-debuts-giant-back-tattoo-cross-similar-to-son-chets-at-69-12136599")],
        _dt(2026, 9, 25),
    ),
    (
        "curated-nancy-mace-rib-tattoo",
        "A congresswoman's 15th tattoo: her kids' names in script",
        "spotlight",
        "Nancy Mace showed off rib ink of her children's names and birthdates "
        "— plus an American-traditional rose.",
        [
            "Nancy Mace displayed new rib tattoos on her 'Get MACED' "
            "podcast: her son Miles Emery's and daughter Ellison Ann's "
            "names, each followed by a full birthdate, with an "
            "American-traditional rose in full color below — matching the "
            "bold saturated style of the roses and hawk already on her arms.",
            "By Maceopedia's count it's her 15th distinct tattoo. She told "
            "Politico early in 2026 she had nine, 'in rapid succession' — "
            "then kept walking the number up through the summer.",
            "Whatever your politics, the script-and-rose combo is pure "
            "classic Americana — and proof that tattoo collectors sit "
            "everywhere now, including Capitol Hill.",
        ],
        [("Maceopedia",
          "https://maceopedia.org/dispatches/2026-09-29-mace-children-names-birthdates-rose-tattoo")],
        _dt(2026, 9, 29),
    ),
    (
        "curated-tattoo-style-trends-2026",
        "What's actually trending in tattoo styles right now",
        "spotlight",
        "Fine line still rules, sticker patchwork is exploding, and "
        "cybersigilism went from meme to mainstay.",
        [
            "Fine-line and minimalist designs remain the most requested "
            "tattoo style in 2026, with sticker-style patchwork the "
            "fastest-growing trend — especially with Gen Z. Birth flower "
            "bouquets, celestial and astrology pieces, Y2K nostalgia, and "
            "American Traditional are all surging too.",
            "The experimental edge: cybersigilism (Y2K cyber-goth, spiky "
            "circuit-like linework in fine-line blackwork), micro-realism "
            "(tiny photorealistic portraits and flora), trash polka "
            "(chaotic black-and-red collage), and 3D liquid chrome "
            "(reflective mercury depth with white highlights).",
            "And the quiet giant: neo-traditional is still the most-tagged "
            "style out there at 3.7M+ hashtags, while nostalgic romantic "
            "motifs — pet portraits in heart lockets, Lisa Frank dolphins, "
            "refined tramp stamps, cursive script — keep winning with Gen Z "
            "and millennials.",
        ],
        [("Temporalis",
          "https://www.temporalis.tattoo/blogs/magazine/top-10-temporary-tattoo-trends-2026"),
         ("Burned Hearts Tattoo",
          "http://burnedhearts.com/blog/tattoo-trends-in-2026")],
        _dt(2026, 8, 6),
    ),
    (
        "curated-piercing-trends-2026",
        "Piercing in 2026: quiet luxury, precise placements",
        "spotlight",
        "Minimalist curation is the word — constellation ears, high nostrils, "
        "and implant-grade everything.",
        [
            "Body piercing in 2026 has gone refined. Martin Jewelry & "
            "Piercing Krakow's trend report calls it 'minimalist curation': "
            "constellation piercings mapped to the ear's anatomy, high-lobe "
            "stacks, and cohesive jewelry sets in implant-grade titanium "
            "and solid gold — fewer random placements, more permanent fine "
            "jewelry planned to heal well.",
            "What's getting asked for: the high nostril revival (tiny gold "
            "or titanium studs, often symmetrical pairs), the flat + "
            "forward helix power pair, refined daith and rook work with "
            "slim clickers instead of chunky rings, and double tragus "
            "stacks — a look Zoe Kravitz helped put on the map.",
            "The 90s and Y2K are back too: belly rings are returning, and "
            "faux snug and rook pieces let people get the complex look "
            "without the long heal. The throughline for the year: precision "
            "over shock value.",
        ],
        [("Obsidian Needle via Santa Maria Times",
          "https://santamariatimes.marketminute.com/article/abnewswire-2026-3-26-obsidian-needles-2026-piercing-trends-defining-styles-placements-jewelry-evolution"),
         ("Camile and Stone",
          "https://camileandstone.com.au/collections/piercing-jewellery?page=29")],
        _dt(2026, 3, 26),
    ),
]

# ---------------------------------------------------------------------------
# Podcasts: (series_slug, title, audience, description, show_url, episodes)
# episodes: (title, released, blurb, listen_url)
# ---------------------------------------------------------------------------
PODCASTS = [
    (
        "curated-honest-tattooer",
        "Honest Tattooer Podcast",
        "collectors",
        "Real talk with tattoo artists and tattoo lovers from No Idols NYC. "
        "Hosts Jon Mesa, Matt Truiano, and Gabe keep it honest — shop life, "
        "how ink ages, trends, and the business. External show, curated by "
        "Inktrovert.",
        "https://www.buzzsprout.com/2119835/episodes",
        [
            ("Skin Deep with Josh Adams", _dt(2026, 10, 12),
             "Jon Mesa and Matt Truiano welcome Josh Adams, creator and host "
             "of the tattoo docuseries Skin Deep, on documenting tattoo "
             "artists and shop culture.",
             "https://www.buzzsprout.com/2119835/episodes"),
            ("How Small Tattoos Age with Gordo and Daniela Segal", _dt(2026, 10, 5),
             "How different styles and pigments — tiny realism, traditional "
             "work, fine lines — age over time, plus tipping culture and "
             "generational trends.",
             "https://www.buzzsprout.com/2119835/episodes"),
            ("When Tattooers Should Say No", _dt(2026, 9, 28),
             "A one-on-one on turning down projects outside your strengths, "
             "designs that won't age well, and holding boundaries with "
             "clients.",
             "https://www.buzzsprout.com/2119835/episodes"),
        ],
    ),
    (
        "curated-how-much-for-a-sleeve",
        "How Much For A Sleeve?",
        "collectors",
        "A tattoo podcast hosted by tattooist Lucie Richardson and Mick "
        "Tickner — interviews from the tattoo world, life in tattooing, and "
        "a proper laugh. External show, curated by Inktrovert.",
        "https://uk-podcasts.co.uk/podcast/how-much-for-a-sleeve",
        [
            ("Episode 102 - Dolly", _dt(2026, 10, 4),
             "Lucie and Mick interview Dolly from the tattoo world.",
             "https://uk-podcasts.co.uk/podcast/how-much-for-a-sleeve"),
            ("Episode 101 - Alex Whiley", _dt(2026, 9, 2),
             "Lucie and Mick interview Alex Whiley from the tattoo world.",
             "https://uk-podcasts.co.uk/podcast/how-much-for-a-sleeve"),
        ],
    ),
    (
        "curated-fireside-tattoo",
        "Fireside Tattoo Podcast",
        "professionals",
        "Jake Meeks answers viewer questions, interviews artists, and talks "
        "better tattooing and more informed collectors — running since 2013. "
        "External show, curated by Inktrovert.",
        "https://www.podbean.com/podcast-detail/gaybx-54d9f/Fireside-Tattoo-Podcast",
        [
            ("The Art of Making Art Your Way | Peter Mohrbacher", _dt(2026, 6, 17),
             "Digital painter, character designer, and Angelarium creator "
             "Peter Mohrbacher on making art your way.",
             "https://www.podbean.com/podcast-detail/gaybx-54d9f/Fireside-Tattoo-Podcast"),
            ("Why Good Tattoos Aren't Enough Anymore | Liz Cook", _dt(2026, 5, 6),
             "Tattoo artist, educator, and color formulator Liz Cook on "
             "education, burnout, AI tools, and branding.",
             "https://www.podbean.com/podcast-detail/gaybx-54d9f/Fireside-Tattoo-Podcast"),
            ("What Happens When a World-Class Painter Becomes a Tattoo "
             "Apprentice? | David Cheifetz", _dt(2026, 4, 29),
             "Painter David Cheifetz on crossing over into a tattoo "
             "apprenticeship.",
             "https://www.podbean.com/podcast-detail/gaybx-54d9f/Fireside-Tattoo-Podcast"),
        ],
    ),
    (
        "curated-business-of-tattooing",
        "The Business of Tattooing",
        "professionals",
        "Rob Smead (Electrum Supply) goes beyond the ink into the industry "
        "and the hustle — shop ownership, regulation, and what it takes to "
        "succeed. External show, curated by Inktrovert.",
        "https://podcasts.apple.com/us/podcast/the-business-of-tattooing/id1805984838",
        [
            ("Episode 30 - Spotlight Series feat. Ryan Adams", None,
             "Shop ownership, Michigan's new numbing cream regulations, and "
             "adapting to the industry slowdown — with Ryan Adams of Hell or "
             "High Water Tattoo.",
             "https://youtu.be/ZyMAquvQDgY"),
            ("Episode 28 - TIMA Talks", None,
             "The launch of TIMA and Inktegrity: industry-led safety "
             "standards and product transparency.",
             "https://youtu.be/hVao61fcuOk"),
            ("Episode 26 - Pony Lawson", None,
             "Micro-realism and metallic techniques, AI in design, and the "
             "future of the craft.",
             "https://podcasts.apple.com/us/podcast/the-business-of-tattooing/id1805984838"),
        ],
    ),
    (
        "curated-qa-in-the-kitchen",
        "Q&A in the Kitchen",
        "professionals",
        "DaVo of Axiom Body Piercing (piercing since 1994) with Brent Starr, "
        "Jimmy St John, and Jack Lowe of Skin Kitchen Tattoo — professional "
        "tattooists and piercers talking the body arts. External show, "
        "curated by Inktrovert.",
        "https://bptchannel.com/",
        [
            ("Tattoo & Piercing Trends, Should You Follow Them? — S05 EP02", None,
             "The panel debates tattoo and piercing trends — follow them or "
             "not?",
             "https://www.youtube.com/watch?v=CFqh4tZkNdQ"),
            ("Prolonging the Life of Your Tattoos & Piercings — S04 EP27", None,
             "How to keep tattoos and piercings looking their best over time.",
             "https://www.youtube.com/watch?v=sM9sSsv1SUs"),
            ("Patenting Tattoos & Piercings — S04 EP17", None,
             "Can you patent tattoos and piercings? The panel digs in.",
             "https://www.youtube.com/watch?v=p_kksuqYAWo"),
        ],
    ),
]


def main() -> None:
    from app import create_app  # noqa: E402
    app = create_app()
    with app.app_context():
        _seed()


def _seed() -> None:
    added = {"issues": 0, "stories": 0, "series": 0, "episodes": 0}
    with session_scope() as db:
        # --- Issue #2: the real-news issue --------------------------------------
        issue = db.query(Issue).filter_by(slug="issue-2-the-current-fall-2026").one_or_none()
        if issue is None:
            issue = Issue(
                number=2, title="The Current — Fall 2026",
                slug="issue-2-the-current-fall-2026",
                blurb="Real industry news, convention season, and what's "
                      "trending — October 2026.",
                cover_image="img/issue-2-cover.jpg", is_published=True,
                published_at=utcnow())
            db.add(issue)
            db.flush()
            added["issues"] += 1
        elif issue.cover_image in ("img/ph-1.svg", "", None):
            issue.cover_image = "img/issue-2-cover.jpg"
        # Migrate old #1 numbering to #2 (launch issue is now #1)
        if issue.number == 1 and issue.slug == "issue-1-the-current-fall-2026":
            issue.number = 2
            issue.slug = "issue-2-the-current-fall-2026"

        # --- Stories -------------------------------------------------------
        def _story_image(slug, title, category):
            t = (slug + " " + title + " " + category).lower()
            if "pierc" in t:
                return "img/story-piercing.jpg"
            if "flash" in t or "convention" in t or "con" in t or "expo" in t:
                return "img/story-flash.jpg"
            return "img/homepage-hero.jpg"

        for i, (slug, title, category, excerpt, paras, sources, pub) in enumerate(STORIES):
            existing = db.query(Story).filter_by(slug=slug).one_or_none()
            if existing:
                if existing.cover_image in ("img/ph-2.svg", "", None):
                    existing.cover_image = _story_image(slug, title, category)
                continue
            body = "".join(f"<p>{p}</p>" for p in paras)
            body += "".join(_attrib(n, u) for n, u in sources)
            db.add(Story(
                issue_id=issue.id, title=title, slug=slug, category=category,
                excerpt=excerpt, body=body,
                cover_image=_story_image(slug, title, category),
                author_name=AUTHOR, sort_order=i, is_published=True,
                published_at=pub))
            added["stories"] += 1

        # --- Podcasts ------------------------------------------------------
        for slug, title, audience, desc, show_url, episodes in PODCASTS:
            series = db.query(PodcastSeries).filter_by(slug=slug).one_or_none()
            if series is None:
                series = PodcastSeries(
                    title=title, slug=slug, audience=audience,
                    description=desc + f" Find it here: {show_url}",
                    is_active=True, sort_order=10)
                db.add(series)
                db.flush()
                added["series"] += 1
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

        # --- State tags: backfill US-state codes on seeded news stories ----
        # (idempotent: only fills blanks; international + trend stories stay
        # untagged and appear in the issue overview)
        STATE_TAGS = {
            "curated-golden-state-expo-2026-scaled-back": "CA",   # Pasadena
            "curated-ink-different-bay-area-apprenticeship": "CA",  # Union City
            "curated-flower-city-tattoo-convention-2026": "NY",   # Rochester
        }
        for slug, code in STATE_TAGS.items():
            story = db.query(Story).filter_by(slug=slug).one_or_none()
            if story is not None and not story.state:
                story.state = code

        # --- Featured studio for Wyoming: Luna & Lotus (Casper) -------------
        # Defensive lookup — the studio seed may not have run yet.
        luna = (
            db.query(Profile)
            .filter(Profile.display_name.ilike("%luna%lotus%"))
            .first()
        )
        if luna is not None and not luna.featured_state:
            luna.featured_state = "WY"

    print(f"Content seed done: {added['issues']} issues, {added['stories']} stories, "
          f"{added['series']} podcast series, {added['episodes']} episodes added.")


if __name__ == "__main__":
    main()
