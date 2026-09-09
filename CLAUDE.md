# CLAUDE.md — CampusPluse

Read this before working anywhere in the repo. It's the shared contract every
track (and every Claude Code / Cowork session) builds against, so nobody
re-derives the schema or invents a conflicting API shape.

## What this is

CampusPluse — AI-powered campus problem intelligence. Students report campus
issues (WiFi, electrical, sanitation, infrastructure, academics...) with a
description, an optional photo, and a location. The system categorizes,
scores priority, detects duplicates/recurring issues via embeddings, and
routes to the right department. Full plan: `docs/build-plan.md`.

## Stack

- `apps/web` — Next.js 15 (App Router), TypeScript, Tailwind. Student report
  flow + admin dashboard.
- `apps/api` — FastAPI (Python 3.11+, async). Owns every DB write and every
  AI call. The web app never talks to Postgres or Gemini directly.
- Postgres 16 + pgvector for storage and similarity search. Local dev via
  `docker-compose.yml` (image `pgvector/pgvector:pg16`); production target
  is a hosted Postgres with the pgvector extension enabled (e.g. Supabase).
- Realtime: Postgres change feed → websocket, so the admin dashboard updates
  live instead of polling. If you're on Supabase, this is Supabase Realtime;
  the FastAPI service also exposes a plain `/ws/complaints` fallback so the
  frontend isn't hard-coupled to one provider.

## AI provider contract — do not bypass this

All model calls go through `apps/api/app/ai/provider.py`'s `AIProvider`
protocol (`understand_complaint`, `embed`). **Never import the Gemini SDK
(or any provider SDK) from a router or pipeline module** — always go through
`get_provider()`, which reads the `LLM_PROVIDER` env var (`gemini` |
`mock`, with `openai`/`claude` stubbed for later). This is what makes the
system provider-agnostic and demo-safe (see `MockProvider` — it's the
automatic fallback when a live call errors or times out, not just a dev
convenience).

The structured-output schema in `apps/api/app/ai/schemas.py` is the source
of truth for what `category`, `severity`, and `safety_flag` mean everywhere
else in the codebase — don't redefine these ad hoc in a router.

## Data model — source of truth

Six tables. Full DDL lives in `apps/api/app/db/migrations/versions/0001_init.py`
(Alembic). Don't hand-edit a live database — write a migration, even a
throwaway one during the hackathon.

- `departments(id, name, contact_email)`
- `categories(id, slug, default_department_id)`
- `complaints(id, student_id, raw_description, photo_url, location_building,
  location_room, category_id, department_id, severity, safety_flag,
  priority_score, cluster_id, status, ai_summary, created_at)`
- `complaint_embeddings(complaint_id, embedding vector(768))` — HNSW cosine index
- `complaint_clusters(id, category_id, location_building,
  representative_complaint_id, member_count, is_recurring, first_seen, last_seen)`
- `status_events(id, complaint_id, status, note, actor, created_at)`

## Priority formula — keep it explainable

```
priority = 0.40 * severity_score
         + 0.30 * log1p(cluster_size) / log1p(CLUSTER_CAP)
         + 0.20 * safety_flag
         + 0.10 * sla_age_factor
```

All four terms get stored per-complaint (not just the final number) so the
UI can render a 4-segment breakdown bar instead of an opaque score. See
`apps/api/app/pipeline/priority.py`.

## Similarity / clustering thresholds

Cosine similarity via pgvector, scoped to same `category_id` + same
`location_building` + a rolling 14-day window:

- `>= 0.92` → auto-merge as a duplicate of the existing open complaint
- `0.75–0.92` → "suggested merge", surfaced to an admin, not auto-applied
- `< 0.75` → new, independent complaint

A cluster crossing 3 independent students → `is_recurring = true`.

## Conventions

- Python: `ruff` + `black`, async everywhere in `apps/api`, type hints
  required on public functions.
- TypeScript: strict mode, server components by default, `'use client'`
  only for genuinely interactive widgets (map, live feed, chaos button).
- Commits: small, one per working slice. Push at least every couple of
  hours — track owners integrate against `main`, not against each other's
  branches, to keep merge pain low.
- Every new backend function that isn't a thin route handler should have at
  least one test next to it (`apps/api/tests/`), especially anything in
  `pipeline/` — the clustering and priority logic is the one thing that
  cannot silently break before a live demo.

## Environment variables

See `apps/api/.env.example` and `apps/web/.env.example`. Never commit a
real `.env` — both are gitignored.

## A note on this scaffold

This initial scaffold was written by hand (no `npm install` / `pip install`
was run while generating it, so double-check dependency versions and run a
full install before trusting anything compiles). Treat every file here as a
solid, structurally-correct starting point per §09/§10 of `docs/build-plan.md`
— not a finished feature. Each track should extend, not rewrite, unless
something is actually wrong.
