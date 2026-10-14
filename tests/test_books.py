"""Books vertical: model/seed, landing page, detail, her-textbook page."""
import sys

from app.models import Book, TextbookNotify


def _seed_books(app):
    sys.path.insert(0, "scripts")
    import seed_books
    with app.app_context():
        seed_books._seed()


def _count(app):
    from app.db import get_db
    with app.app_context():
        return get_db().query(Book).count()


def test_seed_is_idempotent(app):
    _seed_books(app)
    first = _count(app)
    assert first >= 16, f"expected at least 16 seeded books, got {first}"
    _seed_books(app)
    assert _count(app) == first


def test_seed_covers_all_crafts_and_shelves(app):
    _seed_books(app)
    from app.db import get_db
    with app.app_context():
        db = get_db()
        crafts = {b.craft for b in db.query(Book).all()}
        kinds = {b.kind for b in db.query(Book).all()}
        audiences = {b.audience for b in db.query(Book).all()}
    assert {"tattoo", "piercing", "business"} <= crafts
    assert {"guide", "artist", "textbook"} <= kinds
    assert {"collectors", "professionals"} <= audiences


def test_audiobook_flags_only_where_verified(app):
    _seed_books(app)
    from app.db import get_db
    with app.app_context():
        db = get_db()
        audio = {b.slug for b in db.query(Book).filter_by(has_audiobook=True).all()}
    # Verified audio editions only.
    assert "piercing-bible" in audio
    assert "profit-first" in audio
    assert "company-of-one" in audio
    assert "e-myth-revisited" in audio
    # Print-only craft books must NOT be flagged.
    for slug in ("tattooing-a-to-z", "world-atlas-of-tattoo", "japanese-tattoos",
                 "forever-the-new-tattoo", "tattoo-history-source-book",
                 "bodies-of-subversion", "wear-your-dreams",
                 "sailor-jerry-tattoo-flash-vol-1",
                 "basic-fundamentals-modern-tattoo", "tattoo-textbook-dax"):
        assert slug not in audio, slug


def test_index_renders_landing(client, app):
    _seed_books(app)
    rv = client.get("/books/")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "Books worth your shelf" in body
    assert "Textbooks" in body          # textbooks shelf
    assert "Artist books" in body        # artist books shelf
    assert "textbook" in body           # her-textbook banner link
    assert "The Piercing Bible" in body
    assert "Tattooing A to Z" in body


def test_index_craft_filter(client, app):
    _seed_books(app)
    rv = client.get("/books/?craft=piercing")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "The Piercing Bible" in body
    assert "Tattooing A to Z" not in body
    # Invalid craft is ignored, not an error.
    rv = client.get("/books/?craft=nope")
    assert rv.status_code == 200


def test_index_search(client, app):
    _seed_books(app)
    rv = client.get("/books/?q=Hardy")
    assert rv.status_code == 200
    assert "Ed Hardy" in rv.data.decode()
    rv = client.get("/books/?q=zzzz-no-such-book")
    assert b"No books found" in rv.data


def test_detail_page(client, app):
    _seed_books(app)
    rv = client.get("/books/piercing-bible")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "The Piercing Bible" in body
    assert "Elayne Angel" in body
    assert "Audiobook edition verified" in body
    assert "audible.co.uk" in body
    assert "piercingbible.com" in body


def test_detail_print_only_has_no_audiobook_badge(client, app):
    _seed_books(app)
    rv = client.get("/books/tattooing-a-to-z")
    assert rv.status_code == 200
    assert "Audiobook edition verified" not in rv.data.decode()


def test_detail_404_and_inactive_hidden(client, app):
    _seed_books(app)
    rv = client.get("/books/no-such-book")
    assert rv.status_code == 404
    from app.db import get_db
    with app.app_context():
        db = get_db()
        book = db.query(Book).filter_by(slug="tattooing-a-to-z").one()
        book.is_active = False
        db.commit()
    rv = client.get("/books/tattooing-a-to-z")
    assert rv.status_code == 404


def test_her_textbook_landing(client, app):
    """Her textbook page: coming soon, no invented title/price/date/buy."""
    rv = client.get("/books/textbook")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "Coming soon" in body
    assert "Angie Valentin" in body
    assert "Luna &amp; Lotus" in body or "Luna & Lotus" in body
    assert "twelve chapters" in body
    assert "Notify me" in body
    for invented in ("$19.99", "$29.99", "Buy now", "Add to cart",
                     "Published 2026", "Available now"):
        assert invented not in body, invented


def test_textbook_route_not_swallowed_by_slug(client, app):
    _seed_books(app)
    rv = client.get("/books/textbook")
    assert rv.status_code == 200
    assert b"Angie Valentin" in rv.data


