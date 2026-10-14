"""Phase 4 — reviews, inquiries, and the booking handoff.

End-to-end via the test client: review submit -> moderate -> publish ->
aggregate shows; inquiry -> pro reply -> collector reads; booking request
-> pro confirm. Permission boundaries: strangers can't moderate, can't read
another pro's inbox, can't read another collector's threads.

The community blueprint is registered on a per-test copy of the app
fixture here (the real registration in app/__init__.py is the parent's
integration step); this file changes no shared fixtures.
"""
import pytest

from app.models import BookingInquiry, Profile, Review


@pytest.fixture()
def community_app(app):
    from app import community as _community_module  # noqa: F401 (model registration)
    from app import db as _db
    from app.community import community_bp
    # Models register on Base.metadata at import; create their tables now.
    with app.app_context():
        _db.create_all()
    if "community" not in app.blueprints:
        app.register_blueprint(community_bp)
    # Lets render_template() calls outside a request build URLs.
    app.config["SERVER_NAME"] = "localhost"
    return app


@pytest.fixture()
def community_client(community_app):
    return community_app.test_client()


def _login(client, email, password):
    return client.post("/account/login",
                       data={"email": email, "password": password},
                       follow_redirects=True)


def _logout(client):
    return client.get("/account/logout", follow_redirects=True)


def _seed_cast(app):
    """A claimed studio (+owner), an unclaimed artist listing, a stranger."""
    from app.auth import register_user
    from app.db import get_db
    with app.app_context():
        db = get_db()
        studio_owner = register_user("studio@test.local", "StudioPass1!",
                                     "Studio Boss", roles=["studio_owner"])
        fan = register_user("fan@test.local", "FanPass1!",
                            "Fan One", roles=["collector"])
        stranger = register_user("stranger@test.local", "Stranger1!",
                                 "Stranger", roles=["collector"])
        studio = Profile(kind="studio", display_name="Test Studio",
                         slug="test-studio", city="Casper", state="WY",
                         claim_status="claimed", verified=True,
                         claimed_by_user_id=studio_owner.id,
                         booking_url="https://books.test/studio")
        artist = Profile(kind="tattoo_artist", display_name="Test Artist",
                         slug="test-artist", city="Casper", state="WY")
        db.add_all([studio, artist])
        db.commit()
        return {"studio_id": studio.id, "artist_id": artist.id,
                "owner_id": studio_owner.id, "fan_id": fan.id,
                "stranger_id": stranger.id}


def _review(app, profile_id, user_id):
    from app.db import get_db
    with app.app_context():
        return (get_db().query(Review)
                .filter_by(profile_id=profile_id, user_id=user_id)
                .one_or_none())


def _inquiry(app, inquiry_id):
    from app.db import get_db
    with app.app_context():
        return get_db().get(BookingInquiry, inquiry_id)


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------

def test_review_submit_enters_pending_and_stays_private(community_client,
                                                       community_app):
    ids = _seed_cast(community_app)
    _login(community_client, "fan@test.local", "FanPass1!")
    rv = community_client.post("/community/profiles/test-studio/review",
                               data={"rating": "5", "body": "Incredible work."},
                               follow_redirects=True)
    assert rv.status_code == 200
    review = _review(community_app, ids["studio_id"], ids["fan_id"])
    assert review is not None and review.status == "pending"
    # Pending reviews never show on the public page.
    page = community_client.get("/community/profiles/test-studio/reviews")
    assert b"Incredible work." not in page.data
    assert b"No reviews yet" in page.data


def test_review_rejects_bad_rating(community_client, community_app):
    ids = _seed_cast(community_app)
    _login(community_client, "fan@test.local", "FanPass1!")
    rv = community_client.post("/community/profiles/test-studio/review",
                               data={"rating": "9", "body": "x"},
                               follow_redirects=True)
    assert rv.status_code == 200
    assert _review(community_app, ids["studio_id"], ids["fan_id"]) is None


