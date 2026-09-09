"use client";

/**
 * Admin command center.
 *
 * Realtime, not polling: it holds one websocket to `/ws/complaints` and
 * refetches on each event. That is what makes the signature demo work —
 * three students submit from three tabs and this screen reacts as it
 * happens, including the moment a cluster flips to recurring, which is
 * announced by a dedicated `cluster.recurring` event and surfaced as a
 * banner rather than left for someone to notice in a table.
 *
 * Layout is ordered by what an operator needs first: what is on fire
 * (stats), what is systemic (recurring clusters), what needs a human
 * decision (suggested merges), where it is (map), then the full queue.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  api,
  ApiError,
  getAdminToken,
  setAdminToken,
  subscribeToRealtime,
  type AdminStats,
  type Cluster,
  type Complaint,
  type ComplaintStatus,
  type Department,
  type Health,
  type SuggestedMerge,
} from "@/lib/api";
import { categoryLabel, CATEGORY_SLUGS } from "@/lib/campus";
import { PriorityBar } from "@/components/PriorityBar";
import { LiveIndicator, type ConnectionStatus } from "@/components/LiveIndicator";
import { RecurringLeaderboard } from "./RecurringLeaderboard";
import { AskCampusPlus } from "./AskCampusPlus";
import { LocationHeatmap } from "./LocationHeatmap";
import { SuggestedMerges } from "./SuggestedMerges";
import { ComplaintTable } from "./ComplaintTable";
import { DigestPanel } from "./DigestPanel";

/** Safety net only. The websocket is the real update path; this catches the
 *  case where the socket is up but an event was dropped. */
const BACKGROUND_REFRESH_MS = 30_000;

export default function DashboardPage() {
  const [complaints, setComplaints] = useState<Complaint[]>([]);
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [merges, setMerges] = useState<SuggestedMerge[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [health, setHealth] = useState<Health | null>(null);

  const [connection, setConnection] = useState<ConnectionStatus>("connecting");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [needsToken, setNeedsToken] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);

  const [statusFilter, setStatusFilter] = useState<ComplaintStatus | "">("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [recurringOnly, setRecurringOnly] = useState(false);

  const flashTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const announce = useCallback((message: string) => {
    setFlash(message);
    if (flashTimer.current) clearTimeout(flashTimer.current);
    flashTimer.current = setTimeout(() => setFlash(null), 6000);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [nextComplaints, nextClusters] = await Promise.all([
        api.listComplaints({
          status: statusFilter || undefined,
          category: categoryFilter || undefined,
          recurring_only: recurringOnly || undefined,
        }),
        api.listClusters(),
      ]);
      setComplaints(nextComplaints);
      setClusters(nextClusters);
      setError(null);

      // Admin-gated reads are separate: if the token is wrong, the public
      // half of the dashboard should still render rather than going blank.
      try {
        const [nextStats, nextMerges, nextDepartments] = await Promise.all([
          api.adminStats(),
          api.listSuggestedMerges(),
          api.listDepartments(),
        ]);
        setStats(nextStats);
        setMerges(nextMerges);
        setDepartments(nextDepartments);
        setNeedsToken(false);
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) setNeedsToken(true);
      }
    } catch (err) {
      setError(
        err instanceof ApiError
          ? `API error (${err.status}) — showing the last known data.`
          : "Can't reach the API — showing the last known data.",
      );
    } finally {
      setLoading(false);
    }
  }, [statusFilter, categoryFilter, recurringOnly]);

  useEffect(() => {
    refresh();
    api.health().then(setHealth).catch(() => setHealth(null));
  }, [refresh]);

  useEffect(() => {
    return subscribeToRealtime(
      (event) => {
        if (event.type === "cluster.recurring") {
          announce(
            `Recurring issue detected in ${event.data.location_building ?? "campus"} — ` +
              `${event.data.independent_student_count} independent students reporting.`,
          );
        } else if (event.type === "complaint.created") {
          if (event.data.similarity_label === "duplicate") {
            announce(
              `New report auto-merged as a duplicate ` +
                `(${((event.data.best_match_score ?? 0) * 100).toFixed(0)}% similar).`,
            );
          } else if (event.data.similarity_label === "suggested_merge") {
            announce("New report flagged as a possible duplicate — awaiting review.");
          }
        }
        refresh();
      },
      (status) => {
        setConnection(status);
        if (status === "live") refresh();
      },
    );
  }, [refresh, announce]);

  useEffect(() => {
    const interval = setInterval(refresh, BACKGROUND_REFRESH_MS);
    return () => clearInterval(interval);
  }, [refresh]);

  const filtersActive = Boolean(statusFilter || categoryFilter || recurringOnly);

  return (
    <main className="mx-auto flex min-h-screen max-w-7xl flex-col gap-5 px-5 py-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Link
            href="/"
            className="font-mono text-xs uppercase tracking-widest text-ink/50 hover:text-ink"
          >
            CampusPlus
          </Link>
          <h1 className="mt-1 text-2xl font-bold tracking-tight">Command center</h1>
        </div>
        <div className="flex items-center gap-4">
          {health && (
            <span
              className="font-mono text-[10px] uppercase tracking-widest text-ink/40"
              title={
                health.llm_effective === "gemini"
                  ? "Complaints are being analyzed by Gemini."
                  : "Running on the deterministic mock provider — no model quota is being spent."
              }
            >
              AI: {health.llm_effective}
            </span>
          )}
          <LiveIndicator status={connection} />
        </div>
      </header>

      {flash && (
        <div
          role="status"
          className="animate-[fadeIn_150ms_ease-out] rounded-lg border border-signal/40 bg-signal/10 px-4 py-2.5 text-sm font-medium text-signal"
        >
          {flash}
        </div>
      )}

      {error && (
        <p className="rounded-lg border border-critical/30 bg-critical/10 px-3 py-2 text-sm text-critical">
          {error}
        </p>
      )}

      {needsToken && <AdminTokenPrompt onSaved={refresh} />}

      <StatsRow stats={stats} complaints={complaints} loading={loading} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <RecurringLeaderboard clusters={clusters} loading={loading} />
        </div>
        <AskCampusPlus complaints={complaints} />
      </div>

      {merges.length > 0 && (
        <SuggestedMerges
          merges={merges}
          onResolved={(message) => {
            announce(message);
            refresh();
          }}
        />
      )}

      <LocationHeatmap complaints={complaints} clusters={clusters} />

      <DigestPanel onChaos={announce} />

      <section className="rounded-xl border border-ink/10 bg-white">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-ink/10 px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink">
              Complaint queue
            </h2>
            <p className="mt-0.5 text-xs text-ink/50">
              {complaints.length} complaint{complaints.length === 1 ? "" : "s"}, highest
              priority first
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as ComplaintStatus | "")}
              className="rounded-md border border-ink/15 bg-white px-2 py-1.5 text-xs text-ink outline-none focus:border-signal"
              aria-label="Filter by status"
            >
              <option value="">All statuses</option>
              <option value="open">Open</option>
              <option value="in_progress">In progress</option>
              <option value="resolved">Resolved</option>
            </select>

            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="rounded-md border border-ink/15 bg-white px-2 py-1.5 text-xs text-ink outline-none focus:border-signal"
              aria-label="Filter by category"
            >
              <option value="">All categories</option>
              {CATEGORY_SLUGS.map((slug) => (
                <option key={slug} value={slug}>
                  {categoryLabel(slug)}
                </option>
              ))}
            </select>

            <label className="flex cursor-pointer items-center gap-1.5 rounded-md border border-ink/15 px-2 py-1.5 text-xs text-ink">
              <input
                type="checkbox"
                checked={recurringOnly}
                onChange={(e) => setRecurringOnly(e.target.checked)}
                className="accent-[#B4402F]"
              />
              Recurring only
            </label>

            {filtersActive && (
              <button
                onClick={() => {
                  setStatusFilter("");
                  setCategoryFilter("");
                  setRecurringOnly(false);
                }}
                className="rounded-md px-2 py-1.5 text-xs text-ink/50 hover:text-ink"
              >
                Clear
              </button>
            )}
          </div>
        </div>

        <ComplaintTable
          complaints={complaints}
          departments={departments}
          loading={loading}
          filtersActive={filtersActive}
          onChanged={(message) => {
            announce(message);
            refresh();
          }}
        />
      </section>
    </main>
  );
}

