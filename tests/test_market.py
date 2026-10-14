"""Phase 5 — B2B supply marketplace tests.

Covers: sample seeding (idempotent), seller create/publish/edit/status flow,
cart behavior (stock caps, out-of-stock), checkout with no Stripe keys
(graceful "coming soon" + pending order), buyer order views + cancel,
seller fulfill (with stock decrement), and permission denials.

The shared conftest `app` fixture is shadowed here so the market blueprint
is registered (app/__init__.py is frozen for this worker); everything else
reuses conftest's fixtures.
"""
import io
import os

import pytest

from app import db as _db
from app.market import (MarketOrder, MarketOrderItem, SupplyListingDetail,
                        ensure_sample_products, mark_order_paid, market_bp)
from app.models import SupplyListing, User

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/inktrovert-test-bootstrap.db")


@pytest.fixture()
def app(tmp_path):
    import app.market  # noqa: F401 — register new models on Base before create_all
    from app import create_app
    application = create_app()
    if "market" not in application.blueprints:
        application.register_blueprint(market_bp)
    _db.init_engine(f"sqlite:///{tmp_path}/market-test.db")
    application.config["UPLOAD_DIR"] = str(tmp_path / "uploads")
    with application.app_context():
        _db.create_all()
        from app.auth import ensure_roles
        ensure_roles()
    application.config["TESTING"] = True
    application.config["CSRF_ENABLED"] = False
    yield application
    _db.get_engine().dispose()


def _make_user(app, email, password, full_name="", roles=()):
    from app.auth import register_user
    with app.app_context():
        return register_user(email, password, full_name, roles=roles)


@pytest.fixture()
def seller_user(app):
    return _make_user(app, "seller@test.local", "SellerPass1!", "Test Seller",
                      roles=["approved_brand", "collector"])


@pytest.fixture()
def buyer_user(app):
    return _make_user(app, "buyer@test.local", "BuyerPass1!", "Test Buyer",
                      roles=["collector"])


@pytest.fixture()
def stranger_user(app):
    return _make_user(app, "stranger@test.local", "StrangerPass1!", "Test Stranger",
                      roles=["collector"])


def _login(client, email, password):
    return client.post("/account/login",
                       data={"email": email, "password": password},
                       follow_redirects=True)


@pytest.fixture()
def seller_client(app, seller_user):
    c = app.test_client()
    _login(c, "seller@test.local", "SellerPass1!")
    return c


@pytest.fixture()
def buyer_client(app, buyer_user):
    c = app.test_client()
    _login(c, "buyer@test.local", "BuyerPass1!")
    return c


@pytest.fixture()
def stranger_client(app, stranger_user):
    c = app.test_client()
    _login(c, "stranger@test.local", "StrangerPass1!")
    return c


@pytest.fixture()
def owner_client(app, owner_user):
    c = app.test_client()
    _login(c, "owner@test.local", "OwnerPass1!")
    return c


def _add_listing(seller_id, title="Test Balm", category="aftercare",
                 price_cents=1800, status="listed", stock=10, is_sample=False):
    with _db.session_scope() as db:
        listing = SupplyListing(seller_user_id=seller_id, title=title,
                                category=category, description="A fine product.",
                                price_cents=price_cents, status=status)
        db.add(listing)
        db.flush()
        db.add(SupplyListingDetail(supply_listing_id=listing.id, stock=stock,
                                   is_sample=is_sample))
        return listing.id


def _place_order(client, listing_id, qty=2):
    client.post(f"/market/cart/add/{listing_id}", data={"qty": str(qty)})
    return client.post("/market/checkout",
                       data={"buyer_name": "Test Buyer",
                             "buyer_email": "buyer@test.local",
                             "buyer_note": "Ship to the studio."})


def _orders():
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    with _db.session_scope() as db:
        return list(db.execute(
            select(MarketOrder)
            .options(selectinload(MarketOrder.items))
            .order_by(MarketOrder.id)).scalars())


# ---------------------------------------------------------------------------
# Catalog + sample seeding
# ---------------------------------------------------------------------------

def test_catalog_seeds_sample_products_idempotently(client, owner_user):
    assert client.get("/market/").status_code == 200
    body = client.get("/market/").get_data(as_text=True)
    assert "Sample listings" in body
    assert "Tattoo Aftercare Balm" in body
    with _db.session_scope() as db:
        count = db.query(SupplyListing).filter_by(status="listed").count()
    assert count == 8  # second GET did not duplicate


