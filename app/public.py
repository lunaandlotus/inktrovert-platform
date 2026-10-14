"""Public editorial home — the Inktrovert magazine front door.

No url prefix: these are the top-level routes.

Paywall split (founder, 2026-10-14):
  FREE (the funnel): individual stories/articles, magazine search,
      issue covers as teasers.
  SUBSCRIBER-ONLY: full-issue online viewing (any issue), print/PDF
      export, the History archive. Gates live in app/access.py.

Only the event-submission POST writes, and it goes through require_csrf.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from flask import (Blueprint, abort, current_app, flash, redirect, render_template,
                   request, url_for)

from .access import (archive_teaser_context, can_print_issue, can_view_history,
                      can_view_issue, can_view_story, current_issue)
from .auth import get_current_user, require_csrf
from .db import get_db
from .models import (STORY_CATEGORIES, Event, Issue, NewsletterEdition, PodcastEpisode,
                     PodcastSeries, Profile, Story, utcnow)

public_bp = Blueprint("public", __name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _naive(dt: datetime | None) -> datetime | None:
    """SQLite strips tzinfo; treat naive datetimes as UTC for comparisons."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def _now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug or "untitled"


def _published_stories():
    return get_db().query(Story).filter_by(is_published=True)


def _published_issues():
    return get_db().query(Issue).filter_by(is_published=True)


def _category_label(category: str) -> str:
    return category.replace("-", " ").title()


def _locked_response(title: str, kind: str, cover_image: str = "",
                     teaser: str = ""):
    """Render the subscription teaser for a locked page: cover image, title,
    and blurb visible, content locked, CTA sells the subscription."""
    flash(
        "This is part of the subscriber archive — join to unlock it.",
        "info",
    )
    return render_template(
        "public/locked.html",
        title=title,
        kind=kind,
        cover_image=cover_image,
        teaser=teaser,
        **_browse_flags(),
    )


def _browse_flags() -> dict:
    """The directory blueprint is built by a sibling agent; guard its links
    so public pages render before (and after) it registers."""
    views = current_app.view_functions
    return {
        "directory_enabled": "directory.profile_detail" in views,
        "directory_browse_enabled": "directory.browse" in views,
    }


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------

@public_bp.get("/")
def home():
    db = get_db()
    latest_issue = current_issue(db)
    stories = (
        db.query(Story).filter_by(is_published=True)
        .order_by(Story.published_at.desc(), Story.created_at.desc()).limit(4).all()
    )
    upcoming_events = (
        db.query(Event).filter(Event.status == "approved",
                               Event.starts_at >= _now_naive())
        .order_by(Event.starts_at.asc()).limit(3).all()
    )
    featured_profiles = (
        db.query(Profile).filter(Profile.is_listed == True,  # noqa: E712
                                 Profile.verified == True)  # noqa: E712
        .order_by(Profile.updated_at.desc()).limit(3).all()
    )
    series_list = db.query(PodcastSeries).filter_by(is_active=True).all()
    latest_episodes = []
    for series in series_list:
        ep = (
            db.query(PodcastEpisode)
            .filter_by(series_id=series.id, is_published=True)
            .order_by(PodcastEpisode.published_at.desc(),
                      PodcastEpisode.episode_number.desc()).first()
        )
        if ep is not None:
            latest_episodes.append({"series": series, "episode": ep})
    return render_template(
        "public/home.html",
        latest_issue=latest_issue,
        stories=stories,
        upcoming_events=upcoming_events,
        featured_profiles=featured_profiles,
        latest_episodes=latest_episodes,
        **_browse_flags(),
    )


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------

@public_bp.get("/issues")
def issues():
    db = get_db()
    all_issues = (
        db.query(Issue).filter_by(is_published=True)
        .order_by(Issue.published_at.desc(), Issue.number.desc()).all()
    )
    return render_template("public/issues.html", issues=all_issues)


@public_bp.get("/issues/<slug>")
def issue_detail(slug):
    """Full-issue reader — subscriber-only (any issue, current included).
    Locked visitors get the teaser page (cover, title, blurb visible +
    subscribe CTA), not a 404."""
    db = get_db()
    issue = db.query(Issue).filter_by(slug=slug, is_published=True).first()
    if issue is None:
        abort(404)
    if not can_view_issue(get_current_user(), issue):
        return _locked_response(
            title=f"Issue #{issue.number} — {issue.title}",
            kind="issue",
            cover_image=issue.cover_image,
            teaser=issue.blurb,
        )
    stories = (
        db.query(Story)
        .filter_by(issue_id=issue.id, is_published=True)
        .order_by(Story.sort_order.asc(), Story.published_at.desc()).all()
    )
    upcoming = _upcoming_events(db)
    return render_template(
        "public/issue_detail.html", issue=issue, stories=stories,
        upcoming_events=upcoming,
    )