def test_one_review_per_user_updates_instead(community_client, community_app):
    ids = _seed_cast(community_app)
    _login(community_client, "fan@test.local", "FanPass1!")
    community_client.post("/community/profiles/test-studio/review",
                          data={"rating": "5", "body": "First take."})
    community_client.post("/community/profiles/test-studio/review",
                          data={"rating": "4", "body": "Second take."})
    from app.db import get_db
    with community_app.app_context():
        rows = (get_db().query(Review)
                .filter_by(profile_id=ids["studio_id"], user_id=ids["fan_id"]).all())
    assert len(rows) == 1
    assert rows[0].rating == 4 and rows[0].body == "Second take."
    assert rows[0].status == "pending"  # re-moderated after edit


def test_anonymous_review_redirects_to_login(community_client, community_app):
    _seed_cast(community_app)
    rv = community_client.get("/community/profiles/test-studio/review")
    assert rv.status_code == 302
    assert "/account/login" in rv.headers["Location"]


def test_admin_queue_approve_publishes(community_client,
                                            community_app, owner_user):
    ids = _seed_cast(community_app)
    _login(community_client, "fan@test.local", "FanPass1!")
    community_client.post("/community/profiles/test-studio/review",
                          data={"rating": "5", "body": "Worth every mile."})
    _logout(community_client)
    _login(community_client, "owner@test.local", "OwnerPass1!")

    queue = community_client.get("/community/admin/reviews")
    assert queue.status_code == 200
    assert b"Worth every mile." in queue.data

    review = _review(community_app, ids["studio_id"], ids["fan_id"])
    rv = community_client.post(
        f"/community/admin/reviews/{review.id}/publish",
        follow_redirects=True)
    assert rv.status_code == 200
    assert _review(community_app, ids["studio_id"],
                   ids["fan_id"]).status == "published"

    page = community_client.get("/community/profiles/test-studio/reviews")
    assert b"Worth every mile." in page.data
    assert b"5.0" in page.data and b"1 review" in page.data


def test_admin_hide_keeps_review_off_public_page(community_client,
                                                 community_app, owner_user):
    ids = _seed_cast(community_app)
    _login(community_client, "fan@test.local", "FanPass1!")
    community_client.post("/community/profiles/test-studio/review",
                          data={"rating": "1", "body": "Spammy review."})
    _logout(community_client)
    _login(community_client, "owner@test.local", "OwnerPass1!")
    review = _review(community_app, ids["studio_id"], ids["fan_id"])
    community_client.post(f"/community/admin/reviews/{review.id}/hide",
                          follow_redirects=True)
    assert _review(community_app, ids["studio_id"],
                   ids["fan_id"]).status == "hidden"
    page = community_client.get("/community/profiles/test-studio/reviews")
    assert b"Spammy review." not in page.data
    assert b"No reviews yet" in page.data


def test_legacy_moderate_url_redirects_to_admin(community_client,
                                                community_app, owner_user):
    _seed_cast(community_app)
    _login(community_client, "owner@test.local", "OwnerPass1!")
    rv = community_client.get("/community/moderate")
    assert rv.status_code == 302
    assert "/community/admin/reviews" in rv.headers["Location"]


def test_admin_access_control(community_client, community_app, owner_user):
    ids = _seed_cast(community_app)
    from app.db import get_db
    with community_app.app_context():
        db = get_db()
        db.add(Review(profile_id=ids["studio_id"], user_id=ids["fan_id"],
                      rating=4, body="Seeded.", status="pending"))
        db.commit()
        review_id = db.query(Review).one().id

    # Anonymous -> sent to sign in.
    rv = community_client.get("/community/admin/reviews")
    assert rv.status_code == 302
    assert "/account/login" in rv.headers["Location"]

    # Collector (non-owner) -> 403 everywhere in admin.
    _login(community_client, "fan@test.local", "FanPass1!")
    assert community_client.get("/community/admin/reviews").status_code == 403
    assert community_client.get(
        f"/community/admin/reviews/{review_id}").status_code == 403
    assert community_client.post(
        f"/community/admin/reviews/{review_id}/publish").status_code == 403
    assert community_client.post(
        f"/community/admin/reviews/{review_id}/hide").status_code == 403
    assert community_client.post(
        f"/community/admin/reviews/{review_id}/delete").status_code == 403
    assert community_client.get("/community/moderate").status_code == 403

    # Owner -> 200.
    _logout(community_client)
    _login(community_client, "owner@test.local", "OwnerPass1!")
    assert community_client.get("/community/admin/reviews").status_code == 200
    assert community_client.get(
        f"/community/admin/reviews/{review_id}").status_code == 200


