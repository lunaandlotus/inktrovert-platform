"""Story leads inbox — the owner's review queue for daily industry findings.

The daily gathering runs as a separate scheduled job outside the app. That
job feeds this inbox through `ingest_leads()` (import this module and call
it — same machine, same venv). The owner then reviews each lead in the app:
mark reviewing, promote the good ones to full draft stories, or discard.

Dedupe (so the same story is never suggested twice):
  1. URL: `normalize_url()` strips tracking params (utm_*, fbclid, gclid,
     etc.), lowercases scheme/host, drops trailing slashes, and sorts the
     remaining query args. The SHA-256 of that is `StoryLead.url_hash`,
     which carries a UNIQUE constraint — the database itself refuses a
     repeat link, even across job runs.
  2. Headline: `normalize_headline()` casefolds and strips punctuation; a
     lead whose normalized headline matches a non-discarded lead is skipped
     as a probable same-story-different-URL repeat. Discarded leads don't
     count, so a discarded angle can come back through a new link later.
"""
from __future__ import annotations

import hashlib
import re
import string
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy.orm import Session

from .models import LEAD_STATUSES, Story, StoryLead, normalize_state, utcnow

# Query params that identify the click, not the page — safe to drop.
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "fbclid", "gclid", "msclkid", "mc_cid", "mc_eid", "igshid",
    "_ga", "ref", "ref_src", "ref_url",
}


def normalize_url(url: str) -> str:
    """Canonical form of a source URL for dedupe purposes."""
    url = (url or "").strip()
    if not url:
        return ""
    parsed = urlparse(url if "://" in url else "https://" + url)
    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower() if parsed.hostname else ""
    port = f":{parsed.port}" if parsed.port and parsed.port not in (80, 443) else ""
    path = parsed.path.rstrip("/") or "/"
    kept = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if k.lower() not in _TRACKING_PARAMS]
    kept.sort()
    return urlunparse((scheme, host + port, path, "", urlencode(kept), ""))


def url_hash_for(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()


_PUNCT = re.compile(f"[{re.escape(string.punctuation)}]")


def normalize_headline(headline: str) -> str:
    """Casefolded, punctuation-free headline for soft duplicate matching."""
    text = _PUNCT.sub(" ", (headline or "").casefold())
    return re.sub(r"\s+", " ", text).strip()


def find_duplicate(db: Session, headline: str,
                   source_url: str) -> tuple[StoryLead | None, str | None]:
    """Return (existing_lead, reason) or (None, None).

    Reasons: "duplicate_url" (hard — same canonical link) or
    "duplicate_headline" (soft — same story, different link).
    """
    url_hash = url_hash_for(source_url)
    hit = db.query(StoryLead).filter_by(url_hash=url_hash).one_or_none()
    if hit is not None:
        return hit, "duplicate_url"
    norm = normalize_headline(headline)
    if norm:
        for lead in db.query(StoryLead).filter(StoryLead.status != "discarded").all():
            if normalize_headline(lead.headline) == norm:
                return lead, "duplicate_headline"
    return None, None


def ingest_lead(db: Session, *, headline: str, source_url: str,
                source_name: str = "", suggested_angle: str = "",
                suggested_state: str | None = None,
                submitted_by: str = "daily-gather-job") -> tuple[StoryLead | None, str | None]:
    """Insert one lead. Returns (lead, None), or (existing, skip_reason).

    suggested_state accepts a 2-letter code or full state name; it is
    normalized, and anything unrecognized stays untagged (None).
    """
    headline = (headline or "").strip()
    source_url = (source_url or "").strip()
    if not headline or not source_url:
        raise ValueError("headline and source_url are required")
    existing, reason = find_duplicate(db, headline, source_url)
    if existing is not None:
        return existing, reason
    lead = StoryLead(
        headline=headline,
        source_name=(source_name or "").strip(),
        source_url=source_url,
        url_hash=url_hash_for(source_url),
        suggested_angle=(suggested_angle or "").strip(),
        suggested_state=normalize_state(suggested_state),
        submitted_by=submitted_by,
        status="new",
    )
    db.add(lead)
    db.commit()
    return lead, None


def ingest_leads(db: Session, items: list[dict],
                 submitted_by: str = "daily-gather-job") -> dict:
    """Bulk ingest for the scheduled job.

    items: list of dicts with headline, source_url, and optional
    source_name / suggested_angle / suggested_state. Returns
    {"created": [ids], "skipped": [{"headline":..., "reason":...}]}.
    """
    created: list[int] = []
    skipped: list[dict] = []
    for item in items:
        lead, reason = ingest_lead(
            db,
            headline=item.get("headline", ""),
            source_url=item.get("source_url", ""),
            source_name=item.get("source_name", ""),
            suggested_angle=item.get("suggested_angle", ""),
            suggested_state=item.get("suggested_state"),
            submitted_by=submitted_by,
        )
        if reason is None:
            created.append(lead.id)
        else:
            skipped.append({"headline": item.get("headline", ""), "reason": reason})
    return {"created": created, "skipped": skipped}


def set_lead_status(db: Session, lead: StoryLead, status: str) -> StoryLead:
    if status not in LEAD_STATUSES:
        raise ValueError(f"unknown status {status!r}; valid: {LEAD_STATUSES}")
    lead.status = status
    lead.updated_at = utcnow()
    db.commit()
    return lead


def discard_lead(db: Session, lead: StoryLead, note: str = "") -> StoryLead:
    if note:
        lead.notes = (lead.notes + "\n" + note).strip() if lead.notes else note
    return set_lead_status(db, lead, "discarded")


def promote_lead(db: Session, lead: StoryLead, *, category: str = "news",
                 author_name: str = "") -> Story:
    """Turn a lead into an unpublished draft Story and mark the lead promoted.

    The draft carries the headline, the suggested angle as the starting
    excerpt, and the source link at the top of the body so the owner (or a
    writer) has everything needed to write it up. The story stays
    unpublished until it goes through the normal publishing workflow.
    """
    if lead.status == "promoted" and lead.promoted_story_id:
        story = db.get(Story, lead.promoted_story_id)
        if story is not None:
            return story  # idempotent: already promoted
    from .models import STORY_CATEGORIES  # local import: cheap, avoids cycles
    if category not in STORY_CATEGORIES:
        raise ValueError(f"unknown category {category!r}; valid: {STORY_CATEGORIES}")
    base_slug = re.sub(r"[^a-z0-9]+", "-", lead.headline.casefold()).strip("-")[:200] or "story"
    slug = base_slug
    n = 2
    while db.query(Story).filter_by(slug=slug).one_or_none() is not None:
        slug = f"{base_slug}-{n}"
        n += 1
    story = Story(
        title=lead.headline,
        slug=slug,
        category=category,
        excerpt=lead.suggested_angle,
        body=f"Source: {lead.source_name} — {lead.source_url}\n\n",
        author_name=author_name,
        is_published=False,
        state=lead.suggested_state,
    )
    db.add(story)
    db.flush()
    lead.promoted_story_id = story.id
    set_lead_status(db, lead, "promoted")
    return story


def inbox_counts(db: Session) -> dict:
    """Status counts for the owner's inbox badge/list."""
    counts = {s: 0 for s in LEAD_STATUSES}
    for status, in db.query(StoryLead.status).all():
        counts[status] = counts.get(status, 0) + 1
    return counts
