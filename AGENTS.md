# AGENTS.md — CampusPlus

Read this before working anywhere in the repo. It is the shared contract
every session builds against, so nobody re-derives the schema or invents a
conflicting API shape.

## What this is

CampusPlus — AI-powered campus problem intelligence. Students report campus
issues (WiFi, electrical, sanitation, infrastructure, academics) with a
description, an optional photo, and a location. The system categorizes them,
scores priority, detects duplicates and recurring problems via embeddings,
and routes each to the right department.

**The intelligence layer is the product, not the form.** Any change that
makes the complaint form nicer at the expense of the merge/recurring/priority
path is the wrong trade. Full plan: `docs/build-plan.md`.

## Stack

- `apps/web` — Next.js 15 (App Router), TypeScript, Tailwind. Student report
  flow + admin command center.
- `apps/api` — FastAPI (Python 3.11+, async). Owns every DB write and every
  AI call. The web app never talks to Postgres or a model provider directly.
- Postgres 16 + pgvector for storage and similarity search.
- Realtime: the API broadcasts over `/ws/complaints`; the dashboard
  subscribes instead of polling.

## Running it

Three ways to get a database, in order of preference:

```bash
# 1. Docker (the intended local path)
docker compose up -d

# 2. No Docker? A pip-installable Postgres+pgvector, no admin rights needed.
pip install pgserver && python scripts/dev_db.py start   # prints DATABASE_URL

# 3. Hosted Postgres (Supabase etc.) - put its URL in apps/api/.env with
#    the +asyncpg driver.
```

Option 1 is verified working on the primary dev machine (Docker Desktop with
the WSL2 backend). Option 2 stays documented because it needs neither Docker
nor admin rights, and it is a real PostgreSQL with real pgvector - every code
path (HNSW index, `<=>` operator, `vector(768)` column) is exercised
identically either way.

Then:

```bash
cd apps/api
cp .env.example .env          # fill in DATABASE_URL; LLM_PROVIDER=mock is fine
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

```bash
cd apps/web
cp .env.example .env.local
npm install && npm run dev
```

Seed demo data **through the real pipeline** (this is also the fastest
end-to-end smoke test):

```bash
python scripts/seed_demo.py --post                     # all 27 complaints
python scripts/seed_demo.py --post --reset             # clear first (repeatable demo)
python scripts/seed_demo.py --post --only-clusters     # just the merge clusters
```

> On Windows, write `.env` with a plain editor. PowerShell's `Set-Content`
> and `Out-File` default to UTF-8 **with a BOM**, which corrupts the first
> key so `DATABASE_URL` silently falls back to its default and every request
> fails with a connection error.

## Testing

```bash
cd apps/api && pytest              # DB tests skip if no database is reachable
RUN_DB_TESTS=1 pytest              # make those skips hard failures (use in CI)
cd apps/web && npx tsc --noEmit && npm run build
```

The DB-backed fixtures **TRUNCATE the complaint tables** before and after each
test. Running the suite wipes seeded demo data — re-run `seed_demo.py --post`
afterwards. Reference data (departments, categories) survives.

`conftest.py` pins `LLM_PROVIDER=mock` before anything imports `app.config`,
and an autouse fixture asserts it. Tests must never call a live API: with
`LLM_PROVIDER=gemini` in `.env` the suite went from 3 seconds to 213 and
started failing on clustering assertions, because calls that fell back
mid-test produced embeddings from a different space than their neighbours.

## AI provider contract — do not bypass this

All model calls go through `apps/api/app/ai/provider.py`'s `AIProvider`
protocol: `understand_complaint`, `embed`, `answer_question`. **Never import
a provider SDK (google-genai or any other) from a router or pipeline
module** — always go through `get_provider()`, which reads `LLM_PROVIDER`
(`gemini` | `mock`).

When `LLM_PROVIDER=gemini`, `get_provider()` returns a `FallbackProvider`
that applies `LLM_TIMEOUT_SECONDS` to every call and degrades to
`MockProvider` on timeout, rate limit or malformed output. This is automatic
and load-bearing: **callers must not wrap provider calls in their own
try/except**, because there is exactly one place that decides what "the AI is
unavailable" means. `/health` reports `llm_effective` so nobody has to guess
whether a demo is really hitting Gemini.

The structured-output schema in `apps/api/app/ai/schemas.py` is the source of
truth for what `category`, `severity` and `safety_flag` mean everywhere else.
Every provider payload passes through `parse_understanding()`, which repairs
what can be repaired and raises on what cannot — don't re-validate ad hoc in
a router.

Model choices (re-verify against live docs before a demo; these move fast):
`gemini-3.8-flash` for understanding, `gemini-embedding-001` with
`task_type=CLUSTERING` truncated to 768 dims. `gemini-embedding-2` is also
supported — `_embed_config` drops `task_type` for that family automatically.

`GEMINI_FALLBACK_MODELS` is a comma-separated chain tried in order when the
primary model returns a capacity error (503 "high demand", 429). The newest
flash models are the most likely to be capacity-constrained on a free tier —
during this build 3.8 and 3.7 both 503'd while 3.6 answered instantly — and
stepping down a generation is a much better degrade than dropping to the mock.
MockProvider remains the last resort.

**Embedding spaces do not mix.** A mock vector and a Gemini vector are not
comparable; cosine similarity between them is noise, not a low score. Every
embedding therefore records the provider that produced it
(`complaint_embeddings.provider`) and similarity search filters on it. Without
this, one transient 503 mid-demo would leave a complaint that can never merge
with its own duplicates. `/admin/stats` reports `embedding_providers_mixed`,
and `seed_demo.py --post` warns loudly — if you see a mix, re-seed with
`--reset` once the provider is healthy.

## Data model — source of truth

Six tables. DDL lives in `apps/api/app/db/migrations/versions/`. Never
hand-edit a live database — write a migration, even a throwaway one.

- `departments(id, name, contact_email)`
- `categories(id, slug, default_department_id)`
- `complaints(...)` — plus, from migration 0002: `photo_matches_text`,
  the four stored `priority_*` terms, `suggested_match_complaint_id` /
  `suggested_similarity`, and `department_overridden`.
- `complaint_embeddings(complaint_id, embedding vector(768))` — HNSW cosine index
- `complaint_clusters(..., member_count, independent_student_count, is_recurring, ...)`
- `status_events(id, complaint_id, status, note, actor, created_at)`

`student_id` is **NULL for anonymous**, never the literal string
`"anonymous"` — every anonymous report counts as a distinct reporter, and
collapsing them onto one id would make three anonymous students look like
one.

## Priority formula — keep it explainable

```
priority = 0.40 * severity_score
         + 0.30 * log1p(cluster_size) / log1p(CLUSTER_CAP)
         + 0.20 * safety_flag
         + 0.10 * sla_age_factor