def test_catalog_search_and_category_filter(seller_client, seller_user):
    _add_listing(seller_user.id, title="Sterile Needle Cartridges", category="needles")
    _add_listing(seller_user.id, title="Aftercare Balm", category="aftercare")
    body = seller_client.get("/market/?q=needle").get_data(as_text=True)
    assert "Sterile Needle Cartridges" in body
    assert "Aftercare Balm" not in body
    body = seller_client.get("/market/?category=aftercare").get_data(as_text=True)
    assert "Aftercare Balm" in body
    assert "Sterile Needle Cartridges" not in body


def test_draft_listing_hidden_from_catalog(seller_client, seller_user):
    lid = _add_listing(seller_user.id, title="Unpublished Widget", status="draft")
    assert seller_client.get("/market/").get_data(as_text=True).find(
        "Unpublished Widget") == -1
    assert seller_client.get(f"/market/p/{lid}").status_code == 404


def test_product_detail_renders(seller_client, seller_user):
    lid = _add_listing(seller_user.id, title="Detail Balm")
    body = seller_client.get(f"/market/p/{lid}").get_data(as_text=True)
    assert "Detail Balm" in body
    assert "$18.00" in body
    assert seller_client.get("/market/p/999999").status_code == 404


# ---------------------------------------------------------------------------
# Seller dashboard
# ---------------------------------------------------------------------------

def test_dashboard_requires_login(client):
    resp = client.get("/market/dashboard")
    assert resp.status_code == 302
    assert "/account/login" in resp.headers["Location"]


def test_seller_create_publish_flow(seller_client, seller_user):
    assert seller_client.get("/market/dashboard/new").status_code == 200
    png = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    resp = seller_client.post(
        "/market/dashboard/new",
        data={"title": "Test Balm", "category": "balm",
              "description": "Good stuff.", "price": "18.00", "stock": "5",
              "image": (io.BytesIO(png), "balm.png")},
        content_type="multipart/form-data", follow_redirects=False)
    assert resp.status_code == 302
    with _db.session_scope() as db:
        listing = db.query(SupplyListing).filter_by(title="Test Balm").one()
        assert listing.status == "draft"
        assert listing.price_cents == 1800
        assert listing.seller_user_id == seller_user.id
        detail = db.get(SupplyListingDetail, listing.id)
        assert detail.stock == 5
        assert detail.image.endswith(".png")
        lid = listing.id
    # appears on dashboard, not in catalog
    assert "Test Balm" in seller_client.get("/market/dashboard").get_data(as_text=True)
    assert "Test Balm" not in seller_client.get("/market/").get_data(as_text=True)
    # publish
    resp = seller_client.post(f"/market/dashboard/{lid}/status",
                              data={"action": "publish"})
    assert resp.status_code == 302
    with _db.session_scope() as db:
        assert db.get(SupplyListing, lid).status == "listed"
    assert "Test Balm" in seller_client.get("/market/").get_data(as_text=True)
    # unpublish then remove
    seller_client.post(f"/market/dashboard/{lid}/status", data={"action": "unpublish"})
    with _db.session_scope() as db:
        assert db.get(SupplyListing, lid).status == "draft"
    seller_client.post(f"/market/dashboard/{lid}/status", data={"action": "remove"})
    with _db.session_scope() as db:
        assert db.get(SupplyListing, lid).status == "removed"


def test_listing_create_validation(seller_client):
    resp = seller_client.post("/market/dashboard/new",
                              data={"title": "", "category": "bogus",
                                    "price": "0", "stock": ""})
    assert resp.status_code == 400
    with _db.session_scope() as db:
        assert db.query(SupplyListing).count() == 0


def test_seller_can_edit_own_listing(seller_client, seller_user):
    lid = _add_listing(seller_user.id, title="Old Title")
    assert seller_client.get(f"/market/dashboard/{lid}/edit").status_code == 200
    seller_client.post(f"/market/dashboard/{lid}/edit",
                       data={"title": "New Title", "category": "ink",
                             "description": "Updated.", "price": "25.50",
                             "stock": "7"})
    with _db.session_scope() as db:
        listing = db.get(SupplyListing, lid)
        assert listing.title == "New Title"
        assert listing.category == "ink"
        assert listing.price_cents == 2550
        assert db.get(SupplyListingDetail, lid).stock == 7


def test_owner_can_manage_others_listings(owner_client, seller_user):
    lid = _add_listing(seller_user.id, title="Seller Widget")
    assert owner_client.get(f"/market/dashboard/{lid}/edit").status_code == 200


