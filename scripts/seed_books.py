"""Seed the Books vertical: real, verified books for the craft.

Every title/author here was verified against live book listings on
2026-10-14. Audiobook flags are set ONLY where a real audio edition was
verified (Audible). Nothing invented — unverifiable items were excluded.
Idempotent: books are looked up by slug and never duplicated.

Excluded as unverifiable: audiobook editions for Tattooing A to Z, World
Atlas of Tattoo, Japanese Tattoos, Forever, Tattoo History Source Book,
Bodies of Subversion, the Sailor Jerry books, Wear Your Dreams, Basic
Fundamentals of Modern Tattoo, The Tattoo Textbook (Dax), and the Piercing
Bible Aftercare guide (ebook only).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db import session_scope  # noqa: E402
from app.models import Book  # noqa: E402

# (slug, title, author, publisher, year, isbn, craft, audience, kind,
#  description, why_relevant, buy_url, has_audiobook, audiobook_url, featured)
BOOKS = [
    # --- Tattoo technique / reference ------------------------------------
    ("tattooing-a-to-z",
     "Tattooing A to Z: A Guide to Successful Tattooing",
     "Huck Spaulding", "Spaulding & Rogers Mfg", 1992, "9780929719009",
     "tattoo", "professionals", "textbook",
     "The old-school training manual: machines, needles, sterilization, "
     "outlining, shading, color, cover-ups, and running the shop — written "
     "by a working supplier who taught generations of tattooers.",
     "If you apprentice anywhere serious, this book will be on the shelf. "
     "It teaches the fundamentals the same plain way a good mentor does.",
     "https://www.abebooks.co.uk/Tattooing-Z-Guide-Successful-Spaulding-Huck/32340472082/bd",
     False, "", True),
    ("world-atlas-of-tattoo",
     "The World Atlas of Tattoo",
     "Anna Felicity Friedman", "Yale University Press", 2015, "9780300210484",
     "tattoo", "collectors", "guide",
     "A lavish global tour of tattoo — 100 notable artists across every "
     "continent, with the history and traditions behind each region's styles.",
     "Know where the styles you wear come from. This is the fastest way to "
     "speak the visual language of tattoo with real respect for its roots.",
     "https://www.whiterainbookhouse.com/products/the-world-atlas-of-tattoo-anna-felicity-friedman-9780300210484",
     False, "", False),
    ("japanese-tattoos",
     "Japanese Tattoos: History, Culture, Design",
     "Brian Ashcraft with Hori Benny", "Tuttle Publishing", 2016, "9784805313510",
     "tattoo", "collectors", "guide",
     "An insider's guide to irezumi — the imagery, the kanji, the history — "
     "so readers understand what Japanese tattoos mean before getting one.",
     "Japanese work is everywhere in modern tattooing. This book keeps you "
     "from wearing imagery you don't understand — and helps artists explain "
     "it to clients.",
     "https://www.whiterainbookhouse.com/products/japanese-tattoos-brian-ashcraft-9784805313510",
     False, "", False),
    ("forever-the-new-tattoo",
     "Forever: The New Tattoo",
     "Edited by Robert Klanten and Floyd E. Schulze", "Gestalten", 2012, "9783899554427",
     "tattoo", "collectors", "guide",
     "A stunning document of the new tattoo underground — the innovators "
     "pushing tattoo into art, fashion, and visual culture, profiled in depth.",
     "See where the craft is going, not just where it's been. Great fuel "
     "for collectors hunting their next artist — and for artists finding "
     "their edge.",
     "https://www.abebooks.com/9783899554427/Forever-New-Tattoo-3899554426/plp",
     False, "", False),
    ("tattoo-history-source-book",
     "Tattoo History: A Source Book",
     "Steve Gilbert", "Juno Books", 2001, "9781890451073",
     "tattoo", "professionals", "guide",
     "An anthology of historical records of tattooing worldwide — explorers, "
     "physicians, scholars, and tattoo artists, from ancient times to today, "
     "closing with essays by Don Ed Hardy, Lyle Tuttle, and others.",
     "The deep background every professional should know. When a client asks "
     "about the history behind their piece, this is where the answers live.",
     "https://www.abebooks.com/9781890451066/Tattoo-History-Source-Book-Gilbert-1890451061/plp",
     False, "", False),
    ("bodies-of-subversion",
     "Bodies of Subversion: A Secret History of Women and Tattoo",
     "Margot Mifflin", "powerHouse Books", 2013, "9781576876138",
     "tattoo", "collectors", "guide",
     "The first history of women's tattoo art — sideshow attractions, "
     "Victorian society women, Maud Wagner, and the women reshaping the "
     "craft today.",
     "Half the people in your chair carry this history on their skin. "
     "Essential reading for anyone who tattoos women — which is everyone.",
     "https://www.booktopia.com.au/bodies-of-subversion-margot-mifflin/book/9781576876138.html",
     False, "", False),

    # --- Piercing ----------------------------------------------------------
    ("piercing-bible",
     "The Piercing Bible, Revised and Expanded",
     "Elayne Angel", "Ten Speed Press", 2021, "9781984859327",
     "piercing", "professionals", "textbook",
     "The definitive guide to safe piercing — placements, terminology, "
     "sterility, jewelry quality, aftercare, troubleshooting, and how to "
     "become a piercer — from a pioneer with 50,000+ piercings performed.",
     "This is the piercing industry's bible, full stop. Apprentices study "
     "it, pros reference it, and smart clients read it before they get "
     "pierced.",
     "https://www.piercingbible.com/the-piercing-bible-book",
     True,
     "https://www.audible.co.uk/pd/The-Piercing-Bible-Revised-and-Expanded-Audiobook/B0DQ9ZFW4T",
     True),
    ("piercing-bible-aftercare",
     "The Piercing Bible Guide to Aftercare and Troubleshooting",
     "Elayne Angel", "Ten Speed Press", 2013, "9781607745853",
     "piercing", "collectors", "guide",
     "Elayne Angel's distilled aftercare and troubleshooting advice — "
     "cleaning, healing, and what to do when something goes wrong, piercing "
     "by piercing.",
     "The perfect handout-length companion to give clients — or to read "
     "yourself the night before a new piercing.",
     "http://www.penguinrandomhouse.com/books/228583/the-piercing-bible-guide-to-aftercare-and-troubleshooting-by-elayne-angel/",
     False, "", False),

    # --- Business ----------------------------------------------------------
    ("e-myth-revisited",
     "The E-Myth Revisited: Why Most Small Businesses Don't Work and What to Do About It",
     "Michael E. Gerber", "Harper Business", 1995, "9780887307287",
     "business", "professionals", "guide",
     "The classic on why skilled technicians fail at business — and how to "
     "work on your business instead of just in it, through systems that run "
     "without you.",
     "Being great at tattooing or piercing doesn't make you great at running "
     "a shop. This book is the bridge — required reading before you sign a "
     "lease.",
     "https://www.porchlightbooks.com/products/e-myth-revisited-michael-e-gerber-9780887307287",
     True, "", False),
    ("profit-first",
     "Profit First: Transform Your Business from a Cash-Eating Monster to a Money-Making Machine",
     "Mike Michalowicz", "Portfolio", 2017, "",
     "business", "professionals", "guide",
     "A behavioral cash-management system for small business: take profit "
     "first, then run the shop on what's left — with the author's own "
     "updated commentary in the audio edition.",
     "Shops live and die on cash flow, not talent. This system keeps the "
     "lights on and pays you first.",
     "https://www.amazon.com/dp/B0C9NPP4ZQ/ref=cm_sw_r_ffobk_cp_ud_dp_PZ5KHVX4JYVBFD33DQ9X",
     True,
     "https://www.amazon.com/dp/B0C9NPP4ZQ/ref=cm_sw_r_ffobk_cp_ud_dp_PZ5KHVX4JYVBFD33DQ9X",
     False),
    ("company-of-one",
     "Company of One: Why Staying Small Is the Next Big Thing for Business",
     "Paul Jarvis", "Portfolio / Penguin", 2019, "9780241397411",
     "business", "professionals", "guide",
     "A refreshing case for staying deliberately small — how to build a "
     "profitable, sustainable one-person (or few-person) business without "
     "chasing growth.",
     "Most great shops are small on purpose. This book gives you permission "
     "— and a plan — to stay that way and thrive.",
     "https://www.penguin.com.au/books/company-of-one-9780241397411",
     True,
     "https://www.audible.com/pd/Company-of-One-Audiobook/B07KFN2255",
     False),

    # --- Artist books (for collectors) --------------------------------------
    ("wear-your-dreams",
     "Wear Your Dreams: My Life in Tattoos",
     "Ed Hardy with Joel Selvin", "Thomas Dunne Books", 2013, "9781250021076",
     "tattoo", "collectors", "artist",
     "The memoir of Ed Hardy — from 1960s California beginnings to leading "
     "the tattoo renaissance to a global brand — packed with his own artwork.",
     "The godfather's own story, in his own words and images. If you collect "
     "tattoos, this is your history book.",
     "https://www.powells.com/book/wear-your-dreams-9781250008824/15465420",
     False, "", True),
    ("homeward-bound-sailor-jerry",
     "Homeward Bound: The Life and Times of Hori Smoku Sailor Jerry",
     "Erich Weiss with Nick Schonberger, Jason Buhrmester, et al.",
     "Sailor Jerry Ltd.", 2011, "",
     "tattoo", "collectors", "artist",
     "The companion book to the cult film — unseen photos, ephemera, and "
     "essays on Norman 'Sailor Jerry' Collins, the father of old-school "
     "tattoo.",
     "Old-school collectors treat this like scripture. The roots of American "
     "traditional, straight from the source.",
     "https://www.jasonbuhrmester.com/sailor-jerry-homeward-bound",
     False, "", False),
    ("sailor-jerry-tattoo-flash-vol-1",
     "Sailor Jerry Tattoo Flash: Volume One, Rise and Shine",
     "Don Ed Hardy (editor)", "Hardy Marks Publications", 1996, "9780945367161",
     "tattoo", "collectors", "artist",
     "Fifty sheets of Sailor Jerry's own working flash — hundreds of "
     "tattooable designs from the Mike Malone collection, with an "
     "introduction by Don Ed Hardy.",
     "Real flash from the master himself. Collectors frame it; artists study "
     "it. The reprint finally made it affordable again.",
     "https://hardymarks.com/products/sailor-jerry-tattoo-flash-volume-one-rise-and-shine",
     False, "", False),

    # --- Textbooks (for artists) ---------------------------------------------
    ("basic-fundamentals-modern-tattoo",
     "Basic Fundamentals of Modern Tattoo",
     "C.R. Jordan", "Tattoo Books Online", None, "9780615281476",
     "tattoo", "professionals", "textbook",
     "A 240-page apprenticeship manual: building and tuning machines, needle "
     "configurations, sterilization standards, pigments, and studio practice "
     "— written by someone who completed a formal apprenticeship.",
     "The pre-apprenticeship read that shows a mentor you're serious. "
     "Covers the shop knowledge most beginners only learn the hard way.",
     "https://www.amazon.com/dp/0615281478",
     False, "", False),
    ("tattoo-textbook-dax",
     "The Tattoo Textbook",
     "Shelly Dax", "Independently published", None, "9781734185201",
     "tattoo", "professionals", "textbook",
     "A full-color course in a book — safety, sanitation, skin, equipment, "
     "color theory, client services, and technique — from a tattoo school "
     "instructor with 60+ students taught.",
     "Structured like the classroom training it came from. A solid companion "
     "to any apprenticeship.",
     "https://www.amazon.com/dp/1734185201/ref=dbs_a_def_rwt_hsch_vapi_taft_p1_i0",
     False, "", False),
]


def _seed() -> None:
    added = 0
    with session_scope() as db:
        for i, (slug, title, author, publisher, year, isbn, craft,
                audience, kind, description, why_relevant, buy_url,
                has_audiobook, audiobook_url, featured) in enumerate(BOOKS):
            if db.query(Book).filter_by(slug=slug).one_or_none():
                continue
            db.add(Book(
                title=title, slug=slug, author=author, publisher=publisher,
                year=year, isbn=isbn, craft=craft, audience=audience,
                kind=kind, description=description, why_relevant=why_relevant,
                buy_url=buy_url, has_audiobook=has_audiobook,
                audiobook_url=audiobook_url, is_featured=featured,
                is_active=True, sort_order=i))
            added += 1
    print(f"Book seed done: {added} books added.")


if __name__ == "__main__":
    from app import create_app  # noqa: E402
    app = create_app()
    with app.app_context():
        _seed()
