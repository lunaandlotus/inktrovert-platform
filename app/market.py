"""MARKET blueprint — Phase 5: B2B supply marketplace (pros sell to pros).

Public catalog at /market/ (browse/search listed products), a seller
dashboard at /market/dashboard (create/edit/publish listings), a
session-based cart, and a checkout that creates a MarketOrder and hands
off to the payment provider via the cross-worker contract:

    from .billing import get_provider          # lazy, inside the view
    create = getattr(provider, "create_order_checkout", None)

If the provider (or its checkout URL) is missing — e.g. Stripe keys not
connected yet — checkout renders a tasteful "coming soon" page and the
order stays "pending". Checkout never crashes on missing keys.

NOTE on SupplyListing: the existing model carries seller_user_id, title,
category, description, price_cents, and status, but has no brand/supplier
profile link, stock count, or image. Those live in the companion model
SupplyListingDetail (defined below) rather than new columns on the
frozen SupplyListing table — a later consolidation onto SupplyListing
itself is a small, well-defined migration (see the integration report).

New tables (created automatically by create_all()):
    supply_listing_details, market_orders, market_order_items.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime

from flask import (Blueprint, abort, current_app, flash, g, redirect,
                   render_template, request, session as flask_session, url_for)
from sqlalchemy import (Boolean, DateTime, ForeignKey, Integer, String, Text,
                        or_, select)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.utils import secure_filename

from .auth import login_required, require_csrf, role_required
from .db import get_db
from .models import (Base, Profile, SupplyListing, User, utcnow)

market_bp = Blueprint("market", __name__, url_prefix="/market")

# aftercare / balm / needles / ink / machines / disposables / stencil / other
CATEGORIES: tuple[tuple[str, str], ...] = (
    ("aftercare", "Aftercare"),
    ("balm", "Balm & ointment"),
    ("needles", "Needles & cartridges"),
    ("ink", "Ink"),
    ("machines", "Machines & power"),
    ("disposables", "Disposables"),
    ("stencil", "Stencil & transfer"),
    ("other", "Other"),
)
CATEGORY_LABELS = dict(CATEGORIES)

ORDER_STATUSES = ("pending", "paid", "fulfilled", "canceled")

ALLOWED_IMAGE_EXTS = {"png", "jpg", "jpeg", "webp", "gif"}

CART_KEY = "market_cart"
GUEST_ORDERS_KEY = "market_orders"


# ---------------------------------------------------------------------------
# Models (new tables; SupplyListing itself is untouched)
# ---------------------------------------------------------------------------

class SupplyListingDetail(Base):
    """Companion row for a SupplyListing: stock, image, brand-profile link.

    Kept as a separate table because the existing SupplyListing model is
    frozen (other workers touch nearby files); see module docstring.
    """
    __tablename__ = "supply_listing_details"
    supply_listing_id: Mapped[int] = mapped_column(
        ForeignKey("supply_listings.id", ondelete="CASCADE"), primary_key=True)
    # Optional link to the seller's claimed brand profile.
    seller_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    # None = unlimited / made to order.
    stock: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Relative path under the uploads dir (e.g. "market/abc123.jpg").
    image: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    # Sample seed content (see ensure_sample_products): badged in the UI.
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    listing: Mapped[SupplyListing] = relationship("SupplyListing")
    seller_profile: Mapped[Profile | None] = relationship("Profile")


class MarketOrder(Base):
    """A buyer's order across one or more listings."""
    __tablename__ = "market_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    buyer_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    buyer_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    buyer_email: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    buyer_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # pending / paid / fulfilled / canceled
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False,
                                        index=True)
    provider: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    provider_checkout_ref: Mapped[str] = mapped_column(String(200), default="",
                                                       nullable=False)
    provider_payment_ref: Mapped[str] = mapped_column(String(200), default="",
                                                      nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False)

    items: Mapped[list["MarketOrderItem"]] = relationship(
        "MarketOrderItem", back_populates="order", cascade="all, delete-orphan",
        order_by="MarketOrderItem.id")
    buyer: Mapped[User | None] = relationship("User")


class MarketOrderItem(Base):
    """One line on an order: qty of a listing at a snapshotted price."""
    __tablename__ = "market_order_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("market_orders.id", ondelete="CASCADE"),
                                          nullable=False, index=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("supply_listings.id",
                                                       ondelete="SET NULL"),
                                            nullable=True, index=True)
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Snapshot of listing.price_cents at checkout time.
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    order: Mapped[MarketOrder] = relationship("MarketOrder", back_populates="items")
    listing: Mapped[SupplyListing | None] = relationship("SupplyListing")


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------

@market_bp.app_template_filter("dollars")
def _dollars(cents: int | None) -> str:
    if cents is None:
        return "—"
    return f"${cents / 100:,.2f}"


@market_bp.app_template_filter("category_label")
def _category_label(code: str | None) -> str:
    return CATEGORY_LABELS.get(code or "", code or "—")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _db():
    return get_db()


