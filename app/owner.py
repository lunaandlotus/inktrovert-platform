"""Platform-owner dashboard — the publishing desk for Inktrovert.

Every route here is owner-only (@role_required("platform_owner")): leads
inbox review, story/issue/newsletter editing, event and claim approvals,
podcast series + episode management, and a read-only look at the funding
stubs (support tiers / fundraising campaigns — no money moves yet).
"""
from __future__ import annotations

import re

from flask import (Blueprint, flash, g, redirect, render_template, request,
                   url_for)

from . import leads
from .auth import require_csrf, role_required
from .db import get_db
from .models import (BOOK_AUDIENCES, BOOK_CRAFTS, BOOK_KINDS, LEAD_STATUSES,
                     STORY_CATEGORIES, Book, ClaimRequest, Event,
                     FundraisingCampaign, Issue, NewsletterEdition,
                     PodcastEpisode, PodcastSeries, Profile, Review, Story,
                     StoryLead, SubscriptionTier, utcnow)

owner_bp = Blueprint("owner", __name__, url_prefix="/owner")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _slugify(text: str, maxlen: int = 200) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").casefold()).strip("-")[:maxlen]
    return slug or "item"


def _unique_slug(model, base: str, exclude_id: int | None = None) -> str:
    slug, n = base, 2
    while True:
        q = get_db().query(model).filter_by(slug=slug)
        if exclude_id is not None:
            q = q.filter(model.id != exclude_id)
        if q.one_or_none() is None:
            return slug
        slug = f"{base}-{n}"
        n += 1


def _is_checked(form, name: str) -> bool:
    return name in form