def test_admin_tabs_filter_by_status(community_client, community_app,
                                     owner_user):
    ids = _seed_cast(community_app)
    from app.db import get_db
    with community_app.app_context():
        db = get_db()
        db.add_all([
            Review(profile_id=ids["studio_id"], user_id=ids["fan_id"],
                   rating=5, body="Pending one.", status="pending"),
            Review(profile_id=ids["studio_id"], user_id=ids["stranger_id"],
                   rating=4, body="Published one.", status="published"),
            Review(profile_id=ids["studio_id"], user_id=ids["owner_id"],
                   rating=2, body="Hidden one.", status="hidden"),
        ])
        db.commit()
    _login(community_client, "owner@test.local", "OwnerPass1!")

    pending = community_client.get("/community/admin/reviews?status=pending")
    assert b"Pending one." in pending.data
    assert b"Published one." not in pending.data
    assert b"pending (1)" in pending.data

    published = community_client.get(
        "/community/admin/reviews?status=published")
    assert b"Published one." in published.data
    assert b"Pending one." not in published.data

    hidden = community_client.get("/community/admin/reviews?status=hidden")
    assert b"Hidden one." in hidden.data
    assert b"Pending one." not in hidden.data

    bad = community_client.get("/community/admin/reviews?status=bogus")
    assert b"Pending one." in bad.data  # unknown status falls back to pending


def test_admin_edit_body_publish_hide_delete_cycle(community_client,
                                                   community_app, owner_user):
    ids = _seed_cast(community_app)
    from app.db import get_db
    with community_app.app_context():
        db = get_db()
        db.add(Review(profile_id=ids["studio_id"], user_id=ids["fan_id"],
                      rating=3, body="Rough draft wording.",
                      status="pending"))
        db.commit()
        review_id = db.query(Review).one().id
    _login(community_client, "owner@test.local", "OwnerPass1!")

    # View detail.
    detail = community_client.get(f"/community/admin/reviews/{review_id}")
    assert detail.status_code == 200
    assert b"Rough draft wording." in detail.data

    # Edit the body in place.
    rv = community_client.post(f"/community/admin/reviews/{review_id}",
                               data={"body": "Polished wording."},
                               follow_redirects=True)
    assert rv.status_code == 200
    assert b"Polished wording." in rv.data
    assert _review(community_app, ids["studio_id"],
                   ids["fan_id"]).body == "Polished wording."

    # Publish, then hide again (reversible).
    community_client.post(f"/community/admin/reviews/{review_id}/publish",
                          follow_redirects=True)
    assert _review(community_app, ids["studio_id"],
                   ids["fan_id"]).status == "published"
    community_client.post(f"/community/admin/reviews/{review_id}/hide",
                          follow_redirects=True)
    assert _review(community_app, ids["studio_id"],
                   ids["fan_id"]).status == "hidden"

    # Delete without the confirmation tick is refused.
    community_client.post(f"/community/admin/reviews/{review_id}/delete",
                          data={}, follow_redirects=True)
    assert _review(community_app, ids["studio_id"],
                   ids["fan_id"]) is not None

    # Delete with confirmation removes the row for good.
    community_client.post(f"/community/admin/reviews/{review_id}/delete",
                          data={"confirm": "yes"}, follow_redirects=True)
    assert _review(community_app, ids["studio_id"],
                   ids["fan_id"]) is None
    assert community_client.get(
        f"/community/admin/reviews/{review_id}").status_code == 404


def test_stranger_cannot_touch_admin_routes(community_client, community_app):
    _seed_cast(community_app)
    _login(community_client, "stranger@test.local", "Stranger1!")
    assert community_client.get("/community/admin/reviews").status_code == 403
    assert community_client.post(
        "/community/admin/reviews/1/publish").status_code == 403