def _current_user() -> User | None:
    return g.get("user")


def get_detail(listing_id: int) -> SupplyListingDetail | None:
    return _db().get(SupplyListingDetail, listing_id)


def ensure_detail(listing: SupplyListing) -> SupplyListingDetail:
    """Fetch-or-create the companion row for a listing."""
    detail = get_detail(listing.id)
    if detail is None:
        detail = SupplyListingDetail(supply_listing_id=listing.id)
        _db().add(detail)
        _db().flush()
    return detail


def can_manage_listing(user: User | None, listing: SupplyListing) -> bool:
    return (user is not None
            and (user.has_role("platform_owner")
                 or listing.seller_user_id == user.id))


def order_seller_ids(order: MarketOrder) -> set[int]:
    """User ids of sellers with items on this order."""
    return {item.listing.seller_user_id for item in order.items if item.listing}


def can_view_order(user: User | None, order: MarketOrder) -> bool:
    if user is not None and user.has_role("platform_owner"):
        return True
    if (user is not None and order.buyer_user_id is not None
            and order.buyer_user_id == user.id):
        return True
    return order.id in (flask_session.get(GUEST_ORDERS_KEY) or [])


def can_fulfill_order(user: User | None, order: MarketOrder) -> bool:
    if user is None:
        return False
    if user.has_role("platform_owner"):
        return True
    return user.id in order_seller_ids(order)


# ---------------------------------------------------------------------------
# Owner admin — /market/admin/ (platform_owner only)
#
# The platform owner's own management pages for the marketplace, kept in
# this module so app/owner.py and templates/owner/* stay untouched.
# ---------------------------------------------------------------------------

LISTING_STATUSES = ("draft", "listed", "sold", "removed")


def _admin_product_values(listing: SupplyListing | None = None,
                          detail: SupplyListingDetail | None = None,
                          form=None) -> dict:
    if form is not None:
        return dict(form)
    if listing is None:
        return {"title": "", "category": "aftercare", "price": "", "stock": "",
                "description": "", "status": "draft", "seller_user_id": "",
                "seller_profile_id": ""}
    return {
        "title": listing.title,
        "category": listing.category,
        "price": "%.2f" % ((listing.price_cents or 0) / 100),
        "stock": "" if not detail or detail.stock is None else str(detail.stock),
        "description": listing.description,
        "status": listing.status,
        "seller_user_id": str(listing.seller_user_id),
        "seller_profile_id": "" if not detail or not detail.seller_profile_id
        else str(detail.seller_profile_id),
    }


def _save_admin_product(form, files, listing: SupplyListing | None,
                        detail: SupplyListingDetail | None) -> SupplyListingDetail:
    """Validate + apply the full admin product form. Raises ValueError
    with a plainspoken message on any problem; never half-saves."""
    title = (form.get("title") or "").strip()
    category = (form.get("category") or "").strip()
    description = (form.get("description") or "").strip()
    status = (form.get("status") or "").strip()
    price_cents = _parse_price_dollars(form.get("price", ""))
    stock = _parse_stock(form.get("stock", ""))
    seller_raw = (form.get("seller_user_id") or "").strip()
    profile_raw = (form.get("seller_profile_id") or "").strip()

    db = _db()
    seller = db.get(User, int(seller_raw)) if seller_raw.isdigit() else None
    seller_profile_id = int(profile_raw) if profile_raw.isdigit() else None
    if seller_profile_id is not None and db.get(Profile, seller_profile_id) is None:
        seller_profile_id = None

    errors = []
    if not title:
        errors.append("Give the product a title.")
    if category not in CATEGORY_LABELS:
        errors.append("Pick a category.")
    if status not in LISTING_STATUSES:
        errors.append("Pick a status.")
    if price_cents is None:
        errors.append("Enter a price above $0.")
    if seller is None:
        errors.append("Pick the seller this listing belongs to.")
    try:
        image_path = _save_product_image(files.get("image"))
    except ValueError as exc:
        errors.append(str(exc))
        image_path = ""
    if errors:
        raise ValueError(" | ".join(errors))

    if listing is None:
        listing = SupplyListing(
            seller_user_id=seller.id, title=title, category=category,
            description=description, price_cents=price_cents, status=status)
        db.add(listing)
        db.flush()
    else:
        listing.title = title
        listing.category = category
        listing.description = description
        listing.status = status
        listing.price_cents = price_cents
        listing.seller_user_id = seller.id

    if detail is None:
        detail = SupplyListingDetail(supply_listing_id=listing.id)
        db.add(detail)
    detail.seller_profile_id = seller_profile_id
    detail.stock = stock
    if image_path:
        old = detail.image
        detail.image = image_path
        if old:
            try:
                os.remove(os.path.join(current_app.config["UPLOAD_DIR"], old))
            except OSError:
                pass
    return detail