function StatsRow({
  stats,
  complaints,
  loading,
}: {
  stats: AdminStats | null;
  complaints: Complaint[];
  loading: boolean;
}) {
  // Fall back to counting what is on screen when the admin-gated stats
  // endpoint is unavailable, so the header is never blank.
  const tiles = [
    {
      label: "Open",
      value: stats?.open ?? complaints.filter((c) => c.status === "open").length,
      accent: "text-critical",
    },
    {
      label: "In progress",
      value: stats?.in_progress ?? complaints.filter((c) => c.status === "in_progress").length,
      accent: "text-signal",
    },
    {
      label: "Resolved",
      value: stats?.resolved ?? complaints.filter((c) => c.status === "resolved").length,
      accent: "text-calm",
    },
    {
      label: "Recurring",
      value: stats?.recurring_clusters ?? 0,
      accent: "text-critical",
      hint: "Clusters with 3+ independent students",
    },
    {
      label: "Safety flags",
      value: stats?.safety_flagged ?? complaints.filter((c) => c.safety_flag).length,
      accent: "text-[#8B2E8B]",
    },
    {
      label: "Needs review",
      value: stats?.pending_merges ?? 0,
      accent: "text-ink",
      hint: "Possible duplicates awaiting a human decision",
    },
  ];

  return (
    <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      {tiles.map((tile) => (
        <div
          key={tile.label}
          className="rounded-xl border border-ink/10 bg-white px-4 py-3"
          title={tile.hint}
        >
          <p className="text-[11px] uppercase tracking-wide text-ink/50">{tile.label}</p>
          <p className={`mt-1 font-mono text-2xl font-bold tabular-nums ${tile.accent}`}>
            {loading ? "—" : tile.value}
          </p>
        </div>
      ))}
    </section>
  );
}

function AdminTokenPrompt({ onSaved }: { onSaved: () => void }) {
  const [value, setValue] = useState(getAdminToken() ?? "");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setAdminToken(value.trim() || null);
        onSaved();
      }}
      className="flex flex-wrap items-end gap-3 rounded-xl border border-signal/40 bg-signal/5 px-4 py-3"
    >
      <div className="flex-1">
        <p className="text-sm font-medium text-ink">Admin token required</p>
        <p className="text-xs text-ink/60">
          This API has <code className="font-mono">ADMIN_TOKEN</code> set. Enter it to
          manage statuses, routing and merges. It is stored in this browser only —
          never bundled into the app.
        </p>
      </div>
      <input
        type="password"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="X-Admin-Token"
        className="rounded-md border border-ink/20 bg-white px-3 py-1.5 font-mono text-sm outline-none focus:border-signal"
      />
      <button
        type="submit"
        className="rounded-md bg-signal px-3 py-1.5 text-sm font-medium text-white"
      >
        Save
      </button>
    </form>
  );
}