def test_textbook_notify_signup(client, app):
    rv = client.post("/books/textbook/notify",
                     data={"name": "Test Fan", "email": "fan@example.com"},
                     follow_redirects=True)
    assert rv.status_code == 200
    assert b"on the list" in rv.data
    from app.db import get_db
    with app.app_context():
        row = get_db().query(TextbookNotify).filter_by(
            email="fan@example.com").one_or_none()
    assert row is not None and row.name == "Test Fan"


def test_textbook_notify_rejects_bad_email_and_dedupes(client, app):
    client.post("/books/textbook/notify",
                data={"name": "X", "email": "not-an-email"})
    from app.db import get_db
    with app.app_context():
        assert get_db().query(TextbookNotify).filter_by(
            email="not-an-email").one_or_none() is None
    client.post("/books/textbook/notify",
                data={"name": "A", "email": "dup@example.com"})
    client.post("/books/textbook/notify",
                data={"name": "B", "email": "dup@example.com"})
    with app.app_context():
        rows = get_db().query(TextbookNotify).filter_by(
            email="dup@example.com").all()
    assert len(rows) == 1


def test_textbook_notify_requires_csrf_when_enabled(client, app):
    app.config["CSRF_ENABLED"] = True
    rv = client.post("/books/textbook/notify",
                     data={"name": "X", "email": "x@example.com"})
    assert rv.status_code == 400


# ---------------------------------------------------------------------------
# Owner CRUD: "this needs to be editable by me."
# ---------------------------------------------------------------------------

def _book_payload(**over):
    data = {
        "title": "Owner Test Book", "slug": "", "author": "Test Author",
        "publisher": "Test Press", "year": "2020", "isbn": "9780000000000",
        "craft": "tattoo", "audience": "professionals", "kind": "guide",
        "description": "A test book.", "why_relevant": "Because testing.",
        "cover_image": "", "buy_url": "https://example.com/buy",
        "audiobook_url": "", "sort_order": "5", "is_active": "on",
    }
    data.update(over)
    return data


def test_owner_books_list_requires_owner(app, owner_client):
    anon = app.test_client()
    assert anon.get("/owner/books").status_code in (302, 403)
    rv = owner_client.get("/owner/books")
    assert rv.status_code == 200


def test_owner_can_create_book(owner_client, app):
    rv = owner_client.post("/owner/books/new", data=_book_payload(),
                           follow_redirects=False)
    assert rv.status_code == 302
    from app.db import get_db
    with app.app_context():
        book = get_db().query(Book).filter_by(title="Owner Test Book").one()
        assert book.slug == "owner-test-book"
        assert book.craft == "tattoo" and book.kind == "guide"
        assert book.is_active is True and book.sort_order == 5


def test_owner_create_requires_title(owner_client, app):
    rv = owner_client.post("/owner/books/new", data=_book_payload(title=""))
    assert rv.status_code == 200
    assert b"A title is required" in rv.data


def test_owner_can_edit_book_and_featured_order(owner_client, app):
    _seed_books(app)
    from app.db import get_db
    with app.app_context():
        book = get_db().query(Book).filter_by(slug="tattooing-a-to-z").one()
        book_id = book.id
    rv = owner_client.post(
        f"/owner/books/{book_id}/edit",
        data=_book_payload(title="Tattooing A to Z (2nd ed.)",
                           is_featured="on", sort_order="1",
                           has_audiobook="on",
                           audiobook_url="https://example.com/audio"),
        follow_redirects=False)
    assert rv.status_code == 302
    with app.app_context():
        book = get_db().query(Book).get(book_id)
        assert book.title == "Tattooing A to Z (2nd ed.)"
        assert book.is_featured is True and book.sort_order == 1
        assert book.has_audiobook is True


def test_owner_audiobook_guard_needs_link(owner_client, app):
    _seed_books(app)
    from app.db import get_db
    with app.app_context():
        book_id = get_db().query(Book).filter_by(
            slug="tattooing-a-to-z").one().id
    rv = owner_client.post(
        f"/owner/books/{book_id}/edit",
        data=_book_payload(has_audiobook="on", audiobook_url=""))
    assert rv.status_code == 200
    assert b"verified really exist" in rv.data


def test_owner_can_delete_book(owner_client, app):
    _seed_books(app)
    from app.db import get_db
    with app.app_context():
        book_id = get_db().query(Book).filter_by(
            slug="forever-the-new-tattoo").one().id
    rv = owner_client.post(f"/owner/books/{book_id}/delete",
                           follow_redirects=False)
    assert rv.status_code == 302
    with app.app_context():
        assert get_db().query(Book).get(book_id) is None


def test_owner_books_links_visible_on_dashboard(owner_client):
    rv = owner_client.get("/owner/")
    assert rv.status_code == 200
    assert b"Manage books" in rv.data