@market_bp.route("/admin/")
@role_required("platform_owner")
def admin_index():
    db = _db()
    counts = {
        "listed": db.query(SupplyListing).filter_by(status="listed").count(),
        "draft": db.query(SupplyListing).filter_by(status="draft").count(),
        "orders_pending": db.query(MarketOrder).filter_by(status="pending").count(),
        "orders_open": db.query(MarketOrder).filter(
            MarketOrder.status.in_(("pending", "paid"))).count(),
    }
    return render_template("market/admin/index.html", counts=counts)


@market_bp.route("/admin/products")
@role_required("platform_owner")
def admin_products():
    db = _db()
    status = (request.args.get("status") or "").strip()
    stmt = (select(SupplyListing)
            .order_by(SupplyListing.created_at.desc(), SupplyListing.id.desc()))
    if status in LISTING_STATUSES:
        stmt = stmt.where(SupplyListing.status == status)
    listings = list(db.execute(stmt).scalars())
    sellers = {u.id: u for u in db.query(User).all()}
    details = {}
    if listings:
        details = {d.supply_listing_id: d for d in db.execute(
            select(SupplyListingDetail).where(
                SupplyListingDetail.supply_listing_id.in_(
                    [l.id for l in listings]))).scalars()}
    return render_template("market/admin/products.html", listings=listings,
                           sellers=sellers, details=details, status=status,
                           statuses=LISTING_STATUSES,
                           category_labels=CATEGORY_LABELS)


@market_bp.route("/admin/products/new", methods=["GET", "POST"])
@role_required("platform_owner")
@require_csrf
def admin_product_new():
    db = _db()
    users = db.query(User).order_by(User.email).all()
    brands = db.query(Profile).filter_by(kind="brand").order_by(
        Profile.display_name).all()
    if request.method == "POST":
        try:
            _save_admin_product(request.form, request.files, None, None)
            db.commit()
        except ValueError as exc:
            for err in str(exc).split(" | "):
                flash(err, "error")
            return render_template(
                "market/admin/product_form.html", mode="new",
                values=_admin_product_values(form=request.form),
                users=users, brands=brands, categories=CATEGORIES,
                statuses=LISTING_STATUSES), 400
        flash("Product saved.", "success")
        return redirect(url_for("market.admin_products"))
    return render_template("market/admin/product_form.html", mode="new",
                           values=_admin_product_values(), users=users,
                           brands=brands, categories=CATEGORIES,
                           statuses=LISTING_STATUSES)


@market_bp.route("/admin/products/<int:listing_id>/edit", methods=["GET", "POST"])
@role_required("platform_owner")
@require_csrf
def admin_product_edit(listing_id: int):
    db = _db()
    listing = db.get(SupplyListing, listing_id)
    if listing is None:
        abort(404)
    detail = ensure_detail(listing)
    users = db.query(User).order_by(User.email).all()
    brands = db.query(Profile).filter_by(kind="brand").order_by(
        Profile.display_name).all()
    if request.method == "POST":
        try:
            _save_admin_product(request.form, request.files, listing, detail)
            db.commit()
        except ValueError as exc:
            for err in str(exc).split(" | "):
                flash(err, "error")
            return render_template(
                "market/admin/product_form.html", mode="edit", listing=listing,
                detail=detail, values=_admin_product_values(form=request.form),
                users=users, brands=brands, categories=CATEGORIES,
                statuses=LISTING_STATUSES), 400
        flash("Product updated.", "success")
        return redirect(url_for("market.admin_products"))
    return render_template("market/admin/product_form.html", mode="edit",
                           listing=listing, detail=detail,
                           values=_admin_product_values(listing, detail),
                           users=users, brands=brands, categories=CATEGORIES,
                           statuses=LISTING_STATUSES)


@market_bp.route("/admin/products/<int:listing_id>/delete", methods=["POST"])
@role_required("platform_owner")
@require_csrf
def admin_product_delete(listing_id: int):
    db = _db()
    listing = db.get(SupplyListing, listing_id)
    if listing is None:
        abort(404)
    title = listing.title
    # Companion row cascades; order items keep their snapshots with the
    # listing link nulled (ondelete=SET NULL).
    db.query(SupplyListingDetail).filter_by(
        supply_listing_id=listing.id).delete()
    db.delete(listing)
    db.commit()
    flash(f"“{title}” deleted.", "success")
    return redirect(url_for("market.admin_products"))


@market_bp.route("/admin/orders")
@role_required("platform_owner")
def admin_orders():
    db = _db()
    status = (request.args.get("status") or "").strip()
    stmt = (select(MarketOrder)
            .order_by(MarketOrder.created_at.desc(), MarketOrder.id.desc()))
    if status in ORDER_STATUSES:
        stmt = stmt.where(MarketOrder.status == status)
    orders = list(db.execute(stmt).scalars())
    return render_template("market/admin/orders.html", orders=orders,
                           status=status, statuses=ORDER_STATUSES)