def test_stranger_cannot_manage_others_listings(stranger_client, seller_user):
    lid = _add_listing(seller_user.id, title="Seller Widget")
    assert stranger_client.get(f"/market/dashboard/{lid}/edit").status_code == 403
    assert stranger_client.post(
        f"/market/dashboard/{lid}/status",
        data={"action": "publish"}).status_code == 403
    with _db.session_scope() as db:
        assert db.get(SupplyListing, lid).status == "listed"


# ---------------------------------------------------------------------------
# Cart
# ---------------------------------------------------------------------------

def test_cart_add_view_remove_clear(buyer_client, seller_user):
    lid = _add_listing(seller_user.id, title="Cart Balm", stock=10)
    resp = buyer_client.post(f"/market/cart/add/{lid}", data={"qty": "2"})
    assert resp.status_code == 302
    body = buyer_client.get("/market/cart").get_data(as_text=True)
    assert "Cart Balm" in body
    assert "$36.00" in body
    buyer_client.post(f"/market/cart/remove/{lid}")
    assert "Cart Balm" not in buyer_client.get("/market/cart").get_data(as_text=True)
    buyer_client.post(f"/market/cart/add/{lid}", data={"qty": "1"})
    buyer_client.post("/market/cart/clear")
    assert "Your cart is empty" in buyer_client.get("/market/cart").get_data(as_text=True)


def test_cart_caps_qty_at_stock(buyer_client, seller_user):
    lid = _add_listing(seller_user.id, title="Low Stock Ink", stock=3)
    buyer_client.post(f"/market/cart/add/{lid}", data={"qty": "10"})
    with buyer_client.session_transaction() as sess:
        assert sess["market_cart"][str(lid)] == 3


def test_cannot_add_out_of_stock(buyer_client, seller_user):
    lid = _add_listing(seller_user.id, title="Gone Balm", stock=0)
    buyer_client.post(f"/market/cart/add/{lid}", data={"qty": "1"})
    with buyer_client.session_transaction() as sess:
        assert str(lid) not in (sess.get("market_cart") or {})


def test_cannot_add_unlisted_product(buyer_client, seller_user):
    lid = _add_listing(seller_user.id, title="Draft Balm", status="draft")
    assert buyer_client.post(f"/market/cart/add/{lid}",
                             data={"qty": "1"}).status_code == 404


# ---------------------------------------------------------------------------
# Checkout (no Stripe keys -> graceful "coming soon", order stays pending)
# ---------------------------------------------------------------------------

def test_checkout_coming_soon_records_pending_order(buyer_client, seller_user,
                                                   buyer_user):
    lid = _add_listing(seller_user.id, title="Checkout Balm", price_cents=1800,
                       stock=10)
    assert buyer_client.get("/market/checkout").status_code == 302  # empty cart
    buyer_client.post(f"/market/cart/add/{lid}", data={"qty": "2"})
    assert buyer_client.get("/market/checkout").status_code == 200
    resp = buyer_client.post("/market/checkout",
                             data={"buyer_name": "Test Buyer",
                                   "buyer_email": "buyer@test.local",
                                   "buyer_note": "Ship to the studio."})
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Order received" in body
    assert "isn\u2019t wired up yet" in body or "isn't wired up yet" in body
    orders = _orders()
    assert len(orders) == 1
    order = orders[0]
    assert order.status == "pending"
    assert order.total_cents == 3600
    assert order.buyer_user_id == buyer_user.id
    assert order.buyer_email == "buyer@test.local"
    assert len(order.items) == 1
    assert order.items[0].qty == 2
    assert order.items[0].price_cents == 1800  # snapshot
    # cart cleared; order visible to buyer
    assert "Your cart is empty" in buyer_client.get("/market/cart").get_data(as_text=True)
    assert f"#{order.id}" in buyer_client.get("/market/orders").get_data(as_text=True)
    body = buyer_client.get(f"/market/order/{order.id}/success").get_data(as_text=True)
    assert "Order confirmed" in body


def test_checkout_requires_name_and_email(buyer_client, seller_user):
    lid = _add_listing(seller_user.id, title="Checkout Balm")
    buyer_client.post(f"/market/cart/add/{lid}", data={"qty": "1"})
    resp = buyer_client.post("/market/checkout",
                             data={"buyer_name": "", "buyer_email": "nope"})
    assert resp.status_code == 400
    assert _orders() == []


