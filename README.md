# CampusPlus

AI-powered campus problem intelligence. Students report campus issues with a
description, photo and location; the system works out which reports are the
*same* problem, which problems keep coming back, and which deserve attention
first — and explains every one of those decisions.

The complaint form is not the product. The intelligence layer is.

**Read [`CLAUDE.md`](CLAUDE.md) before touching anything** — it is the shared
contract (schema, AI provider interface, priority formula, thresholds,
security rules). Full build plan: [`docs/build-plan.md`](docs/build-plan.md).

## What it actually does

```
student submits
   → multimodal understanding (category, severity 1-5, safety flag, photo check, summary)
     → embed the normalized summary (768-dim)
       → pgvector cosine search, scoped to same category + building + 14 days
         → >= 0.92 auto-merge · 0.75-0.92 ask an admin · < 0.75 new complaint
           → count INDEPENDENT students; 3+ makes it a recurring issue
             → recompute explainable priority for every cluster member
               → route to a department
                 → broadcast over the websocket; the dashboard reacts live
```

## Layout

```
apps/web/     Next.js 15 — student report flow + admin command center
apps/api/     FastAPI — pipeline, clustering, priority, realtime, admin API
packages/     Shared TypeScript types
scripts/      seed_demo.py (demo + test fixture), dev_db.py (no-Docker database)
docs/         Build plan
```

## Running it in VS Code

Open the **`CampusPlus` folder** as the workspace root (not `Documents`).

Press `Ctrl+Shift+P` -> **Tasks: Run Task** -> **Start everything**. That runs
three tasks in order and leaves each in its own terminal tab:

| Task | What it does | URL |
|---|---|---|
| 1: Database (Docker) | Postgres 16 + pgvector, waits for healthy | `localhost:5432` |
| 2: API (FastAPI) | Owns every DB write and AI call | http://localhost:8000 |
| 3: Web (Next.js) | Student flow + admin dashboard | http://localhost:3000 |

Then run the **Seed demo data** task once to populate the dashboard.

Other tasks in the same menu: *Seed: demo clusters only* (fast, just the two
merge clusters), *Run backend tests*, *Typecheck web*, *Stop database*.

`F5` gives you two debug configurations: **Debug API (FastAPI)** with working
breakpoints, and **Debug: one pytest file** for whichever test file is open.

### Or by hand, three terminals

```bash
# Terminal 1 - database
docker compose up -d

# Terminal 2 - API
cd apps/api
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# Terminal 3 - web
cd apps/web
npm run dev
```

Open http://localhost:3000. First run only, in a fourth terminal:

```bash
.\apps\api\.venv\Scripts\python.exe scripts\seed_demo.py --post --reset
```

## Local setup

**1. A database with pgvector.** Any one of:

```bash
docker compose up -d                                    # preferred
pip install pgserver && python scripts/dev_db.py start  # no Docker, no admin rights
# or point DATABASE_URL at a hosted Postgres (Supabase etc.)
```

> Docker is the verified path. `scripts/dev_db.py` is the fallback for a
> machine without Docker or admin rights - a real PostgreSQL with real
> pgvector, so the code behaves identically either way.

**2. Backend.**

```bash
cd apps/api
cp .env.example .env          # set DATABASE_URL; LLM_PROVIDER=mock needs no key
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

**3. Frontend** (separate terminal).

```bash
cd apps/web
cp .env.example .env.local
npm install
npm run dev
```

**4. Demo data**, pushed through the real pipeline — real model calls, real
embeddings, real pgvector search, real clusters:

```bash
python scripts/seed_demo.py --post           # seed
python scripts/seed_demo.py --post --reset   # clear first, for a repeatable demo
```

OpenAPI docs at `http://localhost:8000/docs`; `GET /health` reports which
provider is actually live and whether admin auth is on.

## Testing

```bash
cd apps/api && pytest        # 116 tests; DB-backed ones skip without a database
RUN_DB_TESTS=1 pytest        # turn those skips into failures (CI)
cd apps/web && npm run build
```

`apps/api/tests/test_pipeline_db.py::test_the_signature_demo` is the one that
matters: it drives three students reporting the same leak through the real
pipeline against real pgvector and asserts each visible step — merge, then
recurring, then the priority rise on the *earlier* reports.

Note: the DB fixtures truncate complaint tables around each test, so running
the suite clears seeded demo data. Re-seed afterwards.

## AI provider

`LLM_PROVIDER=mock` (the default) runs the entire pipeline against
deterministic fake-but-realistic structured output and embeddings — no key, no
network, no quota burned, and near-duplicates still cluster correctly, so the
whole demo works offline.

Set `LLM_PROVIDER=gemini` and `LLM_API_KEY=<key>` for the real thing. Gemini
calls are wrapped with a timeout and fall back to the mock provider
automatically on failure, so a rate limit mid-demo degrades instead of
crashing.