@market_bp.route("/admin/orders/<int:order_id>")
@role_required("platform_owner")
def admin_order_detail(order_id: int):
    order = _db().get(MarketOrder, order_id)
    if order is None:
        abort(404)
    return render_template("market/admin/order_detail.html", order=order,
                           statuses=ORDER_STATUSES)


@market_bp.route("/admin/orders/<int:order_id>/status", methods=["POST"])
@role_required("platform_owner")
@require_csrf
def admin_order_status(order_id: int):
    db = _db()
    order = db.get(MarketOrder, order_id)
    if order is None:
        abort(404)
    status = (request.form.get("status") or "").strip()
    if status not in ORDER_STATUSES:
        abort(400)
    order.status = status
    db.commit()
    flash(f"Order #{order.id} set to {status}.", "success")
    return redirect(url_for("market.admin_order_detail", order_id=order.id))


def mark_order_paid(checkout_ref: str, payment_ref: str = "") -> MarketOrder | None:
    """Webhook handoff for the billing worker.

    When Stripe keys land, the billing webhook should call this on
    checkout.session.completed: it finds the order by the checkout
    session id stored at checkout time and moves it pending -> paid.
    Returns the order, or None if no order carries that checkout ref.
    """
    if not checkout_ref:
        return None
    db = get_db()
    order = db.execute(
        select(MarketOrder).where(
            MarketOrder.provider_checkout_ref == checkout_ref)
    ).scalar_one_or_none()
    if order is None:
        return None
    if order.status == "pending":
        order.status = "paid"
    if payment_ref:
        order.provider_payment_ref = payment_ref
    db.commit()
    return order


def mark_order_paid_by_id(order_id: int, payment_ref: str = "") -> MarketOrder | None:
    """Mark a marketplace order paid by its id (for the billing webhook's
    order.completed branch — see the integration report). Only moves
    pending -> paid; never touches fulfilled/canceled orders."""
    db = get_db()
    order = db.get(MarketOrder, order_id)
    if order is None:
        return None
    if order.status == "pending":
        order.status = "paid"
    if payment_ref:
        order.provider_payment_ref = payment_ref
    db.commit()
    return order


def _cart() -> dict[str, int]:
    raw = flask_session.get(CART_KEY) or {}
    return {str(k): int(v) for k, v in raw.items() if int(v) > 0}


def _save_cart(cart: dict[str, int]) -> None:
    flask_session[CART_KEY] = {str(k): int(v) for k, v in cart.items() if int(v) > 0}
    flask_session.modified = True


def _cart_lines(cart: dict[str, int]):
    """Resolve cart ids to (listing, detail, qty), dropping dead listings."""
    db = _db()
    lines = []
    changed = False
    for lid, qty in list(cart.items()):
        listing = db.get(SupplyListing, int(lid))
        if listing is None or listing.status != "listed":
            del cart[lid]
            changed = True
            continue
        detail = get_detail(listing.id)
        stock = detail.stock if detail else None
        if stock is not None and stock <= 0:
            del cart[lid]
            changed = True
            continue
        if stock is not None and qty > stock:
            cart[lid] = stock
            qty = stock
            changed = True
        lines.append((listing, detail, qty))
    if changed:
        _save_cart(cart)
    return lines


def _cart_total_cents(lines) -> int:
    return sum((l.price_cents or 0) * qty for l, _d, qty in lines)


def _save_product_image(file_storage) -> str:
    """Store an uploaded product image under UPLOAD_DIR/market/.

    Returns the relative path (served by /uploads/<path>), or "" when no
    file was uploaded. Raises ValueError on bad type / oversize.
    """
    if file_storage is None or not getattr(file_storage, "filename", ""):
        return ""
    filename = secure_filename(file_storage.filename)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_IMAGE_EXTS:
        raise ValueError("Image must be a PNG, JPG, WEBP, or GIF file.")
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    max_bytes = current_app.config["MAX_UPLOAD_MB"] * 1024 * 1024
    if size > max_bytes:
        raise ValueError(f"Image is too large (limit "
                         f"{current_app.config['MAX_UPLOAD_MB']} MB).")
    name = f"{uuid.uuid4().hex}.{ext}"
    dest_dir = os.path.join(current_app.config["UPLOAD_DIR"], "market")
    os.makedirs(dest_dir, exist_ok=True)
    file_storage.save(os.path.join(dest_dir, name))
    return f"market/{name}"


