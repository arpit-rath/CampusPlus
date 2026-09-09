/**
 * Admin command center (Track D — build-plan.md §6, §7). Scanned, not
 * read: a summary strip, the recurring-issue leaderboard (the live-merge
 * demo moment) and the Ask CampusPluse box up top, then the full
 * priority-sorted complaint list.
 *
 * Realtime: this polls `api.listComplaints()` on an interval to approximate
 * the live feed the build plan describes (CLAUDE.md's Postgres→websocket
 * `/ws/complaints` fallback). Swapping this for a real websocket
 * subscription is a stretch goal — see the TODO below — but polling gives
 * the same "the dashboard just updates" effect for a demo.
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type Complaint, type ComplaintStatus } from "@/lib/api";
import { PriorityBar } from "./PriorityBar";
import { RecurringLeaderboard } from "./RecurringLeaderboard";
import { AskCampusPulse } from "./AskCampusPulse";
import { LocationHeatmap } from "./LocationHeatmap";

const POLL_INTERVAL_MS = 4000;

// TODO(stretch goal): replace this poll loop with a subscription to the
// FastAPI `/ws/complaints` fallback (or Supabase Realtime) once that's
// wired up — CLAUDE.md's "Realtime" section. The component shape below
// (setComplaints on every update) doesn't need to change, only how updates
// arrive.

const STATUS_STYLES: Record<
  ComplaintStatus,
  { label: string; className: string }
> = {
  open: { label: "Open", className: "bg-critical/10 text-critical" },
  in_progress: { label: "In progress", className: "bg-signal/10 text-signal" },
  resolved: { label: "Resolved", className: "bg-calm/10 text-calm" },
};

function StatusPill({ status }: { status: ComplaintStatus }) {
  const style = STATUS_STYLES[status];
  return (
    <span
      className={`inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${style.className}`}
    >
      {style.label}
    </span>
  );
}

function formatCategory(slug: string): string {
  return slug
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export default function DashboardPage() {
  const [complaints, setComplaints] = useState<Complaint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await api.listComplaints();
      setComplaints(data);
      setLastUpdated(new Date());
      setError(null);
    } catch (err) {
      // Keep whatever data we already have on screen; surface a stale
      // banner rather than blanking the dashboard on a transient failure.
      setError(
        err instanceof ApiError
          ? `API error (${err.status}) — showing last known data.`
          : "Can't reach the API — showing last known data.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [refresh]);

  const sorted = [...complaints].sort(
    (a, b) => b.priority_score - a.priority_score,
  );

  const counts = {
    open: complaints.filter((c) => c.status === "open").length,
    in_progress: complaints.filter((c) => c.status === "in_progress").length,
    resolved: complaints.filter((c) => c.status === "resolved").length,
    recurring: complaints.filter((c) => c.is_recurring).length,
  };

  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 px-6 py-8">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-xs uppercase tracking-widest text-ink/50">
            CampusPluse
          </p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight">
            Admin command center
          </h1>
        </div>
        <p className="font-mono text-xs text-ink/40">
          {loading
            ? "Loading…"
            : lastUpdated
              ? `Updated ${lastUpdated.toLocaleTimeString()} · refreshes every ${POLL_INTERVAL_MS / 1000}s`
              : "No data yet"}
        </p>
      </header>

      {error && (
        <p className="rounded-md bg-critical/10 px-3 py-2 text-sm text-critical">
          {error}
        </p>
      )}

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <SummaryTile label="Open" value={counts.open} accent="text-critical" />
        <SummaryTile
          label="In progress"
          value={counts.in_progress}
          accent="text-signal"
        />
        <SummaryTile label="Resolved" value={counts.resolved} accent="text-calm" />
        <SummaryTile
          label="Recurring"
          value={counts.recurring}
          accent="text-critical"
        />
      </section>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <RecurringLeaderboard complaints={complaints} />
        </div>
        <AskCampusPulse />
      </div>

      <LocationHeatmap complaints={complaints} />

      <section className="rounded-lg border border-ink/10 bg-white">
        <div className="border-b border-ink/10 px-4 py-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-ink">
            All complaints
          </h2>
          <p className="mt-0.5 text-xs text-ink/50">
            Sorted by priority score, highest first
          </p>
        </div>

        {!loading && sorted.length === 0 ? (
          <p className="px-4 py-8 text-center text-sm text-ink/50">
            No complaints yet.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead>
                <tr className="border-b border-ink/10 text-xs uppercase tracking-wide text-ink/40">
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Category</th>
                  <th className="px-4 py-2 font-medium">Building</th>
                  <th className="px-4 py-2 font-medium">Priority</th>
                  <th className="px-4 py-2 font-medium">Recurring</th>
                  <th className="px-4 py-2 font-medium">Reported</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((c) => (
                  <tr
                    key={c.id}
                    className="border-b border-ink/5 last:border-0 hover:bg-ink/[0.03]"
                  >
                    <td className="px-4 py-3">
                      <StatusPill status={c.status} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-medium text-ink">
                        {formatCategory(c.category_slug ?? "other")}
                      </div>
                      <div className="max-w-xs truncate text-xs text-ink/50">
                        {c.ai_summary ?? c.raw_description}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-ink/70">
                      {c.location_building ?? "—"}
                      {c.location_room ? ` · ${c.location_room}` : ""}
                    </td>
                    <td className="px-4 py-3">
                      <PriorityBar
                        breakdown={c.priority_breakdown}
                        score={c.priority_score}
                      />
                    </td>
                    <td className="px-4 py-3">
                      {c.is_recurring ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-critical/10 px-2 py-0.5 text-xs font-medium text-critical">
                          ×{c.cluster_member_count}
                        </span>
                      ) : (
                        <span className="text-ink/20">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-xs text-ink/50">
                      {new Date(c.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}

function SummaryTile({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent: string;
}) {
  return (
    <div className="rounded-lg border border-ink/10 bg-white px-4 py-3">
      <p className="text-xs uppercase tracking-wide text-ink/50">{label}</p>
      <p className={`mt-1 font-mono text-2xl font-bold ${accent}`}>{value}</p>
    </div>
  );
}
