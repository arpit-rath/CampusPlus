# shared-types

TypeScript types for the API surface.

Right now `apps/web/src/lib/api.ts` hand-maintains them, and that is a
deliberate choice rather than an unfinished one: there is exactly one
consumer, the types are read constantly while building the UI, and a
generated `index.ts` would be one more thing to regenerate and keep in sync
during a hackathon. Hand-written types that someone actually reads beat
generated types nobody looks at.

Generate them from the live OpenAPI schema when there is a second consumer
(a mobile client, a second service) or when the API surface stops changing
daily:

```bash
# with the API running on :8000
npx openapi-typescript http://localhost:8000/openapi.json -o packages/shared-types/index.ts
```

Then replace the hand-written interfaces in `apps/web/src/lib/api.ts` with
imports from here, keeping the `api` object and the realtime helper where
they are — those are client behaviour, not schema.

## Keeping the hand-written types honest until then

`apps/api/tests/test_api_basic.py::test_create_complaint_returns_the_full_frontend_contract`
asserts that every field `api.ts` reads is present in the API response. It is
the thing standing between a renamed backend column and a silently `undefined`
value in the dashboard, so add a field name to that test whenever you add one
to the `Complaint` interface.