def _parse_price_dollars(raw: str) -> int | None:
    try:
        value = float((raw or "").strip().replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return int(round(value * 100))


def _parse_stock(raw: str) -> int | None:
    raw = (raw or "").strip()
    if raw == "":
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return max(value, 0)


def ensure_sample_products() -> None:
    """Idempotent seed: a handful of realistic listings so the marketplace
    isn't empty. Runs under the platform owner account (falls back to the
    first user); exits quietly when any listed product already exists."""
    db = _db()
    listed = db.execute(
        select(SupplyListing.id).where(SupplyListing.status == "listed").limit(1)
    ).first()
    if listed is not None:
        return
    # roles is a relationship; query users joined to the platform_owner role.
    from .models import Role
    owner_role = db.execute(
        select(Role).where(Role.name == "platform_owner")).scalar_one_or_none()
    seller = None
    if owner_role is not None:
        seller = db.execute(
            select(User).join(User.roles).where(Role.id == owner_role.id)
            .order_by(User.id).limit(1)).scalar_one_or_none()
    if seller is None:
        seller = db.execute(select(User).order_by(User.id).limit(1)
                            ).scalar_one_or_none()
    if seller is None:
        return  # no users yet — nothing to attribute samples to

    samples = [
        ("aftercare", "Tattoo Aftercare Balm — 2 oz tin", 1800, 40,
         "All-natural balm for fresh tattoos: shea, coconut oil, and vitamin E. "
         "A studio staple for aftercare kits."),
        ("needles", "Pro Needle Cartridges — 20 pack, 3RL", 2400, 120,
         "Sterile single-use membrane cartridges, 3 round liner. EO gas "
         "sterilized, individually blister-packed."),
        ("ink", "True Black Tattoo Ink — 8 oz bottle", 1600, 60,
         "Rich, consistent black for lining and solid fill. Vegan, "
         "sterile, and batch-tested."),
        ("disposables", "Disposable Grip Covers — 100 pack", 1200, 200,
         "Single-use barrier covers for standard grips. Keeps setups clean "
         "and cross-contamination-free."),
        ("stencil", "Stencil Transfer Paper — 25 sheets", 950, 150,
         "Crisp, long-lasting thermal transfer sheets. Works with standard "
         "thermal copiers and freehand."),
        ("machines", "Rotary Machine — Studio Pro", 18900, 8,
         "Direct-drive rotary workhorse: quiet, balanced, and easy to "
         "maintain. RCA connection."),
        ("aftercare", "Piercing Aftercare Saline Spray — 4 oz", 1000, 75,
         "Sterile isotonic saline mist for healing piercings. Drug-free, "
         "no burning, no residue."),
        ("balm", "Piercing Bump Balm — 0.5 oz", 1400, 50,
         "Gentle daily balm for irritated piercings. Tea tree and chamomile; "
         "a little goes a long way."),
    ]
    for category, title, price_cents, stock, description in samples:
        listing = SupplyListing(
            seller_user_id=seller.id, title=title, category=category,
            description=description + " (Sample listing.)",
            price_cents=price_cents, status="listed")
        db.add(listing)
        db.flush()
        db.add(SupplyListingDetail(
            supply_listing_id=listing.id, stock=stock, is_sample=True))
    db.commit()


# ---------------------------------------------------------------------------
# Catalog (public)
# ---------------------------------------------------------------------------

@market_bp.route("/")
def index():
    ensure_sample_products()
    db = _db()
    q = (request.args.get("q") or "").strip()
    category = (request.args.get("category") or "").strip()

    stmt = (select(SupplyListing)
            .where(SupplyListing.status == "listed")
            .order_by(SupplyListing.created_at.desc(), SupplyListing.id.desc()))
    if category in CATEGORY_LABELS:
        stmt = stmt.where(SupplyListing.category == category)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(SupplyListing.title.ilike(like),
                              SupplyListing.description.ilike(like)))
    listings = list(db.execute(stmt).scalars())
    details = {}
    if listings:
        details = {d.supply_listing_id: d for d in db.execute(
            select(SupplyListingDetail).where(
                SupplyListingDetail.supply_listing_id.in_(
                    [l.id for l in listings]))).scalars()}
    has_samples = any(d.is_sample for d in details.values())
    return render_template("market/index.html", listings=listings,
                           details=details, q=q, category=category,
                           categories=CATEGORIES, has_samples=has_samples,
                           category_labels=CATEGORY_LABELS)


@market_bp.route("/p/<int:listing_id>")
def product_detail(listing_id: int):
    db = _db()
    listing = db.get(SupplyListing, listing_id)
    if listing is None or listing.status != "listed":
        abort(404)
    detail = get_detail(listing.id)
    seller = db.get(User, listing.seller_user_id)
    brand = (db.get(Profile, detail.seller_profile_id)
             if detail and detail.seller_profile_id else None)
    return render_template("market/detail.html", listing=listing,
                           detail=detail, seller=seller, brand=brand,
                           category_labels=CATEGORY_LABELS)


# ---------------------------------------------------------------------------
# Seller dashboard
# ---------------------------------------------------------------------------

def _seller_brand_profiles(user: User):
    return list(_db().execute(
        select(Profile).where(Profile.kind == "brand",
                              Profile.claimed_by_user_id == user.id)
        .order_by(Profile.display_name)).scalars())


def _get_managed_listing(listing_id: int) -> SupplyListing:
    listing = _db().get(SupplyListing, listing_id)
    if listing is None:
        abort(404)
    if not can_manage_listing(_current_user(), listing):
        abort(403)
    return listing