```

All four terms are **stored per complaint** (`priority_severity`,
`priority_frequency`, `priority_safety`, `priority_sla_age`) so the UI renders
a 4-segment bar, not an opaque score. They sum to `priority_score`.
`cluster_size` means **independent students**, the same number the recurring
rule uses — using submissions here would let one person inflate priority even
though it explicitly must not flip `is_recurring`.

Only the SLA-age term is recomputed at read time (it climbs while a complaint
sits open); the other three change only when something real changes and are
written by `pipeline/intake.py:apply_priority`, the single place allowed to
write those columns.

## Similarity / clustering thresholds

Cosine similarity via pgvector (`<=>`, HNSW index), scoped to same
`category_id` + same `location_building` + a rolling 14-day window, excluding
resolved complaints:

- `>= 0.92` → auto-merge as a duplicate
- `0.75–0.92` → recorded on `suggested_match_complaint_id`, surfaced to an
  admin, **never auto-applied**
- `< 0.75` → new, independent complaint

A cluster with `>= 3` **independent students** → `is_recurring = true`.

Every threshold is configurable via `Settings` (`app/config.py`). Pipeline
modules keep them as default argument values so they stay pure and testable;
app callers pass the configured values in. Don't scatter magic numbers.

## Architecture rules

- `pipeline/cluster.py` and `pipeline/priority.py` are **pure** — no DB, no
  IO. `pipeline/similarity.py` and `pipeline/intake.py` own the DB-aware
  half. Routers stay thin.
- Cluster counts are always **re-derived from rows** (`refresh_cluster`),
  never incremented, so a merge, unmerge or delete leaves consistent state
  with no separate repair path.
- After any write, re-read through `_get_complaint_or_404`, which sets
  `populate_existing=True`. The session uses `expire_on_commit=False`, so a
  plain re-query returns stale already-loaded relationships.

## API conventions

- `GET /complaints` — priority-sorted, filterable (`status`, `category`,
  `building`, `recurring_only`). Filtering happens in SQL, not the browser.
- `GET /clusters` — real cluster rows. The dashboard must read these, never
  re-derive clusters client-side by grouping on category+building.
- `/admin/*` — all gated by `require_admin`; also `PATCH
  /complaints/{id}/status` and `DELETE /complaints/{id}`.
- `WS /ws/complaints` — `{"type": ..., "data": {...}}`; see `app/realtime.py`
  for the event vocabulary. `cluster.recurring` fires only on the transition.

## Security

- Secrets come only from env vars. Never commit a real `.env` (both are
  gitignored). No key, token or password belongs in the repo.
- `ADMIN_TOKEN` gates every admin action via `X-Admin-Token`. Left empty the
  API runs open — fine for a laptop demo, and reported as
  `admin_auth: "disabled"` on `/health` so it is never a silent hole. The
  token lives in the operator's browser localStorage, never in a
  `NEXT_PUBLIC_*` var, which would ship it to every visitor.
- Uploads are validated by **magic bytes**, not the declared mime type, and
  the stored filename is always generated — there is no client-controlled
  path component.
- "Ask CampusPlus" never lets a model write SQL. A question is reduced to a
  closed set of typed filters; cited ids are intersected with the ids we
  actually fetched, so a hallucinated id cannot reach the client.

## Conventions

- Python: `ruff` + `black`, async everywhere in `apps/api`, type hints on
  public functions.
- TypeScript: strict mode, server components by default, `'use client'` only
  for genuinely interactive widgets.
- Buildings come from `apps/web/src/lib/campus.ts`. Similarity is scoped by
  building name, so free-text building entry would silently break clustering
  — the report form, the heatmap and `seed_demo.py` share one vocabulary.
- Every new backend function that isn't a thin route handler gets at least
  one test in `apps/api/tests/`, especially anything in `pipeline/` — the
  clustering and priority logic is the one thing that cannot silently break
  before a live demo.

## Environment variables

See `apps/api/.env.example` and `apps/web/.env.example`.