def _upcoming_events(db, limit=None):
    query = (
        db.query(Event).filter(Event.status == "approved",
                               Event.starts_at >= _now_naive())
        .order_by(Event.starts_at.asc())
    )
    return query.limit(limit).all() if limit else query.all()


@public_bp.get("/issues/<slug>/print")
def issue_print(slug):
    """Clean, print-first view of an issue (used for browser printing and
    as the HTML source for the server-side PDF export). Subscriber-only.
    Carries the full image treatment plus date-driven content (upcoming
    events, dated announcements) — the print edition stands alone as the
    complete issue."""
    db = get_db()
    issue = db.query(Issue).filter_by(slug=slug, is_published=True).first()
    if issue is None:
        abort(404)
    if not can_print_issue(get_current_user(), issue):
        return redirect(url_for("public.issue_detail", slug=slug))
    stories = (
        db.query(Story)
        .filter_by(issue_id=issue.id, is_published=True)
        .order_by(Story.sort_order.asc(), Story.published_at.desc()).all()
    )
    return render_template(
        "public/issue_print.html", issue=issue, stories=stories,
        upcoming_events=_upcoming_events(db),
    )


@public_bp.get("/issues/<slug>/print.pdf")
def issue_print_pdf(slug):
    """Server-side print PDF of an issue, generated with WeasyPrint from the
    same print template — real magazine feel: cover page, table of contents,
    full-bleed story images, events calendar, page numbers. Subscriber-only."""
    db = get_db()
    issue = db.query(Issue).filter_by(slug=slug, is_published=True).first()
    if issue is None:
        abort(404)
    if not can_print_issue(get_current_user(), issue):
        return redirect(url_for("public.issue_detail", slug=slug))
    stories = (
        db.query(Story)
        .filter_by(issue_id=issue.id, is_published=True)
        .order_by(Story.sort_order.asc(), Story.published_at.desc()).all()
    )
    html = render_template("public/issue_print.html", issue=issue, stories=stories,
                           upcoming_events=_upcoming_events(db))

    from flask import Response, request

    try:
        from weasyprint import HTML
    except ImportError:
        abort(501, "PDF export is not installed on this server yet.")

    pdf_bytes = HTML(string=html, base_url=request.url_root).write_pdf()
    filename = f"{issue.slug}-print.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Stories
# ---------------------------------------------------------------------------

@public_bp.get("/stories")
def stories():
    category = request.args.get("category", "").strip().lower()
    db = get_db()
    query = db.query(Story).filter_by(is_published=True)
    if category:
        if category not in STORY_CATEGORIES:
            abort(404)
        query = query.filter_by(category=category)
    all_stories = (
        query.order_by(Story.published_at.desc(), Story.created_at.desc()).all()
    )
    return render_template(
        "public/stories.html",
        stories=all_stories,
        categories=STORY_CATEGORIES,
        active_category=category,
        category_label=_category_label,
    )


@public_bp.get("/stories/<slug>")
def story_detail(slug):
    """Individual stories/articles are free — they're the discovery funnel."""
    db = get_db()
    story = db.query(Story).filter_by(slug=slug, is_published=True).first()
    if story is None or not can_view_story(get_current_user(), story):
        abort(404)
    more = (
        db.query(Story)
        .filter(Story.is_published == True,  # noqa: E712
                Story.category == story.category,
                Story.id != story.id)
        .order_by(Story.published_at.desc()).limit(3).all()
    )
    return render_template(
        "public/story_detail.html",
        story=story,
        more=more,
        category_label=_category_label,
    )


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@public_bp.get("/events")
def events():
    db = get_db()
    upcoming = (
        db.query(Event).filter(Event.status == "approved",
                               Event.starts_at >= _now_naive())
        .order_by(Event.starts_at.asc()).all()
    )
    return render_template("public/events.html", events=upcoming)


@public_bp.get("/events/<slug>")
def event_detail(slug):
    db = get_db()
    event = db.query(Event).filter_by(slug=slug, status="approved").first()
    if event is None:
        abort(404)
    return render_template("public/event_detail.html", event=event)