@market_bp.route("/dashboard")
@login_required
def dashboard():
    user = _current_user()
    db = _db()
    listings = list(db.execute(
        select(SupplyListing)
        .where(SupplyListing.seller_user_id == user.id)
        .order_by(SupplyListing.created_at.desc(), SupplyListing.id.desc())
    ).scalars())
    details = {}
    if listings:
        details = {d.supply_listing_id: d for d in db.execute(
            select(SupplyListingDetail).where(
                SupplyListingDetail.supply_listing_id.in_(
                    [l.id for l in listings]))).scalars()}
    return render_template("market/dashboard.html", listings=listings,
                           details=details, category_labels=CATEGORY_LABELS)


@market_bp.route("/dashboard/new", methods=["GET", "POST"])
@login_required
@require_csrf
def listing_new():
    user = _current_user()
    brands = _seller_brand_profiles(user)
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        category = (request.form.get("category") or "").strip()
        description = (request.form.get("description") or "").strip()
        price_cents = _parse_price_dollars(request.form.get("price", ""))
        stock = _parse_stock(request.form.get("stock", ""))
        profile_raw = (request.form.get("seller_profile_id") or "").strip()
        seller_profile_id = int(profile_raw) if profile_raw.isdigit() else None
        if seller_profile_id is not None and not any(
                p.id == seller_profile_id for p in brands):
            seller_profile_id = None

        errors = []
        if not title:
            errors.append("Give your product a title.")
        if category not in CATEGORY_LABELS:
            errors.append("Pick a category.")
        if price_cents is None:
            errors.append("Enter a price above $0.")
        try:
            image_path = _save_product_image(request.files.get("image"))
        except ValueError as exc:
            errors.append(str(exc))
            image_path = ""

        if errors:
            for err in errors:
                flash(err, "error")
            return render_template(
                "market/listing_form.html", mode="new", brands=brands,
                categories=CATEGORIES, values=dict(request.form)), 400

        db = _db()
        listing = SupplyListing(
            seller_user_id=user.id, title=title, category=category,
            description=description, price_cents=price_cents, status="draft")
        db.add(listing)
        db.flush()
        db.add(SupplyListingDetail(
            supply_listing_id=listing.id, seller_profile_id=seller_profile_id,
            stock=stock, image=image_path))
        db.commit()
        flash("Listing saved as a draft. Publish it when it's ready.", "success")
        return redirect(url_for("market.dashboard"))
    return render_template("market/listing_form.html", mode="new",
                           brands=brands, categories=CATEGORIES,
                           values={"title": "", "category": "aftercare",
                                   "price": "", "stock": "", "description": "",
                                   "seller_profile_id": ""})


@market_bp.route("/dashboard/<int:listing_id>/edit", methods=["GET", "POST"])
@login_required
@require_csrf
def listing_edit(listing_id: int):
    user = _current_user()
    listing = _get_managed_listing(listing_id)
    detail = ensure_detail(listing)
    brands = _seller_brand_profiles(user)
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        category = (request.form.get("category") or "").strip()
        description = (request.form.get("description") or "").strip()
        price_cents = _parse_price_dollars(request.form.get("price", ""))
        stock = _parse_stock(request.form.get("stock", ""))
        profile_raw = (request.form.get("seller_profile_id") or "").strip()
        seller_profile_id = int(profile_raw) if profile_raw.isdigit() else None
        if seller_profile_id is not None and not any(
                p.id == seller_profile_id for p in brands):
            seller_profile_id = detail.seller_profile_id

        errors = []
        if not title:
            errors.append("Give your product a title.")
        if category not in CATEGORY_LABELS:
            errors.append("Pick a category.")
        if price_cents is None:
            errors.append("Enter a price above $0.")
        try:
            image_path = _save_product_image(request.files.get("image"))
        except ValueError as exc:
            errors.append(str(exc))
            image_path = ""

        if errors:
            for err in errors:
                flash(err, "error")
            return render_template(
                "market/listing_form.html", mode="edit", listing=listing,
                detail=detail, brands=brands, categories=CATEGORIES,
                values=dict(request.form)), 400

        listing.title = title
        listing.category = category
        listing.description = description
        listing.price_cents = price_cents
        detail.seller_profile_id = seller_profile_id
        detail.stock = stock
        if image_path:
            old = detail.image
            detail.image = image_path
            if old:
                try:
                    os.remove(os.path.join(
                        current_app.config["UPLOAD_DIR"], old))
                except OSError:
                    pass
        _db().commit()
        flash("Listing updated.", "success")
        return redirect(url_for("market.dashboard"))
    values = {
        "title": listing.title,
        "category": listing.category,
        "price": "%.2f" % ((listing.price_cents or 0) / 100),
        "stock": "" if detail.stock is None else str(detail.stock),
        "description": listing.description,
        "seller_profile_id": "" if not detail.seller_profile_id
        else str(detail.seller_profile_id),
    }
    return render_template("market/listing_form.html", mode="edit",
                           listing=listing, detail=detail, brands=brands,
                           categories=CATEGORIES, values=values)


