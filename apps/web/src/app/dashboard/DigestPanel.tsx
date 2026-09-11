"use client";

/**
 * Auto-generated operational digest, plus the demo "chaos button".
 *
 * The digest is pure aggregation over real rows on the backend — no model
 * call — so it cannot drift from what the rest of the dashboard shows and
 * costs nothing to open on stage.
 *
 * The chaos button lives here rather than in the header because it is a
 * demo device, not an operational control, and it should take a deliberate
 * click to find. It streams synthetic complaints through the *real* pipeline
 * (see `app/pipeline/chaos.py`), so what lights up afterwards is the system
 * working, not an animation.
 */

import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type Digest } from "@/lib/api";
import { categoryLabel } from "@/lib/campus";

const WINDOWS = [
  { days: 1, label: "24h" },
  { days: 7, label: "7d" },
  { days: 30, label: "30d" },
];

export function DigestPanel({ onChaos }: { onChaos: (message: string) => void }) {
  const [digest, setDigest] = useState<Digest | null>(null);
  const [windowDays, setWindowDays] = useState(7);
  const [open, setOpen] = useState(false);
  const [chaosBusy, setChaosBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setDigest(await api.digest(windowDays));
      setError(null);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "Needs an admin token."
          : "Couldn't load the digest.",
      );
    }
  }, [windowDays]);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  const fireChaos = async () => {
    setChaosBusy(true);
    setError(null);
    try {
      const result = await api.chaos(6);
      onChaos(
        `Chaos: ${result.submitted} synthetic reports submitted, ` +
          `${result.merged} auto-merged` +
          (result.new_clusters_recurring
            ? `, ${result.new_clusters_recurring} cluster(s) became recurring.`
            : "."),
      );
      if (open) load();
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "Needs an admin token."
          : "Couldn't run the chaos burst.",
      );
    } finally {
      setChaosBusy(false);
    }
  };

  return (
    <section className="rounded-xl border border-ink/10 bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-2 text-left"
          aria-expanded={open}
        >
          <span
            className={`text-muted transition-transform ${open ? "rotate-90" : ""}`}
            aria-hidden
          >
            ▸
          </span>
          <span>
            <span className="block text-sm font-semibold uppercase tracking-wide text-ink">
              Operations digest
            </span>
            <span className="block text-xs text-muted">
              Aggregated from real complaint rows — no model involved
            </span>
          </span>
        </button>

        <div className="flex items-center gap-2">
          {open && (
            <div className="flex rounded-md border border-ink/15">
              {WINDOWS.map((w) => (
                <button
                  key={w.days}
                  onClick={() => setWindowDays(w.days)}
                  className={`px-2.5 py-1 text-xs font-medium transition-colors first:rounded-l-md last:rounded-r-md ${
                    windowDays === w.days
                      ? "bg-ink text-paper"
                      : "text-muted hover:bg-ink/5"
                  }`}
                >
                  {w.label}
                </button>
              ))}
            </div>
          )}
          <button
            onClick={fireChaos}
            disabled={chaosBusy}
            title="Submit a burst of synthetic complaints through the real pipeline — a demo device, not a shortcut: they are understood, embedded, matched and clustered exactly like a student's report."
            className="btn btn-sm border border-signal/40 bg-signal/10 font-semibold text-signal-ink hover:bg-signal/20"
          >
            {chaosBusy ? "Running…" : "⚡ Chaos burst"}
          </button>
        </div>
      </div>

      {error && (
        <p className="mx-4 mb-3 rounded-md border border-critical/25 bg-critical/5 px-2.5 py-1.5 text-xs text-critical">
          {error}
        </p>
      )}

      {open && digest && (
        <div className="border-t border-ink/10 px-4 py-4">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Metric label="Reported" value={digest.total_complaints} />
            <Metric label="Resolved" value={digest.resolved_complaints} />
            <Metric label="Recurring clusters" value={digest.recurring_clusters} />
            <Metric label="Safety flagged" value={digest.safety_flagged} />
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Ranking title="Worst locations" rows={digest.top_buildings} />
            <Ranking
              title="By category"
              rows={digest.top_categories.map((r) => ({
                label: categoryLabel(r.label),
                value: r.value,
              }))}
            />
          </div>

          {digest.headline_issues.length > 0 && (
            <div className="mt-4">
              <p className="text-[11px] uppercase tracking-wide text-muted">
                Headline issues
              </p>
              <ol className="mt-1.5 flex flex-col gap-1">
                {digest.headline_issues.map((issue) => (
                  <li key={issue.id} className="flex items-baseline gap-2 text-xs">
                    <span className="font-mono tabular-nums text-muted">
                      {issue.priority_score.toFixed(2)}
                    </span>
                    <span className="truncate text-ink/75">
                      {issue.ai_summary ?? issue.raw_description}
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          <p className="mt-4 font-mono text-[10px] text-muted">
            Generated {new Date(digest.generated_at).toLocaleString()} · last{" "}
            {digest.window_days} day(s)
          </p>
        </div>
      )}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-0.5 font-mono text-xl font-bold tabular-nums text-ink">{value}</p>
    </div>
  );
}

function Ranking({
  title,
  rows,
}: {
  title: string;
  rows: { label: string; value: string }[];
}) {
  const max = Math.max(1, ...rows.map((r) => Number(r.value) || 0));
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-muted">{title}</p>
      {rows.length === 0 ? (
        <p className="mt-1 text-xs text-muted">Nothing in this window.</p>
      ) : (
        <ul className="mt-1.5 flex flex-col gap-1">
          {rows.map((row) => (
            <li key={row.label} className="flex items-center gap-2 text-xs">
              <span className="w-32 shrink-0 truncate text-ink/70">{row.label}</span>
              <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink/10">
                <span
                  className="block h-full rounded-full bg-signal"
                  style={{ width: `${((Number(row.value) || 0) / max) * 100}%` }}
                />
              </span>
              <span className="w-6 shrink-0 text-right font-mono tabular-nums text-muted">
                {row.value}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