def test_aggregate_averages_published_only(community_client, community_app,
                                           owner_user):
    ids = _seed_cast(community_app)
    from app.db import get_db
    with community_app.app_context():
        db = get_db()
        db.add_all([
            Review(profile_id=ids["studio_id"], user_id=ids["fan_id"], rating=5,
                   body="A", status="published"),
            Review(profile_id=ids["studio_id"], user_id=ids["stranger_id"],
                   rating=3, body="B", status="published"),
            Review(profile_id=ids["studio_id"], user_id=ids["owner_id"],
                   rating=1, body="C", status="pending"),
            Review(profile_id=ids["studio_id"], user_id=1,
                   rating=1, body="D", status="hidden"),
        ])
        db.commit()
    page = community_client.get("/community/profiles/test-studio/reviews")
    assert b"4.0" in page.data and b"2 reviews" in page.data
    assert b">A<" in page.data and b">B<" in page.data
    assert b">C<" not in page.data and b">D<" not in page.data


def test_rating_summary_helper(community_app):
    _seed_cast(community_app)
    from app.community import get_rating_summary
    from app.db import get_db
    with community_app.app_context():
        db = get_db()
        db.add_all([
            Review(profile_id=1, user_id=2, rating=5, body="A", status="published"),
            Review(profile_id=1, user_id=3, rating=4, body="B", status="published"),
        ])
        db.commit()
        assert get_rating_summary(1) == (4.5, 2)
        assert get_rating_summary(999) == (0.0, 0)


# ---------------------------------------------------------------------------
# Inquiries
# ---------------------------------------------------------------------------

def test_inquiry_reaches_pro_inbox_only(community_client, community_app):
    _seed_cast(community_app)
    _login(community_client, "fan@test.local", "FanPass1!")
    rv = community_client.post("/community/profiles/test-studio/inquire",
                               data={"message": "Do you do cover-ups?"},
                               follow_redirects=True)
    assert rv.status_code == 200

    from app.db import get_db
    with community_app.app_context():
        inquiry = (get_db().query(BookingInquiry)
                   .filter_by(profile_id=1).one())
    assert inquiry.mode == "inquiry" and inquiry.status == "open"

    # The studio owner sees it in their inbox…
    _logout(community_client)
    _login(community_client, "studio@test.local", "StudioPass1!")
    inbox = community_client.get("/community/inbox")
    assert inbox.status_code == 200
    assert b"Do you do cover-ups?" in inbox.data

    # …but a stranger's inbox is empty (no leak across pros).
    _logout(community_client)
    _login(community_client, "stranger@test.local", "Stranger1!")
    inbox = community_client.get("/community/inbox")
    assert b"Do you do cover-ups?" not in inbox.data


def test_inquiry_thread_reply_roundtrip(community_client, community_app):
    _seed_cast(community_app)
    _login(community_client, "fan@test.local", "FanPass1!")
    community_client.post("/community/profiles/test-studio/inquire",
                          data={"message": "Do you do cover-ups?"})

    from app.db import get_db
    with community_app.app_context():
        inquiry_id = (get_db().query(BookingInquiry)
                      .filter_by(profile_id=1).one().id)

    # Pro replies from their inbox thread.
    _logout(community_client)
    _login(community_client, "studio@test.local", "StudioPass1!")
    rv = community_client.post(f"/community/inbox/{inquiry_id}",
                               data={"body": "Yes — bring reference photos."},
                               follow_redirects=True)
    assert rv.status_code == 200
    assert b"Yes &#8212; bring reference photos." in rv.data or \
        b"bring reference photos" in rv.data

    # Collector reads the reply in their own thread.
    _logout(community_client)
    _login(community_client, "fan@test.local", "FanPass1!")
    thread = community_client.get(f"/community/my-inquiries/{inquiry_id}")
    assert thread.status_code == 200
    assert b"bring reference photos" in thread.data

    # And in the list view.
    listing = community_client.get("/community/my-inquiries")
    assert b"Do you do cover-ups?" in listing.data