_STATUS_ACTIONS = {
    "publish": ("draft", "listed", "Listing published — it's live in the marketplace."),
    "unpublish": ("listed", "draft", "Listing unpublished — back to draft."),
    "sold": ("listed", "sold", "Listing marked as sold."),
    "remove": (None, "removed", "Listing removed."),
    "relist": ("removed", "listed", "Listing is live again."),
}


@market_bp.route("/dashboard/<int:listing_id>/status", methods=["POST"])
@login_required
@require_csrf
def listing_status(listing_id: int):
    listing = _get_managed_listing(listing_id)
    action = (request.form.get("action") or "").strip()
    rule = _STATUS_ACTIONS.get(action)
    if rule is None:
        abort(400)
    from_status, to_status, message = rule
    if from_status is not None and listing.status != from_status:
        flash("That action doesn't apply to this listing right now.", "error")
        return redirect(url_for("market.dashboard"))
    listing.status = to_status
    _db().commit()
    flash(message, "success")
    return redirect(url_for("market.dashboard"))


@market_bp.route("/dashboard/orders")
@login_required
def seller_orders():
    user = _current_user()
    db = _db()
    # Orders (not canceled) containing at least one of this seller's listings.
    orders = list(db.execute(
        select(MarketOrder)
        .join(MarketOrderItem, MarketOrderItem.order_id == MarketOrder.id)
        .join(SupplyListing, SupplyListing.id == MarketOrderItem.listing_id)
        .where(SupplyListing.seller_user_id == user.id,
               MarketOrder.status != "canceled")
        .order_by(MarketOrder.created_at.desc(), MarketOrder.id.desc())
        .distinct()).scalars())
    return render_template("market/seller_orders.html", orders=orders,
                           user_id=user.id)


@market_bp.route("/dashboard/orders/<int:order_id>/fulfill", methods=["POST"])
@login_required
@require_csrf
def fulfill_order(order_id: int):
    user = _current_user()
    order = _db().get(MarketOrder, order_id)
    if order is None:
        abort(404)
    if not can_fulfill_order(user, order):
        abort(403)
    if order.status not in ("pending", "paid"):
        flash("This order can't be fulfilled in its current state.", "error")
        return redirect(url_for("market.seller_orders"))
    db = _db()
    for item in order.items:
        listing = item.listing
        if listing is None:
            continue
        if listing.seller_user_id != user.id and not user.has_role("platform_owner"):
            continue
        detail = get_detail(listing.id)
        if detail and detail.stock is not None:
            detail.stock = max(detail.stock - item.qty, 0)
    order.status = "fulfilled"
    db.commit()
    flash(f"Order #{order.id} marked as fulfilled.", "success")
    return redirect(url_for("market.seller_orders"))


# ---------------------------------------------------------------------------
# Cart (session-based)
# ---------------------------------------------------------------------------

@market_bp.route("/cart/add/<int:listing_id>", methods=["POST"])
@require_csrf
def cart_add(listing_id: int):
    listing = _db().get(SupplyListing, listing_id)
    if listing is None or listing.status != "listed":
        abort(404)
    detail = get_detail(listing.id)
    stock = detail.stock if detail else None
    if stock is not None and stock <= 0:
        flash("Sorry — that product is out of stock.", "error")
        return redirect(url_for("market.product_detail", listing_id=listing.id))
    try:
        qty = max(int(request.form.get("qty", "1")), 1)
    except (TypeError, ValueError):
        qty = 1
    qty = min(qty, 99)
    if stock is not None and qty > stock:
        qty = stock
        flash(f"Only {stock} in stock — cart updated to what's available.", "info")
    cart = _cart()
    cart[str(listing.id)] = min(cart.get(str(listing.id), 0) + qty,
                                stock if stock is not None else 99)
    _save_cart(cart)
    flash(f"Added “{listing.title}” to your cart.", "success")
    return redirect(request.form.get("next") or url_for("market.cart_view"))


@market_bp.route("/cart")
def cart_view():
    cart = _cart()
    lines = _cart_lines(cart)
    return render_template("market/cart.html", lines=lines,
                           total_cents=_cart_total_cents(lines))


@market_bp.route("/cart/remove/<int:listing_id>", methods=["POST"])
@require_csrf
def cart_remove(listing_id: int):
    cart = _cart()
    cart.pop(str(listing_id), None)
    _save_cart(cart)
    return redirect(url_for("market.cart_view"))


@market_bp.route("/cart/clear", methods=["POST"])
@require_csrf
def cart_clear():
    _save_cart({})
    return redirect(url_for("market.cart_view"))


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------

