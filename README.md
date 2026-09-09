# CampusPluse

AI-powered campus problem intelligence. Students report campus issues with a
description, photo, and location; the system categorizes them, scores
priority, detects duplicate and recurring problems via embeddings, and
routes each one to the right department. Admins get a live dashboard instead
of a flat ticket queue.

Full build plan (architecture, AI pipeline, 48-hour timeline, demo script):
[`docs/build-plan.md`](docs/build-plan.md).

**Read `CLAUDE.md` before touching anything** — it's the shared contract
(schema, AI provider interface, priority formula, conventions) every part of
this repo is built against.

## Layout

```
apps/web/     Next.js 15 — student report flow + admin dashboard
apps/api/     FastAPI — CRUD, AI pipeline, clustering, priority scoring
packages/     Shared TypeScript types generated from the API's OpenAPI spec
scripts/      Seed / demo-data tooling
docs/         The build plan and any other reference docs
```

## Local setup

```bash
# 1. Database (Postgres + pgvector)
docker compose up -d

# 2. Backend
cd apps/api
cp .env.example .env      # fill in DATABASE_URL / LLM_API_KEY
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# 3. Frontend (separate terminal)
cd apps/web
cp .env.example .env.local
npm install
npm run dev
```

The API serves its OpenAPI spec at `http://localhost:8000/docs` — use it to
sanity-check request/response shapes across tracks before wiring the
frontend to a new endpoint.

## Provider

Set `LLM_PROVIDER=gemini` and `LLM_API_KEY=<your Gemini API key>` in
`apps/api/.env` once you have one. Until then, `LLM_PROVIDER=mock` (the
default in `.env.example`) runs the whole pipeline against a fake provider
that returns realistic-but-fake structured output and embeddings — the rest
of the system works identically either way.
