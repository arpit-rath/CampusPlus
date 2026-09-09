# CampusPluse — Hackathon Build Plan

Designed version with diagrams and a visual timeline:
https://claude.ai/code/artifact/8d2a706b-f264-41aa-9b11-3f76a6e462a4

Prepared for: 36–48 hour hackathon, team of 3–4, building mostly via Claude
Code. Stack: Next.js + FastAPI + Postgres/pgvector. AI: Gemini as primary
provider (free tier) behind a swappable `AIProvider` interface
(`LLM_PROVIDER` env var).

## 1. The thesis

Routing-only complaint apps already exist as hackathon projects (e.g.
"Campus Solver" from VIT Bhopal, "Campus AI"). CampusPluse's differentiator
has to be the parts most teams skip: similar-complaint detection,
recurring-problem detection, and an explainable smart-priority score. The
signature demo moment: submit 3 similar complaints from different tabs live
on stage and watch them merge into one recurring-issue card in seconds.

## 2. Architecture

Next.js (student app + admin console) → FastAPI service (owns every DB
write and every AI call) → Gemini provider (understand + embed) and
Postgres + pgvector (+ realtime change feed). Realtime pushes DB changes
straight to the browser — no polling.

## 3. Data model

See `CLAUDE.md` for the six-table schema; full DDL is in
`apps/api/app/db/migrations/versions/0001_init.py`.

## 4. Intelligence pipeline

1. **Multimodal understanding** — one Gemini call, description + photo,
   structured JSON output: category, severity (1–5), safety_flag,
   photo_matches_text, summary.
2. **Embedding** — `gemini-embedding-001`, `task_type=CLUSTERING`,
   truncated to 768 dims, embedded on the AI's normalized summary, not raw
   text.
3. **Similarity search** — pgvector cosine, scoped to same category +
   building + 14-day window. Thresholds in `CLAUDE.md`.
4. **Recurring detection** — connected components over the similarity
   graph; ≥3 independent students → `is_recurring = true`.
5. **Priority scoring** — explainable 4-term weighted formula, shown as a
   segmented bar, never a bare number.
6. **Routing** — deterministic category→department map + Gemini fallback
   for ambiguous free text, always one click from admin override.

## 5. Provider abstraction

`AIProvider` protocol (`understand_complaint`, `embed`), `GeminiProvider`
and `MockProvider` as concrete implementations, `get_provider()` factory
reads `LLM_PROVIDER`. Nothing outside `apps/api/app/ai/` imports a provider
SDK directly.

## 6. Realtime & admin dashboard

Location heatmap, recurring-issue leaderboard, explainable priority bar,
and an "Ask CampusPluse" natural-language query box over the admin data.

## 7. Spectacle features

Live merge-in-front-of-you (core), explainable priority breakdown (core),
photo-verification badge, Ask CampusPluse, auto-generated weekly digest, a
"chaos button" that streams synthetic complaints for a dramatic live demo
moment.

## 8. 48-hour timeline — 4 parallel tracks

- **Track A** — Data & backend core (schema, CRUD API, auth, deploy)
- **Track B** — Intelligence pipeline (Gemini provider, clustering,
  priority, NL query)
- **Track C** — Student experience (report form, photo upload, live status
  tracker)
- **Track D** — Admin command center (dashboard, realtime wiring, heatmap,
  digest)

Phases: 0–4h setup → 4–16h core build → 16h integration checkpoint →
16–36h intelligence + polish → 36h integration + seed data → 42–46h
hardening → 46–48h rehearse/buffer. For a 24h box: cut the digest, chaos
button and NL query; keep the live-merge moment and the priority bar.

## 9. Repo structure

```
campuspulse/
├─ apps/web/                apps/api/
│                            ├─ app/ai/         (provider.py, gemini.py, mock.py, schemas.py)
│                            ├─ app/pipeline/    (understand.py, cluster.py, priority.py)
│                            ├─ app/routers/
│                            └─ app/db/migrations/
├─ packages/shared-types/
├─ scripts/seed_demo.py
├─ docs/build-plan.md
└─ CLAUDE.md
```

## 10. Claude Code playbook

- `CLAUDE.md` at repo root, read before any track starts.
- One Claude Code session (or worktree) per track, kicked off with a
  concrete first prompt, not a vague one.
- Integration lead pass at hour 16 and hour 36 — a session reviews the
  cross-track diff specifically for API-contract mismatches.
- `scripts/seed_demo.py` built on day one — it's the demo fixture and the
  clustering test fixture.
- A focused test on the similarity-threshold logic protects the highest-
  value demo moment.

## 11. Demo script (<3 min)

Hook → submit a live complaint with a photo → trigger the merge (2 more
near-identical reports, live) → explain the priority bar → ask a
natural-language question in the admin console → close on the architecture
diagram and "the intelligence layer, not the form, is the product."

## 12. Risk & fallbacks

Rehearse the exact click sequence so live Gemini calls during judging are
few and known in advance. `MockProvider` is the automatic fallback on
error/timeout, not just a manual toggle. Check Gemini quota the morning of
the demo; use the mock provider by default in dev.