@public_bp.route("/events/submit", methods=["GET", "POST"])
@require_csrf
def event_submit():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if not title:
            flash("Give the event a title so we know what it is.", "error")
            return redirect(url_for("public.event_submit"))
        db = get_db()
        starts_at = None
        raw_date = request.form.get("starts_at", "").strip()
        if raw_date:
            try:
                # datetime-local comes through as "YYYY-MM-DDTHH:MM".
                starts_at = datetime.fromisoformat(raw_date)
            except ValueError:
                starts_at = None
        slug = _slugify(title)[:200]
        if db.query(Event).filter_by(slug=slug).first() is not None:
            slug = f"{slug}-{int(utcnow().timestamp())}"
        current_user = get_current_user()
        event = Event(
            title=title,
            slug=slug,
            description=request.form.get("description", "").strip(),
            venue_name=request.form.get("venue_name", "").strip(),
            city=request.form.get("city", "").strip(),
            state=request.form.get("state", "").strip(),
            starts_at=starts_at,
            url=request.form.get("url", "").strip(),
            status="pending",
            submitted_by_user_id=current_user.id if current_user else None,
        )
        db.add(event)
        db.commit()
        flash(
            "Thanks — your event is in for review. We'll list it once the "
            "magazine team gives it a look.",
            "success",
        )
        return redirect(url_for("public.events"))
    return render_template("public/event_submit.html")


# ---------------------------------------------------------------------------
# Newsletter archive
# ---------------------------------------------------------------------------

@public_bp.get("/newsletter")
def newsletter():
    db = get_db()
    editions = (
        db.query(NewsletterEdition).filter_by(is_archived=True)
        .order_by(NewsletterEdition.sent_at.desc(),
                  NewsletterEdition.created_at.desc()).all()
    )
    return render_template("public/newsletter.html", editions=editions)


@public_bp.get("/newsletter/<slug>")
def newsletter_detail(slug):
    db = get_db()
    edition = (
        db.query(NewsletterEdition).filter_by(slug=slug, is_archived=True).first()
    )
    if edition is None:
        abort(404)
    return render_template("public/newsletter_detail.html", edition=edition)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Search — full magazine search (stories, issues, episodes, events) plus
# the directory profile search, with scope tabs. Ranking: title hits outrank
# excerpt/body hits, then newest first.
# ---------------------------------------------------------------------------

SEARCH_SCOPES = ("all", "magazine", "directory")


def _score(needle: str, *fields_with_weight):
    score = 0
    for weight, value in fields_with_weight:
        if needle in (value or "").lower():
            score += weight
    return score


def _magazine_search(db, q: str) -> list[dict]:
    needle = q.lower()
    found = []
    stories = (
        db.query(Story)
        .filter(Story.is_published == True)  # noqa: E712
        .all()
    )
    for s in stories:
        score = _score(needle, (3, s.title), (2, s.excerpt), (1, s.category),
                       (1, s.body))
        if score:
            found.append({
                "kind": "story", "title": s.title, "blurb": s.excerpt,
                "score": score, "date": _naive(s.published_at) or _naive(s.created_at),
                "url": url_for("public.story_detail", slug=s.slug),
                "label": _category_label(s.category),
            })
    for i in db.query(Issue).filter_by(is_published=True).all():
        score = _score(needle, (3, f"Issue {i.number} {i.title}"), (3, i.title),
                       (2, i.blurb))
        if score:
            found.append({
                "kind": "issue", "title": f"Issue #{i.number} — {i.title}",
                "blurb": i.blurb, "score": score,
                "date": _naive(i.published_at) or _naive(i.created_at),
                "url": url_for("public.issue_detail", slug=i.slug),
                "label": "Issue",
            })
    episodes = (
        db.query(PodcastEpisode)
        .filter(PodcastEpisode.is_published == True)  # noqa: E712
        .join(PodcastSeries, PodcastSeries.id == PodcastEpisode.series_id)
        .filter(PodcastSeries.is_active == True)  # noqa: E712
        .all()
    )
    for ep in episodes:
        score = _score(needle, (3, ep.title), (2, ep.description),
                       (1, ep.series.title))
        if score:
            found.append({
                "kind": "episode", "title": f"{ep.series.title} — {ep.title}",
                "blurb": ep.description, "score": score,
                "date": _naive(ep.published_at) or _naive(ep.created_at),
                "url": url_for("podcasts.episode_detail",
                               series_slug=ep.series.slug,
                               episode_slug=ep.slug),
                "label": "Podcast",
            })
    for e in db.query(Event).filter_by(status="approved").all():
        score = _score(needle, (3, e.title), (2, e.description), (1, e.city),
                       (1, e.venue_name))
        if score:
            found.append({
                "kind": "event", "title": e.title, "blurb": e.description,
                "score": score, "date": _naive(e.starts_at),
                "url": url_for("public.event_detail", slug=e.slug),
                "label": "Event",
            })
    found.sort(key=lambda r: (-r["score"], r["date"] or datetime(1970, 1, 1)),
               reverse=False)
    found.sort(key=lambda r: r["date"] or datetime(1970, 1, 1), reverse=True)
    found.sort(key=lambda r: r["score"], reverse=True)
    return found


