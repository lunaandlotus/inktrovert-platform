"""Books — magazine/editorial layer reading pages.

The Books section stands next to Podcasts: real, verified books for the
craft — tattoo, piercing, and the business of running a shop — plus two
special shelves:

  * Textbooks — published training manuals for artists and apprentices.
  * Artist books — flash books and monographs published by artists
    themselves, for collectors and fans.

Angie Valentin's own apprentice textbook (Luna & Lotus) has its own
coming-soon landing page at /books/textbook with an email-notify signup.
It is NOT published yet: no invented title, date, price, or buy links.

Browsing is public — no login required.
"""
from __future__ import annotations

import re

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .auth import require_csrf
from .db import get_db
from .models import BOOK_AUDIENCES, BOOK_CRAFTS, BOOK_KINDS, Book, TextbookNotify

book_bp = Blueprint("books", __name__, url_prefix="/books")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _active_books():
    db = get_db()
    return db.query(Book).filter_by(is_active=True)


def _book_by_slug(slug: str) -> Book:
    db = get_db()
    book = db.query(Book).filter_by(slug=slug, is_active=True).first()
    if book is None:
        abort(404)
    return book


def _craft_label(craft: str) -> str:
    return {"tattoo": "Tattoo", "piercing": "Piercing", "business": "Business"}.get(
        craft, craft.title())


def _audience_label(audience: str) -> str:
    return {"collectors": "Collectors", "professionals": "Professionals"}.get(
        audience, audience.title())


def _kind_label(kind: str) -> str:
    return {"guide": "Guide", "artist": "Artist book",
            "textbook": "Textbook"}.get(kind, kind.title())


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@book_bp.get("/")
def index():
    """The Books landing page: featured picks, shelves, browse by craft."""
    craft = (request.args.get("craft") or "").strip().lower()
    q = (request.args.get("q") or "").strip()
    if craft and craft not in BOOK_CRAFTS:
        craft = ""

    query = _active_books()
    if craft:
        query = query.filter(Book.craft == craft)
    if q:
        like = f"%{q}%"
        query = query.filter(
            Book.title.ilike(like) | Book.author.ilike(like))
    results = query.order_by(Book.sort_order, Book.title).all()

    db = get_db()
    featured = (db.query(Book)
                .filter_by(is_active=True, is_featured=True)
                .order_by(Book.sort_order).limit(3).all())
    textbooks = (db.query(Book)
                 .filter_by(is_active=True, kind="textbook")
                 .order_by(Book.sort_order).all())
    artist_books = (db.query(Book)
                    .filter_by(is_active=True, kind="artist")
                    .order_by(Book.sort_order).all())
    crafts = [(c, _craft_label(c)) for c in BOOK_CRAFTS]

    return render_template(
        "books/index.html",
        results=results, featured=featured, textbooks=textbooks,
        artist_books=artist_books, crafts=crafts,
        active_craft=craft, q=q,
        craft_label=_craft_label, audience_label=_audience_label,
        kind_label=_kind_label,
    )


@book_bp.get("/textbook")
def her_textbook():
    """Landing page for Angie Valentin's coming-soon apprentice textbook.

    Pre-launch: no title, date, price, or buy links are shown — only what
    is real (author, studio, chapter scope) plus an email-notify signup.
    """
    return render_template("books/textbook.html")


@book_bp.post("/textbook/notify")
@require_csrf
def textbook_notify():
    """Email-notify signup for her textbook launch."""
    name = (request.form.get("name") or "").strip()[:120]
    email = (request.form.get("email") or "").strip().lower()[:254]
    if not _EMAIL_RE.match(email):
        flash("That email doesn't look right — try again?", "error")
        return redirect(url_for("books.her_textbook"))
    db = get_db()
    existing = db.query(TextbookNotify).filter_by(email=email).first()
    if existing is None:
        db.add(TextbookNotify(name=name, email=email))
        db.commit()
        flash("You're on the list — you'll hear about it first.", "ok")
    else:
        flash("You're already on the list — we'll be in touch.", "ok")
    return redirect(url_for("books.her_textbook"))


@book_bp.get("/<slug>")
def detail(slug: str):
    """One book: cover, description, why it matters, where to get it."""
    book = _book_by_slug(slug)
    db = get_db()
    more = (db.query(Book)
            .filter(Book.id != book.id, Book.is_active.is_(True))
            .filter((Book.craft == book.craft) | (Book.kind == book.kind))
            .order_by(Book.sort_order).limit(4).all())
    return render_template(
        "books/detail.html", book=book, more=more,
        craft_label=_craft_label, audience_label=_audience_label,
        kind_label=_kind_label,
    )