def test_stranger_cannot_open_pro_thread(community_client, community_app):
    _seed_cast(community_app)
    _login(community_client, "fan@test.local", "FanPass1!")
    community_client.post("/community/profiles/test-studio/inquire",
                          data={"message": "Secret question."})
    from app.db import get_db
    with community_app.app_context():
        inquiry_id = (get_db().query(BookingInquiry)
                      .filter_by(profile_id=1).one().id)
    _logout(community_client)
    _login(community_client, "stranger@test.local", "Stranger1!")
    assert community_client.get(f"/community/inbox/{inquiry_id}").status_code == 403
    assert community_client.post(f"/community/inbox/{inquiry_id}",
                                 data={"body": "hi"}).status_code == 403


def test_collector_cannot_read_others_threads(community_client, community_app):
    _seed_cast(community_app)
    _login(community_client, "fan@test.local", "FanPass1!")
    community_client.post("/community/profiles/test-studio/inquire",
                          data={"message": "My private question."})
    from app.db import get_db
    with community_app.app_context():
        inquiry_id = (get_db().query(BookingInquiry)
                      .filter_by(profile_id=1).one().id)
    _logout(community_client)
    _login(community_client, "stranger@test.local", "Stranger1!")
    assert community_client.get(f"/community/my-inquiries/{inquiry_id}").status_code == 404
    stranger_list = community_client.get("/community/my-inquiries")
    assert b"My private question." not in stranger_list.data


def test_pro_can_close_thread(community_client, community_app):
    _seed_cast(community_app)
    _login(community_client, "fan@test.local", "FanPass1!")
    community_client.post("/community/profiles/test-studio/inquire",
                          data={"message": "Quick question."})
    from app.db import get_db
    with community_app.app_context():
        inquiry_id = (get_db().query(BookingInquiry)
                      .filter_by(profile_id=1).one().id)
    _logout(community_client)
    _login(community_client, "studio@test.local", "StudioPass1!")
    rv = community_client.post(f"/community/inbox/{inquiry_id}/close",
                               follow_redirects=True)
    assert rv.status_code == 200
    assert _inquiry(community_app, inquiry_id).status == "closed"


def test_platform_owner_sees_all_inbox(community_client, community_app,
                                       owner_user):
    _seed_cast(community_app)
    _login(community_client, "fan@test.local", "FanPass1!")
    community_client.post("/community/profiles/test-studio/inquire",
                          data={"message": "Owner-visible question."})
    _logout(community_client)
    _login(community_client, "owner@test.local", "OwnerPass1!")
    inbox = community_client.get("/community/inbox")
    assert b"Owner-visible question." in inbox.data


# ---------------------------------------------------------------------------
# Booking handoff
# ---------------------------------------------------------------------------

def test_booking_disabled_redirects_to_inquire(community_client, community_app):
    _seed_cast(community_app)
    _login(community_client, "fan@test.local", "FanPass1!")
    rv = community_client.get("/community/profiles/test-studio/book")
    assert rv.status_code == 302
    assert "/community/profiles/test-studio/inquire" in rv.headers["Location"]


def test_booking_settings_toggle_owner_only(community_client, community_app):
    _seed_cast(community_app)
    # Stranger toggles -> 403.
    _login(community_client, "stranger@test.local", "Stranger1!")
    rv = community_client.post("/community/profiles/test-studio/booking-settings",
                               data={"enabled": "on"})
    assert rv.status_code == 403

    # Owner switches it on.
    _logout(community_client)
    _login(community_client, "studio@test.local", "StudioPass1!")
    rv = community_client.post("/community/profiles/test-studio/booking-settings",
                               data={"enabled": "on"}, follow_redirects=True)
    assert rv.status_code == 200
    from app.community import ProBookingSettings
    from app.db import get_db
    with community_app.app_context():
        db = get_db()
        settings = db.get(ProBookingSettings, 1)
        assert settings is not None and settings.platform_booking_enabled is True
        assert db.get(Profile, 1).booking_mode == "platform"

    # And back off.
    community_client.post("/community/profiles/test-studio/booking-settings",
                          data={}, follow_redirects=True)
    with community_app.app_context():
        db = get_db()
        assert db.get(ProBookingSettings, 1).platform_booking_enabled is False
        assert db.get(Profile, 1).booking_mode == "external"