def _profile_search(db, q: str) -> list:
    needle = q.lower()
    matches = []
    for p in db.query(Profile).filter(Profile.is_listed == True).all():  # noqa: E712
        specialties = " ".join(str(s) for s in (p.specialties or [])).lower()
        if (needle in (p.display_name or "").lower()
                or needle in (p.city or "").lower()
                or needle in specialties):
            matches.append(p)
    return matches


@public_bp.get("/search")
def search():
    q = request.args.get("q", "").strip()
    scope = request.args.get("scope", "all").strip().lower()
    if scope not in SEARCH_SCOPES:
        scope = "all"
    results = []
    profiles = []
    if q:
        db = get_db()
        if scope in ("all", "magazine"):
            results = _magazine_search(db, q)
        if scope in ("all", "directory"):
            profiles = _profile_search(db, q)
    return render_template(
        "public/search.html",
        q=q,
        scope=scope,
        results=results,
        profiles=profiles,
        category_label=_category_label,
        **_browse_flags(),
    )


# ---------------------------------------------------------------------------
# About
# ---------------------------------------------------------------------------

@public_bp.get("/about")
def about():
    return render_template("public/about.html", **_browse_flags())


# ---------------------------------------------------------------------------
# History — the magazine's memory. Subscriber-only for the full timeline;
# public visitors get teaser rows (covers/titles visible, content locked).
# ---------------------------------------------------------------------------

@public_bp.get("/history")
def history():
    db = get_db()
    user = get_current_user()
    if not can_view_history(user):
        teaser = archive_teaser_context(db)
        return render_template(
            "public/history.html",
            teaser_mode=True,
            teaser_issues=teaser["issues"],
            **_browse_flags(),
        )

    type_filter = request.args.get("type", "").strip().lower()
    year_filter = request.args.get("year", "").strip()

    items = []
    if not type_filter or type_filter == "issue":
        for issue in db.query(Issue).filter_by(is_published=True).all():
            when = _naive(issue.published_at) or _naive(issue.created_at)
            items.append({"kind": "issue", "date": when, "object": issue,
                          "title": f"Issue #{issue.number} — {issue.title}",
                          "blurb": issue.blurb})
    if not type_filter or type_filter == "story":
        for story in _published_stories().all():
            when = _naive(story.published_at) or _naive(story.created_at)
            items.append({"kind": "story", "date": when, "object": story,
                          "title": story.title, "blurb": story.excerpt})
    if not type_filter or type_filter == "episode":
        episodes = (
            db.query(PodcastEpisode)
            .filter(PodcastEpisode.is_published == True)  # noqa: E712
            .join(PodcastSeries,
                  PodcastSeries.id == PodcastEpisode.series_id)
            .filter(PodcastSeries.is_active == True)  # noqa: E712
            .all()
        )
        for ep in episodes:
            when = _naive(ep.published_at) or _naive(ep.created_at)
            items.append({"kind": "episode", "date": when, "object": ep,
                          "title": f"{ep.series.title} — {ep.title}",
                          "blurb": ep.description})

    items.sort(key=lambda i: i["date"] or datetime(1970, 1, 1), reverse=True)

    years = sorted({i["date"].year for i in items if i["date"]}, reverse=True)
    if year_filter.isdigit():
        y = int(year_filter)
        items = [i for i in items if i["date"] and i["date"].year == y]
    else:
        year_filter = ""

    return render_template(
        "public/history.html",
        teaser_mode=False,
        items=items,
        years=years,
        type_filter=type_filter,
        year_filter=year_filter,
        category_label=_category_label,
    )