def _parse_int(value: str | None, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _set_published(obj, published: bool) -> None:
    """Flip is_published; stamp published_at on publish, clear on unpublish."""
    obj.is_published = published
    if published and obj.published_at is None:
        obj.published_at = utcnow()
    elif not published:
        obj.published_at = None


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@owner_bp.route("/")
@role_required("platform_owner")
def dashboard():
    db = get_db()
    lead_counts = leads.inbox_counts(db)
    pending_claims = db.query(ClaimRequest).filter_by(status="pending").count()
    pending_events = db.query(Event).filter_by(status="pending").count()
    published_stories = db.query(Story).filter_by(is_published=True).count()
    draft_stories = db.query(Story).filter_by(is_published=False).count()
    issue_count = db.query(Issue).count()
    episode_count = db.query(PodcastEpisode).count()
    book_count = db.query(Book).count()
    pending_reviews = db.query(Review).filter_by(status="pending").count()

    new_leads = (db.query(StoryLead).filter_by(status="new")
                 .order_by(StoryLead.found_date.desc()).limit(5).all())
    pending_claim_list = (db.query(ClaimRequest).filter_by(status="pending")
                          .order_by(ClaimRequest.created_at.desc()).limit(5).all())
    pending_event_list = (db.query(Event).filter_by(status="pending")
                          .order_by(Event.created_at.desc()).limit(5).all())

    return render_template(
        "owner/dashboard.html",
        lead_counts=lead_counts,
        lead_statuses=LEAD_STATUSES,
        pending_claims=pending_claims,
        pending_events=pending_events,
        published_stories=published_stories,
        draft_stories=draft_stories,
        issue_count=issue_count,
        episode_count=episode_count,
        book_count=book_count,
        new_leads=new_leads,
        pending_claim_list=pending_claim_list,
        pending_event_list=pending_event_list,
        pending_reviews=pending_reviews,
    )


# ---------------------------------------------------------------------------
# Story leads inbox
# ---------------------------------------------------------------------------

# Function is named leads_inbox to keep the `leads` module name free;
# the explicit endpoint keeps the contract's exact name: owner.leads.
@owner_bp.route("/leads", endpoint="leads")
@role_required("platform_owner")
def leads_inbox():
    db = get_db()
    status = request.args.get("status", "new")
    if status not in LEAD_STATUSES:
        status = "new"
    lead_rows = (db.query(StoryLead).filter_by(status=status)
                 .order_by(StoryLead.found_date.desc()).all())
    return render_template(
        "owner/leads.html",
        status=status,
        lead_statuses=LEAD_STATUSES,
        lead_counts=leads.inbox_counts(db),
        lead_rows=lead_rows,
    )


@owner_bp.route("/leads/<int:lead_id>", methods=["GET", "POST"])
@role_required("platform_owner")
@require_csrf
def lead_detail(lead_id: int):
    db = get_db()
    lead = db.get(StoryLead, lead_id)
    if lead is None:
        flash("That lead is gone.", "error")
        return redirect(url_for("owner.leads"))

    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "reviewing":
            leads.set_lead_status(db, lead, "reviewing")
            flash("Marked as reviewing.", "success")
        elif action == "discard":
            note = request.form.get("note", "").strip()
            leads.discard_lead(db, lead, note=note)
            flash("Lead discarded.", "success")
        elif action == "promote":
            category = request.form.get("category", "news")
            if category not in STORY_CATEGORIES:
                category = "news"
            author_name = request.form.get("author_name", "").strip()
            try:
                story = leads.promote_lead(db, lead, category=category,
                                           author_name=author_name)
            except ValueError as exc:
                flash(str(exc), "error")
                return redirect(url_for("owner.lead_detail", lead_id=lead.id))
            flash("Promoted to a draft story.", "success")
            return redirect(url_for("owner.story_edit", story_id=story.id))
        else:
            flash("Unknown action.", "error")
        return redirect(url_for("owner.lead_detail", lead_id=lead.id))

    return render_template(
        "owner/lead_detail.html",
        lead=lead,
        categories=STORY_CATEGORIES,
        default_author=g.user.full_name if g.user else "",
    )


# ---------------------------------------------------------------------------
# Stories
# ---------------------------------------------------------------------------

@owner_bp.route("/stories")
@role_required("platform_owner")
def stories():
    db = get_db()
    story_rows = (db.query(Story).order_by(Story.created_at.desc()).all())
    return render_template("owner/stories.html", story_rows=story_rows)


def _story_form_common(form, story: Story) -> str | None:
    """Apply form fields to a story. Returns an error message, or None."""
    title = (form.get("title") or "").strip()
    if not title:
        return "A title is required."
    story.title = title
    category = form.get("category", "news")
    story.category = category if category in STORY_CATEGORIES else "news"
    story.excerpt = (form.get("excerpt") or "").strip()
    story.body = form.get("body", "")
    story.author_name = (form.get("author_name") or "").strip()
    issue_id = _parse_int(form.get("issue_id"), None)
    story.issue_id = issue_id if issue_id else None
    slug_in = (form.get("slug") or "").strip()
    story.slug = _unique_slug(Story, _slugify(slug_in or title), exclude_id=story.id or None)
    _set_published(story, _is_checked(form, "is_published"))
    return None


@owner_bp.route("/stories/new", methods=["GET", "POST"])
@role_required("platform_owner")
@require_csrf
def story_new():
    db = get_db()
    story = Story()
    if request.method == "POST":
        error = _story_form_common(request.form, story)
        if error:
            flash(error, "error")
        else:
            db.add(story)
            db.commit()
            flash("Story saved.", "success")
            return redirect(url_for("owner.story_edit", story_id=story.id))
    issues = db.query(Issue).order_by(Issue.number.desc()).all()
    return render_template(
        "owner/story_form.html", story=story, is_new=True,
        categories=STORY_CATEGORIES, issues=issues,
        suggested_slug=_slugify(request.form.get("title", "")) if request.method == "POST" else "",
    )


@owner_bp.route("/stories/<int:story_id>/edit", methods=["GET", "POST"])
@role_required("platform_owner")
@require_csrf
def story_edit(story_id: int):
    db = get_db()
    story = db.get(Story, story_id)
    if story is None:
        flash("That story is gone.", "error")
        return redirect(url_for("owner.stories"))
    if request.method == "POST":
        error = _story_form_common(request.form, story)
        if error:
            flash(error, "error")
        else:
            db.commit()
            flash("Story saved.", "success")
            return redirect(url_for("owner.story_edit", story_id=story.id))
    issues = db.query(Issue).order_by(Issue.number.desc()).all()
    return render_template(
        "owner/story_form.html", story=story, is_new=False,
        categories=STORY_CATEGORIES, issues=issues, suggested_slug="",
    )


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------

@owner_bp.route("/issues")
@role_required("platform_owner")
def issues():
    db = get_db()
    issue_rows = db.query(Issue).order_by(Issue.number.desc()).all()
    return render_template("owner/issues.html", issue_rows=issue_rows)


def _issue_form_common(form, issue: Issue) -> str | None:
    number = _parse_int(form.get("number"), None)
    if number is None:
        return "Issue number must be a number."
    db = get_db()
    dup = db.query(Issue).filter_by(number=number)
    if issue.id:
        dup = dup.filter(Issue.id != issue.id)
    if dup.one_or_none() is not None:
        return f"Issue number {number} is already taken."
    issue.number = number
    title = (form.get("title") or "").strip()
    if not title:
        return "A title is required."
    issue.title = title
    slug_in = (form.get("slug") or "").strip()
    issue.slug = _unique_slug(Issue, _slugify(slug_in or title), exclude_id=issue.id or None)
    issue.blurb = (form.get("blurb") or "").strip()
    _set_published(issue, _is_checked(form, "is_published"))
    return None


@owner_bp.route("/issues/new", methods=["GET", "POST"])
@role_required("platform_owner")
@require_csrf
def issue_new():
    db = get_db()
    issue = Issue()
    if request.method == "POST":
        error = _issue_form_common(request.form, issue)
        if error:
            flash(error, "error")
        else:
            db.add(issue)
            db.commit()
            flash("Issue saved.", "success")
            return redirect(url_for("owner.issue_edit", issue_id=issue.id))
    return render_template("owner/issue_form.html", issue=issue, is_new=True)


@owner_bp.route("/issues/<int:issue_id>/edit", methods=["GET", "POST"])
@role_required("platform_owner")
@require_csrf
def issue_edit(issue_id: int):
    db = get_db()
    issue = db.get(Issue, issue_id)
    if issue is None:
        flash("That issue is gone.", "error")
        return redirect(url_for("owner.issues"))
    if request.method == "POST":
        error = _issue_form_common(request.form, issue)
        if error:
            flash(error, "error")
        else:
            db.commit()
            flash("Issue saved.", "success")
            return redirect(url_for("owner.issue_edit", issue_id=issue.id))
    return render_template("owner/issue_form.html", issue=issue, is_new=False)


# ---------------------------------------------------------------------------
# Events — approve / reject submissions
# ---------------------------------------------------------------------------

@owner_bp.route("/events")
@role_required("platform_owner")
def events():
    db = get_db()
    event_rows = db.query(Event).all()
    event_rows.sort(key=lambda e: (0 if e.status == "pending" else 1,
                                   -(e.created_at.timestamp() if e.created_at else 0)))
    return render_template("owner/events.html", event_rows=event_rows)


@owner_bp.route("/events/<int:event_id>/approve", methods=["POST"])
@role_required("platform_owner")
@require_csrf
def event_approve(event_id: int):
    db = get_db()
    event = db.get(Event, event_id)
    if event is None:
        flash("That event is gone.", "error")
    else:
        event.status = "approved"
        db.commit()
        flash(f"“{event.title}” approved.", "success")
    return redirect(url_for("owner.events"))


@owner_bp.route("/events/<int:event_id>/reject", methods=["POST"])
@role_required("platform_owner")
@require_csrf
def event_reject(event_id: int):
    db = get_db()
    event = db.get(Event, event_id)
    if event is None:
        flash("That event is gone.", "error")
    else:
        event.status = "rejected"
        db.commit()
        flash(f"“{event.title}” rejected.", "success")
    return redirect(url_for("owner.events"))


# ---------------------------------------------------------------------------
# Claim requests — approve / reject
# ---------------------------------------------------------------------------

@owner_bp.route("/claims")
@role_required("platform_owner")
def claims():
    db = get_db()
    claim_rows = db.query(ClaimRequest).all()
    claim_rows.sort(key=lambda c: (0 if c.status == "pending" else 1,
                                   -(c.created_at.timestamp() if c.created_at else 0)))
    return render_template("owner/claims.html", claim_rows=claim_rows)


@owner_bp.route("/claims/<int:claim_id>/approve", methods=["POST"])
@role_required("platform_owner")
@require_csrf
def claim_approve(claim_id: int):
    db = get_db()
    claim = db.get(ClaimRequest, claim_id)
    if claim is None:
        flash("That claim request is gone.", "error")
        return redirect(url_for("owner.claims"))
    profile = db.get(Profile, claim.profile_id)
    if profile is None:
        flash("The listing for that claim is gone.", "error")
        return redirect(url_for("owner.claims"))
    claim.status = "approved"
    claim.decided_at = utcnow()
    profile.claim_status = "claimed"
    profile.verified = True
    profile.claimed_by_user_id = claim.user_id
    db.commit()
    flash(f"“{profile.display_name}” claimed — listing is now verified.", "success")
    return redirect(url_for("owner.claims"))


@owner_bp.route("/claims/<int:claim_id>/reject", methods=["POST"])
@role_required("platform_owner")
@require_csrf
def claim_reject(claim_id: int):
    db = get_db()
    claim = db.get(ClaimRequest, claim_id)
    if claim is None:
        flash("That claim request is gone.", "error")
        return redirect(url_for("owner.claims"))
    claim.status = "rejected"
    claim.reviewer_note = (request.form.get("reviewer_note") or "").strip()
    claim.decided_at = utcnow()
    profile = db.get(Profile, claim.profile_id)
    if profile is not None:
        profile.claim_status = "unclaimed"
        profile.verified = False
        profile.claimed_by_user_id = None
    db.commit()
    flash("Claim request rejected.", "success")
    return redirect(url_for("owner.claims"))


# ---------------------------------------------------------------------------
# Podcasts — series and episodes
# ---------------------------------------------------------------------------

@owner_bp.route("/podcasts")
@role_required("platform_owner")
def podcasts():
    db = get_db()
    series_rows = db.query(PodcastSeries).order_by(PodcastSeries.sort_order).all()
    return render_template("owner/podcasts.html", series_rows=series_rows)


def _series_form_common(form, series: PodcastSeries) -> str | None:
    title = (form.get("title") or "").strip()
    if not title:
        return "A title is required."
    series.title = title
    slug_in = (form.get("slug") or "").strip()
    series.slug = _unique_slug(PodcastSeries, _slugify(slug_in or title),
                              exclude_id=series.id or None)
    audience = form.get("audience", "collectors")
    series.audience = audience if audience in ("collectors", "professionals") else "collectors"
    series.description = (form.get("description") or "").strip()
    series.is_active = _is_checked(form, "is_active")
    return None


@owner_bp.route("/podcasts/series/new", methods=["GET", "POST"])
@role_required("platform_owner")
@require_csrf
def series_new():
    db = get_db()
    series = PodcastSeries()
    if request.method == "POST":
        error = _series_form_common(request.form, series)
        if error:
            flash(error, "error")
        else:
            db.add(series)
            db.commit()
            flash("Series saved.", "success")
            return redirect(url_for("owner.series_edit", series_id=series.id))
    return render_template("owner/series_form.html", series=series, is_new=True)


@owner_bp.route("/podcasts/series/<int:series_id>/edit", methods=["GET", "POST"])
@role_required("platform_owner")
@require_csrf
def series_edit(series_id: int):
    db = get_db()
    series = db.get(PodcastSeries, series_id)
    if series is None:
        flash("That series is gone.", "error")
        return redirect(url_for("owner.podcasts"))
    if request.method == "POST":
        error = _series_form_common(request.form, series)
        if error:
            flash(error, "error")
        else:
            db.commit()
            flash("Series saved.", "success")
            return redirect(url_for("owner.series_edit", series_id=series.id))
    return render_template("owner/series_form.html", series=series, is_new=False)


def _episode_form_common(form, episode: PodcastEpisode) -> str | None:
    title = (form.get("title") or "").strip()
    if not title:
        return "A title is required."
    episode.title = title
    episode.slug = _unique_slug(PodcastEpisode, _slugify(title),
                                exclude_id=episode.id or None)
    episode.episode_number = _parse_int(form.get("episode_number"), 1) or 1
    episode.description = (form.get("description") or "").strip()
    audio_file = (form.get("audio_file") or "").strip().lstrip("/")
    episode.audio_file = audio_file
    story_id = _parse_int(form.get("related_story_id"), None)
    episode.related_story_id = story_id if story_id else None
    profile_id = _parse_int(form.get("related_profile_id"), None)
    episode.related_profile_id = profile_id if profile_id else None
    _set_published(episode, _is_checked(form, "is_published"))
    return None


@owner_bp.route("/podcasts/series/<int:series_id>/episodes/new",
                methods=["GET", "POST"])
@role_required("platform_owner")
@require_csrf
def episode_new(series_id: int):
    db = get_db()
    series = db.get(PodcastSeries, series_id)
    if series is None:
        flash("That series is gone.", "error")
        return redirect(url_for("owner.podcasts"))
    episode = PodcastEpisode(series_id=series.id)
    if request.method == "POST":
        error = _episode_form_common(request.form, episode)
        if error:
            flash(error, "error")
        else:
            db.add(episode)
            db.commit()
            flash("Episode saved.", "success")
            return redirect(url_for("owner.episode_edit", episode_id=episode.id))
    stories = db.query(Story).order_by(Story.title).all()
    profiles = db.query(Profile).order_by(Profile.display_name).all()
    return render_template(
        "owner/episode_form.html", episode=episode, series=series, is_new=True,
        stories=stories, profiles=profiles,
    )


@owner_bp.route("/podcasts/episodes/<int:episode_id>/edit",
                methods=["GET", "POST"])
@role_required("platform_owner")
@require_csrf
def episode_edit(episode_id: int):
    db = get_db()
    episode = db.get(PodcastEpisode, episode_id)
    if episode is None:
        flash("That episode is gone.", "error")
        return redirect(url_for("owner.podcasts"))
    if request.method == "POST":
        error = _episode_form_common(request.form, episode)
        if error:
            flash(error, "error")
        else:
            db.commit()
            flash("Episode saved.", "success")
            return redirect(url_for("owner.episode_edit", episode_id=episode.id))
    stories = db.query(Story).order_by(Story.title).all()
    profiles = db.query(Profile).order_by(Profile.display_name).all()
    return render_template(
        "owner/episode_form.html", episode=episode, series=episode.series,
        is_new=False, stories=stories, profiles=profiles,
    )


# ---------------------------------------------------------------------------
# Books — full CRUD: new/edit/delete, featured picks, shelf order
# ---------------------------------------------------------------------------

@owner_bp.route("/books")
@role_required("platform_owner")
def books():
    db = get_db()
    book_rows = db.query(Book).order_by(Book.sort_order, Book.title).all()
    return render_template("owner/books.html", book_rows=book_rows)


def _book_form_common(form, book: Book) -> str | None:
    title = (form.get("title") or "").strip()
    if not title:
        return "A title is required."
    book.title = title
    slug_in = (form.get("slug") or "").strip()
    book.slug = _unique_slug(Book, _slugify(slug_in or title),
                            exclude_id=book.id or None)
    book.author = (form.get("author") or "").strip()
    book.publisher = (form.get("publisher") or "").strip()
    book.year = _parse_int(form.get("year"), None)
    book.isbn = (form.get("isbn") or "").strip()
    craft = (form.get("craft") or "tattoo").strip()
    book.craft = craft if craft in BOOK_CRAFTS else "tattoo"
    audience = (form.get("audience") or "collectors").strip()
    book.audience = audience if audience in BOOK_AUDIENCES else "collectors"
    kind = (form.get("kind") or "guide").strip()
    book.kind = kind if kind in BOOK_KINDS else "guide"
    book.description = (form.get("description") or "").strip()
    book.why_relevant = (form.get("why_relevant") or "").strip()
    book.cover_image = (form.get("cover_image") or "").strip().lstrip("/")
    book.buy_url = (form.get("buy_url") or "").strip()
    book.has_audiobook = _is_checked(form, "has_audiobook")
    book.audiobook_url = (form.get("audiobook_url") or "").strip()
    if book.has_audiobook and not book.audiobook_url:
        return ("You marked an audiobook — add its link, or uncheck the box. "
                "Only mark audiobooks you have verified really exist.")
    book.is_featured = _is_checked(form, "is_featured")
    book.is_active = _is_checked(form, "is_active")
    book.sort_order = _parse_int(form.get("sort_order"), 0) or 0
    return None


@owner_bp.route("/books/new", methods=["GET", "POST"])
@role_required("platform_owner")
@require_csrf
def book_new():
    db = get_db()
    book = Book(craft="tattoo", audience="collectors", kind="guide")
    if request.method == "POST":
        error = _book_form_common(request.form, book)
        if error:
            flash(error, "error")
        else:
            db.add(book)
            db.commit()
            flash("Book saved.", "success")
            return redirect(url_for("owner.book_edit", book_id=book.id))
    return render_template("owner/book_form.html", book=book, is_new=True,
                           crafts=BOOK_CRAFTS, audiences=BOOK_AUDIENCES,
                           kinds=BOOK_KINDS)


@owner_bp.route("/books/<int:book_id>/edit", methods=["GET", "POST"])
@role_required("platform_owner")
@require_csrf
def book_edit(book_id: int):
    db = get_db()
    book = db.get(Book, book_id)
    if book is None:
        flash("That book is gone.", "error")
        return redirect(url_for("owner.books"))
    if request.method == "POST":
        error = _book_form_common(request.form, book)
        if error:
            flash(error, "error")
        else:
            db.commit()
            flash("Book saved.", "success")
            return redirect(url_for("owner.book_edit", book_id=book.id))
    return render_template("owner/book_form.html", book=book, is_new=False,
                           crafts=BOOK_CRAFTS, audiences=BOOK_AUDIENCES,
                           kinds=BOOK_KINDS)


@owner_bp.route("/books/<int:book_id>/delete", methods=["POST"])
@role_required("platform_owner")
@require_csrf
def book_delete(book_id: int):
    db = get_db()
    book = db.get(Book, book_id)
    if book is None:
        flash("That book is gone.", "error")
    else:
        title = book.title
        db.delete(book)
        db.commit()
        flash(f"“{title}” was deleted.", "success")
    return redirect(url_for("owner.books"))


# ---------------------------------------------------------------------------
# Newsletter editions
# ---------------------------------------------------------------------------

@owner_bp.route("/newsletter")
@role_required("platform_owner")
def newsletter():
    db = get_db()
    editions = (db.query(NewsletterEdition)
                 .order_by(NewsletterEdition.created_at.desc()).all())
    return render_template("owner/newsletter.html", editions=editions)


def _newsletter_form_common(form, edition: NewsletterEdition) -> str | None:
    subject = (form.get("subject") or "").strip()
    if not subject:
        return "A subject is required."
    edition.subject = subject
    slug_in = (form.get("slug") or "").strip()
    edition.slug = _unique_slug(NewsletterEdition, _slugify(slug_in or subject),
                                exclude_id=edition.id or None)
    edition.summary = (form.get("summary") or "").strip()
    edition.body = form.get("body", "")
    edition.is_archived = _is_checked(form, "is_archived")
    return None


@owner_bp.route("/newsletter/new", methods=["GET", "POST"])
@role_required("platform_owner")
@require_csrf
def newsletter_new():
    db = get_db()
    edition = NewsletterEdition()
    if request.method == "POST":
        error = _newsletter_form_common(request.form, edition)
        if error:
            flash(error, "error")
        else:
            db.add(edition)
            db.commit()
            flash("Edition saved.", "success")
            return redirect(url_for("owner.newsletter_edit", edition_id=edition.id))
    return render_template("owner/newsletter_form.html", edition=edition, is_new=True)


@owner_bp.route("/newsletter/<int:edition_id>/edit", methods=["GET", "POST"])
@role_required("platform_owner")
@require_csrf
def newsletter_edit(edition_id: int):
    db = get_db()
    edition = db.get(NewsletterEdition, edition_id)
    if edition is None:
        flash("That edition is gone.", "error")
        return redirect(url_for("owner.newsletter"))
    if request.method == "POST":
        error = _newsletter_form_common(request.form, edition)
        if error:
            flash(error, "error")
        else:
            db.commit()
            flash("Edition saved.", "success")
            return redirect(url_for("owner.newsletter_edit", edition_id=edition.id))
    return render_template("owner/newsletter_form.html", edition=edition, is_new=False)


# ---------------------------------------------------------------------------
# Support tiers — read-only phase-3 stubs (no money moves yet)
# ---------------------------------------------------------------------------

@owner_bp.route("/support-tiers")
@role_required("platform_owner")
def tiers():
    db = get_db()
    tier_rows = db.query(SubscriptionTier).order_by(SubscriptionTier.name).all()
    campaign_rows = (db.query(FundraisingCampaign)
                     .order_by(FundraisingCampaign.created_at.desc()).all())
    return render_template(
        "owner/tiers.html", tier_rows=tier_rows, campaign_rows=campaign_rows,
    )