def test_booking_request_confirm_decline_flow(community_client, community_app):
    _seed_cast(community_app)
    # Owner switches platform booking on.
    _login(community_client, "studio@test.local", "StudioPass1!")
    community_client.post("/community/profiles/test-studio/booking-settings",
                          data={"enabled": "on"})

    # Collector requests a booking.
    _logout(community_client)
    _login(community_client, "fan@test.local", "FanPass1!")
    rv = community_client.post("/community/profiles/test-studio/book",
                               data={"date": "2026-11-05", "time": "2pm",
                                     "notes": "Small dagger tattoo."},
                               follow_redirects=True)
    assert rv.status_code == 200
    from app.db import get_db
    with community_app.app_context():
        inquiry = (get_db().query(BookingInquiry)
                   .filter_by(mode="platform").one())
    assert inquiry.status == "open"
    assert "2026-11-05" in inquiry.message and "dagger" in inquiry.message
    assert b"Booking request" in rv.data  # landed on the collector thread

    # Pro confirms from the inbox thread.
    _logout(community_client)
    _login(community_client, "studio@test.local", "StudioPass1!")
    rv = community_client.post(f"/community/inbox/{inquiry.id}/confirm",
                               follow_redirects=True)
    assert rv.status_code == 200
    assert _inquiry(community_app, inquiry.id).status == "confirmed"
    assert b"Confirmed" in rv.data

    # A second request gets declined.
    _logout(community_client)
    _login(community_client, "fan@test.local", "FanPass1!")
    community_client.post("/community/profiles/test-studio/book",
                          data={"date": "2026-11-06", "notes": "Another one."})
    with community_app.app_context():
        second = (get_db().query(BookingInquiry)
                  .filter(BookingInquiry.id != inquiry.id).one())
    _logout(community_client)
    _login(community_client, "studio@test.local", "StudioPass1!")
    community_client.post(f"/community/inbox/{second.id}/decline",
                          follow_redirects=True)
    assert _inquiry(community_app, second.id).status == "declined"

    # Confirming a non-open request is refused.
    rv = community_client.post(f"/community/inbox/{second.id}/confirm",
                               follow_redirects=True)
    assert _inquiry(community_app, second.id).status == "declined"


def test_booking_panel_partial_paths(community_app):
    from flask import render_template
    with community_app.app_context():
        from app.db import get_db
        db = get_db()
        # Need the seeded profile rows for this render-only test.
        _seed_cast(community_app)
        profile = db.get(Profile, 1)
        html = render_template("community/_booking_panel.html", profile=profile)
        # (a) inquiry always; (c) external link present (booking_url seeded).
        assert "/community/profiles/test-studio/inquire" in html
        assert "https://books.test/studio" in html
        # (b) request booking hidden while disabled.
        assert "/community/profiles/test-studio/book" not in html
        profile.booking_mode = "platform"
        html = render_template("community/_booking_panel.html", profile=profile)
        assert "/community/profiles/test-studio/book" in html


def test_reviews_section_partial_published_only(community_app):
    from flask import render_template
    _seed_cast(community_app)
    from app.db import get_db
    with community_app.app_context():
        db = get_db()
        db.add_all([
            Review(profile_id=1, user_id=2, rating=5, body="Public praise.",
                   status="published"),
            Review(profile_id=1, user_id=3, rating=2, body="Still pending…",
                   status="pending"),
        ])
        db.commit()
        profile = db.get(Profile, 1)
        from app.community import get_rating_summary
        summary = get_rating_summary(1)
        published = (db.query(Review)
                     .filter_by(profile_id=1, status="published").all())
        html = render_template("community/_reviews_section.html",
                               profile=profile, rating_summary=summary,
                               published_reviews=published)
        assert "Public praise." in html
        assert "Still pending" not in html
        assert "5.0" in html
        # Degraded mode (no context) still links out.
        html = render_template("community/_reviews_section.html",
                               profile=profile)
        assert "/community/profiles/test-studio/reviews" in html