def test_guest_checkout_works_without_login(client, seller_user):
    lid = _add_listing(seller_user.id, title="Guest Balm")
    client.post(f"/market/cart/add/{lid}", data={"qty": "1"})
    resp = client.post("/market/checkout",
                       data={"buyer_name": "Guest", "buyer_email": "g@example.com"})
    assert resp.status_code == 200
    orders = _orders()
    assert len(orders) == 1 and orders[0].buyer_user_id is None
    assert f"/market/orders/{orders[0].id}" in resp.get_data(as_text=True) or \
        f"Order #{orders[0].id}" in resp.get_data(as_text=True)


# ---------------------------------------------------------------------------
# Buyer order views + cancel
# ---------------------------------------------------------------------------

def test_buyer_can_cancel_pending_order(buyer_client, seller_user):
    lid = _add_listing(seller_user.id, title="Cancel Balm")
    _place_order(buyer_client, lid, qty=1)
    order = _orders()[0]
    resp = buyer_client.post(f"/market/orders/{order.id}/cancel",
                             follow_redirects=False)
    assert resp.status_code == 302
    with _db.session_scope() as db:
        assert db.get(MarketOrder, order.id).status == "canceled"


def test_order_visibility_permissions(buyer_client, stranger_client, seller_user):
    lid = _add_listing(seller_user.id, title="Private Balm")
    _place_order(buyer_client, lid, qty=1)
    order = _orders()[0]
    # stranger (different session) cannot see it
    assert stranger_client.get(f"/market/orders/{order.id}").status_code == 404
    assert stranger_client.post(
        f"/market/orders/{order.id}/cancel").status_code == 404
    assert stranger_client.get(
        f"/market/order/{order.id}/success").status_code == 404
    # buyer can
    assert buyer_client.get(f"/market/orders/{order.id}").status_code == 200


# ---------------------------------------------------------------------------
# Seller orders + fulfill
# ---------------------------------------------------------------------------

def test_seller_fulfills_order_and_decrements_stock(buyer_client, seller_client,
                                                   seller_user):
    lid = _add_listing(seller_user.id, title="Fulfill Balm", stock=10)
    _place_order(buyer_client, lid, qty=2)
    order = _orders()[0]
    body = seller_client.get("/market/dashboard/orders").get_data(as_text=True)
    assert f"Order #{order.id}" in body
    resp = seller_client.post(f"/market/dashboard/orders/{order.id}/fulfill")
    assert resp.status_code == 302
    with _db.session_scope() as db:
        assert db.get(MarketOrder, order.id).status == "fulfilled"
        assert db.get(SupplyListingDetail, lid).stock == 8


def test_stranger_cannot_fulfill_others_order(stranger_client, buyer_client,
                                             seller_user):
    lid = _add_listing(seller_user.id, title="Fulfill Balm")
    _place_order(buyer_client, lid, qty=1)
    order = _orders()[0]
    assert stranger_client.post(
        f"/market/dashboard/orders/{order.id}/fulfill").status_code == 403
    with _db.session_scope() as db:
        assert db.get(MarketOrder, order.id).status == "pending"


def test_cannot_fulfill_canceled_order(buyer_client, seller_client, seller_user):
    lid = _add_listing(seller_user.id, title="Fulfill Balm")
    _place_order(buyer_client, lid, qty=1)
    order = _orders()[0]
    buyer_client.post(f"/market/orders/{order.id}/cancel")
    seller_client.post(f"/market/dashboard/orders/{order.id}/fulfill",
                       follow_redirects=True)
    with _db.session_scope() as db:
        assert db.get(MarketOrder, order.id).status == "canceled"


# ---------------------------------------------------------------------------
# Webhook handoff helper
# ---------------------------------------------------------------------------

def test_mark_order_paid_helper(app, buyer_client, seller_user):
    lid = _add_listing(seller_user.id, title="Paid Balm")
    _place_order(buyer_client, lid, qty=1)
    order = _orders()[0]
    with _db.session_scope() as db:
        db.get(MarketOrder, order.id).provider_checkout_ref = "cs_test_123"
    with app.app_context():
        paid = mark_order_paid("cs_test_123", "pi_test_456")
        assert paid is not None
        assert paid.status == "paid"
        assert paid.provider_payment_ref == "pi_test_456"
        assert mark_order_paid("cs_nope") is None
        assert mark_order_paid("") is None
    with _db.session_scope() as db:
        assert db.get(MarketOrder, order.id).status == "paid"


# ---------------------------------------------------------------------------
# Owner admin (/market/admin/)
# ---------------------------------------------------------------------------

