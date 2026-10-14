# Story leads inbox — contract for the daily gathering job

The daily industry-news gathering runs as a **separate scheduled job outside
the app**. Its only job is to find things; this inbox is where the findings
land. The platform owner reviews each lead, promotes the good ones to full
draft stories, or discards the rest.

## How the job feeds the inbox

The job runs on the same machine and venv as the app. It imports the app
code and calls `ingest_leads()` — no HTTP, no credentials, nothing to
configure:

```python
import sys
sys.path.insert(0, "/home/hatch/workspace/inktrovert-platform")

from app.db import init_engine, session_scope
from app.leads import ingest_leads
from app.config import Config

init_engine(Config.DATABASE_URL)

items = [
    {
        "headline": "Ink brand launches vegan aftercare line",
        "source_url": "https://example.com/news/vegan-aftercare",
        "source_name": "Example Industry News",          # optional
        "suggested_angle": "Angle: interview the founder about the formula.",  # optional
    },
]

with session_scope() as db:
    result = ingest_leads(db, items, submitted_by="daily-gather-job")
    print(result)
    # {"created": [12, 13], "skipped": [{"headline": ..., "reason": "duplicate_url"}]}
```

Required per item: `headline`, `source_url`. Optional: `source_name`,
`suggested_angle`.

## Dedupe — the same story is never suggested twice

1. **URL (hard):** the source URL is normalized — tracking params
   (`utm_*`, `fbclid`, `gclid`, …) stripped, scheme/host lowercased,
   trailing slashes dropped, remaining query args sorted — then SHA-256
   hashed. `story_leads.url_hash` is UNIQUE, so the database itself refuses
   a repeat link even across job runs. A re-suggested link comes back as
   `{"reason": "duplicate_url"}` and is **not** re-inserted.
2. **Headline (soft):** if the normalized headline (casefolded, punctuation
   stripped) matches a lead that isn't discarded, it's skipped as
   `duplicate_headline` — same story, different link. Discarded leads don't
   count, so a discarded angle can legitimately come back via a new link.

## Owner workflow (in the app)

- **new** → fresh from the job. **reviewing** → owner is looking at it.
- **Promote** (`promote_lead`): creates an *unpublished* draft `Story`
  carrying the headline, the suggested angle as the starting excerpt, and
  the source link at the top of the body. The lead is marked `promoted`
  and linked to the story. Promoting twice returns the same story —
  idempotent.
- **Discard** (`discard_lead`): marks `discarded` with an optional note.
- `inbox_counts()` gives per-status counts for the inbox badge.

## Statuses

`new` → `reviewing` → `promoted` | `discarded`. Only the owner
(`platform_owner` role) touches this inbox; the job only ever inserts.