@market_bp.route("/checkout", methods=["GET", "POST"])
@require_csrf
def checkout():
    user = _current_user()
    cart = _cart()
    lines = _cart_lines(cart)
    if not lines:
        flash("Your cart is empty.", "info")
        return redirect(url_for("market.index"))

    if request.method == "POST":
        buyer_name = (request.form.get("buyer_name")
                      or (user.full_name if user else "") or "").strip()
        buyer_email = (request.form.get("buyer_email")
                       or (user.email if user else "") or "").strip()
        buyer_note = (request.form.get("buyer_note") or "").strip()
        if not buyer_name or "@" not in buyer_email:
            flash("Add your name and a valid email so the seller can reach you.",
                  "error")
            return render_template("market/checkout.html", lines=lines,
                                   total_cents=_cart_total_cents(lines),
                                   form=request.form), 400

        db = _db()
        order = MarketOrder(
            buyer_user_id=user.id if user else None,
            buyer_name=buyer_name, buyer_email=buyer_email,
            buyer_note=buyer_note,
            total_cents=_cart_total_cents(lines), status="pending")
        db.add(order)
        db.flush()
        for listing, _detail, qty in lines:
            db.add(MarketOrderItem(order_id=order.id, listing_id=listing.id,
                                   qty=qty, price_cents=listing.price_cents or 0))
        db.commit()
        _save_cart({})
        guest_orders = flask_session.get(GUEST_ORDERS_KEY) or []
        guest_orders.append(order.id)
        flask_session[GUEST_ORDERS_KEY] = guest_orders

        # Hand off to the payment provider (cross-worker contract).
        # Missing provider / missing keys / missing checkout URL all fall
        # through to the honest "coming soon" page — never a crash.
        provider = None
        try:
            from .billing import get_provider  # lazy: avoid import-order issues
            provider = get_provider()
        except Exception:
            provider = None
        create = getattr(provider, "create_order_checkout", None) \
            if provider is not None else None
        checkout_session = None
        if callable(create):
            try:
                checkout_session = create(
                    user_id=user.id if user else None,
                    order_id=order.id,
                    amount_cents=order.total_cents,
                    success_url=url_for("market.order_success", order_id=order.id,
                                        _external=True),
                    cancel_url=url_for("market.checkout", _external=True),
                )
            except Exception:
                checkout_session = None
        checkout_url = (getattr(checkout_session, "url", "") or "").strip()
        if checkout_url:
            order.provider = (getattr(provider, "name", "") or "stripe")[:40]
            order.provider_checkout_ref = (
                getattr(checkout_session, "provider_ref", "") or "")[:200]
            db.commit()
            return redirect(checkout_url)
        return render_template("market/coming_soon.html", order=order)

    return render_template("market/checkout.html", lines=lines,
                           total_cents=_cart_total_cents(lines), form=None)


@market_bp.route("/order/<int:order_id>/success")
def order_success(order_id: int):
    order = _db().get(MarketOrder, order_id)
    if order is None or not can_view_order(_current_user(), order):
        abort(404)
    return render_template("market/order_success.html", order=order)


# ---------------------------------------------------------------------------
# Buyer order views
# ---------------------------------------------------------------------------

@market_bp.route("/orders")
def buyer_orders():
    user = _current_user()
    db = _db()
    orders = []
    if user is not None:
        orders = list(db.execute(
            select(MarketOrder)
            .where(MarketOrder.buyer_user_id == user.id)
            .order_by(MarketOrder.created_at.desc(),
                      MarketOrder.id.desc())).scalars())
    guest_ids = flask_session.get(GUEST_ORDERS_KEY) or []
    if guest_ids:
        guests = list(db.execute(
            select(MarketOrder).where(MarketOrder.id.in_(guest_ids))).scalars())
        seen = {o.id for o in orders}
        orders.extend(o for o in guests if o.id not in seen)
        orders.sort(key=lambda o: (o.created_at, o.id), reverse=True)
    return render_template("market/orders.html", orders=orders)


@market_bp.route("/orders/<int:order_id>")
def order_detail(order_id: int):
    order = _db().get(MarketOrder, order_id)
    if order is None or not can_view_order(_current_user(), order):
        abort(404)
    return render_template("market/order_detail.html", order=order)


@market_bp.route("/orders/<int:order_id>/cancel", methods=["POST"])
@require_csrf
def order_cancel(order_id: int):
    user = _current_user()
    order = _db().get(MarketOrder, order_id)
    if order is None or not can_view_order(user, order):
        abort(404)
    # Only the buyer (or platform owner) may cancel — a seller viewing the
    # order through their dashboard must not cancel someone else's order.
    is_buyer = (user is not None and user.has_role("platform_owner")) or (
        user is not None and order.buyer_user_id is not None
        and order.buyer_user_id == user.id) or (
            order.buyer_user_id is None and order.id in (
                flask_session.get(GUEST_ORDERS_KEY) or []))
    if not is_buyer:
        abort(403)
    if order.status != "pending":
        flash("Only pending orders can be canceled.", "error")
        return redirect(url_for("market.order_detail", order_id=order.id))
    order.status = "canceled"
    _db().commit()
    flash(f"Order #{order.id} canceled.", "success")
    return redirect(url_for("market.buyer_orders"))