def test_admin_routes_deny_non_owners(client, stranger_client):
    for path in ("/market/admin/", "/market/admin/products",
                 "/market/admin/products/new", "/market/admin/orders"):
        assert client.get(path).status_code == 302  # anon -> login
        assert stranger_client.get(path).status_code == 403
    assert stranger_client.post("/market/admin/orders/1/status",
                                data={"status": "paid"}).status_code == 403


def test_owner_admin_index(owner_client):
    body = owner_client.get("/market/admin/").get_data(as_text=True)
    assert body.startswith("<!DOCTYPE html>") or "Marketplace admin" in body
    assert "Manage products" in body and "Manage orders" in body


def test_owner_admin_product_crud(owner_client, seller_user):
    # create with every field
    resp = owner_client.post(
        "/market/admin/products/new",
        data={"title": "Admin Widget", "category": "machines",
              "description": "Owner-created.", "price": "99.99", "stock": "4",
              "status": "listed", "seller_user_id": str(seller_user.id),
              "seller_profile_id": "",
              "image": (io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32), "w.png")},
        content_type="multipart/form-data", follow_redirects=False)
    assert resp.status_code == 302
    with _db.session_scope() as db:
        listing = db.query(SupplyListing).filter_by(title="Admin Widget").one()
        assert listing.status == "listed"
        assert listing.price_cents == 9999
        assert listing.seller_user_id == seller_user.id
        assert db.get(SupplyListingDetail, listing.id).stock == 4
        lid = listing.id
    assert "Admin Widget" in owner_client.get("/market/admin/products").get_data(as_text=True)
    # edit every field, incl. status + seller reassignment
    resp = owner_client.post(
        f"/market/admin/products/{lid}/edit",
        data={"title": "Admin Widget v2", "category": "ink",
              "description": "Updated by owner.", "price": "10.00", "stock": "",
              "status": "sold", "seller_user_id": str(seller_user.id),
              "seller_profile_id": ""})
    assert resp.status_code == 302
    with _db.session_scope() as db:
        listing = db.get(SupplyListing, lid)
        assert listing.title == "Admin Widget v2"
        assert listing.category == "ink"
        assert listing.status == "sold"
        assert listing.price_cents == 1000
        assert db.get(SupplyListingDetail, lid).stock is None
    # validation: bad price rejected, nothing saved
    resp = owner_client.post(
        f"/market/admin/products/{lid}/edit",
        data={"title": "Admin Widget v2", "category": "ink",
              "description": "x", "price": "0", "stock": "",
              "status": "sold", "seller_user_id": str(seller_user.id),
              "seller_profile_id": ""})
    assert resp.status_code == 400
    # delete
    resp = owner_client.post(f"/market/admin/products/{lid}/delete",
                             follow_redirects=False)
    assert resp.status_code == 302
    with _db.session_scope() as db:
        assert db.get(SupplyListing, lid) is None
        assert db.get(SupplyListingDetail, lid) is None


def test_owner_admin_orders(owner_client, stranger_client, buyer_client,
                            seller_user):
    lid = _add_listing(seller_user.id, title="Admin Order Balm")
    _place_order(buyer_client, lid, qty=2)
    order = _orders()[0]
    body = owner_client.get("/market/admin/orders").get_data(as_text=True)
    assert f"#{order.id}" in body
    assert "buyer@test.local" in body
    body = owner_client.get(f"/market/admin/orders/{order.id}").get_data(as_text=True)
    assert "Admin Order Balm" in body
    assert "Ship to the studio." in body
    resp = owner_client.post(f"/market/admin/orders/{order.id}/status",
                             data={"status": "paid"})
    assert resp.status_code == 302
    with _db.session_scope() as db:
        assert db.get(MarketOrder, order.id).status == "paid"
    assert stranger_client.get(f"/market/admin/orders/{order.id}").status_code == 403
    assert owner_client.get("/market/admin/orders/999999").status_code == 404


def test_mark_order_paid_by_id(app, buyer_client, seller_user):
    from app.market import mark_order_paid_by_id
    lid = _add_listing(seller_user.id, title="Webhook Balm")
    _place_order(buyer_client, lid, qty=1)
    order = _orders()[0]
    with app.app_context():
        paid = mark_order_paid_by_id(order.id, "pi_test_999")
        assert paid is not None and paid.status == "paid"
        assert paid.provider_payment_ref == "pi_test_999"
        # never downgrades a fulfilled order
        paid.status = "fulfilled"
        from app.db import get_db
        get_db().commit()
        again = mark_order_paid_by_id(order.id, "pi_test_000")
        assert again.status == "fulfilled"
        assert again.provider_payment_ref == "pi_test_000"
        assert mark_order_paid_by_id(999999) is None
