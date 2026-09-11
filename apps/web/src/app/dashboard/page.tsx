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
 * The panels are the same ones this screen has always had, and the rail
 * keeps them in the same order — what is on fire, what is systemic, what
 * needs a human decision, where it is, the digest, then the full queue. What
 * changed is that they are now sections rather than one long scroll: the
 * queue is the screen an operator lives in, and it used to be four panels
 * below the fold on every refresh.
 *
 * The selected section lives in the URL hash, so a reload keeps you where you
 * were and `/dashboard#queue` can be linked to directly.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { LiveIndicator, type ConnectionStatus } from "@/components/LiveIndicator";
import { ThemeToggle } from "@/components/ThemeToggle";
import { BrandMark } from "@/components/icons";
import { DashboardNav, SECTIONS, type DashboardSection } from "./DashboardNav";
import { RecurringLeaderboard } from "./RecurringLeaderboard";
import { AskCampusPlus } from "./AskCampusPlus";
import { LocationHeatmap } from "./LocationHeatmap";
import { SuggestedMerges } from "./SuggestedMerges";
import { ComplaintTable } from "./ComplaintTable";
import { DigestPanel } from "./DigestPanel";
import { Pagination } from "./Pagination";

/** Safety net only. The websocket is the real update path; this catches the
 *  case where the socket is up but an event was dropped. */
const BACKGROUND_REFRESH_MS = 30_000;

const DEFAULT_PAGE_SIZE = 25;

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

  const [section, setSection] = useState<DashboardSection>("overview");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

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
          : // Naming the fix here rather than only in the README: this
            // message is where someone actually is when the API is down, and
            // the script starts only whatever is missing.
            "Can't reach the API on :8000 — showing the last known data. " +
            "Run scripts/dev.ps1 to start it.",
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

  // --- section routing ------------------------------------------------
  // The hash is the source of truth, so the back button and a pasted
  // `#queue` link both work without pulling in a router.
  useEffect(() => {
    const fromHash = () => {
      const id = window.location.hash.replace("#", "");
      const match = SECTIONS.find((s) => s.id === id);
      if (match) setSection(match.id);
    };
    fromHash();
    window.addEventListener("hashchange", fromHash);
    return () => window.removeEventListener("hashchange", fromHash);
  }, []);

  const selectSection = useCallback((next: DashboardSection) => {
    setSection(next);
    // replace, not push: flipping between panels should not bury the page
    // the operator arrived from under six history entries.
    window.history.replaceState(null, "", `#${next}`);
  }, []);

  // --- paging ---------------------------------------------------------
  const filtersActive = Boolean(statusFilter || categoryFilter || recurringOnly);

  useEffect(() => {
    setPage(1);
  }, [statusFilter, categoryFilter, recurringOnly, pageSize]);

  const pageCount = Math.max(1, Math.ceil(complaints.length / pageSize));
  // Clamp rather than store: a websocket update can shrink the list under a
  // reader who is on the last page, and a page number past the end would
  // show them nothing at all.
  const currentPage = Math.min(page, pageCount);
  const visibleComplaints = useMemo(
    () => complaints.slice((currentPage - 1) * pageSize, currentPage * pageSize),
    [complaints, currentPage, pageSize],
  );

  const recurringCount = clusters.filter((c) => c.is_recurring).length;

  const meta = SECTIONS.find((s) => s.id === section)!;

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-ink/10 bg-paper/85 backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <Link
              href="/"
              className="inline-flex items-center gap-2 text-ink/60 transition-colors hover:text-ink"
              title="Back to the landing page"
            >
              <BrandMark className="h-[18px] w-[18px] text-signal-ink" />
              <span className="font-mono text-xs uppercase tracking-widest">CampusPlus</span>
            </Link>
            <span aria-hidden="true" className="h-5 w-px bg-ink/15" />
            <h1 className="text-lg font-bold tracking-tight sm:text-xl">Command center</h1>
          </div>

          <div className="flex items-center gap-3 sm:gap-4">
            {health && (
              <span
                className="hidden font-mono text-[10px] uppercase tracking-widest text-ink/50 sm:inline"
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
            <ThemeToggle />
          </div>
        </div>
      </header>

      <div className="flex flex-col gap-4 px-4 py-5 sm:px-6 lg:flex-row lg:gap-6">
        <aside className="lg:w-56 lg:shrink-0">
          <div className="lg:sticky lg:top-[84px]">
            <DashboardNav
              active={section}
              onSelect={selectSection}
              counts={{
                recurring: recurringCount,
                review: merges.length,
                queue: complaints.length,
              }}
            />
          </div>
        </aside>

        <main className="flex min-w-0 flex-1 flex-col gap-4">
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

          <div
            role="tabpanel"
            id={`panel-${section}`}
            aria-labelledby={`tab-${section}`}
            tabIndex={-1}
            className="flex flex-col gap-4"
          >
            <div>
              <h2 className="text-base font-semibold tracking-tight text-ink">
                {meta.label}
              </h2>
              <p className="text-xs text-ink/60">{meta.hint}</p>
            </div>

            {section === "overview" && (
              <>
                <StatsRow stats={stats} complaints={complaints} loading={loading} />
                <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
                  <div className="xl:col-span-2">
                    <RecurringLeaderboard clusters={clusters} loading={loading} />
                  </div>
                  <AskCampusPlus complaints={complaints} />
                </div>
              </>
            )}

            {section === "recurring" && (
              <>
                <RecurringLeaderboard clusters={clusters} loading={loading} />
                <p className="text-xs text-ink/60">
                  A cluster becomes recurring at three <em>independent</em> students, not
                  three reports — one student filing the same problem three times is one
                  problem, not a pattern.
                </p>
              </>
            )}

            {section === "review" &&
              (merges.length > 0 ? (
                <SuggestedMerges
                  merges={merges}
                  onResolved={(message) => {
                    announce(message);
                    refresh();
                  }}
                />
              ) : (
                <EmptyPanel
                  title="Nothing waiting for review"
                  body="Reports that match an existing one closely enough to be suspicious, but not closely enough to merge automatically, land here. The auto-merge threshold is 0.92 cosine similarity; anything from 0.75 up asks a human."
                />
              ))}

            {section === "map" && <LocationHeatmap complaints={complaints} clusters={clusters} />}

            {section === "digest" && <DigestPanel onChaos={announce} />}

            {section === "queue" && (
              <section className="rounded-xl border border-ink/10 bg-surface">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-ink/10 px-4 py-3">
                  <div>
                    <h3 className="text-sm font-semibold uppercase tracking-wide text-ink">
                      Complaint queue
                    </h3>
                    <p className="mt-0.5 text-xs text-ink/60">
                      {complaints.length} complaint{complaints.length === 1 ? "" : "s"},
                      highest priority first
                    </p>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <select
                      value={statusFilter}
                      onChange={(e) => setStatusFilter(e.target.value as ComplaintStatus | "")}
                      className="rounded-md border border-ink/15 bg-surface px-2 py-1.5 text-xs text-ink outline-none focus:border-signal"
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
                      className="rounded-md border border-ink/15 bg-surface px-2 py-1.5 text-xs text-ink outline-none focus:border-signal"
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
                        className="rounded-md px-2 py-1.5 text-xs text-ink/60 hover:text-ink"
                      >
                        Clear
                      </button>
                    )}
                  </div>
                </div>

                <ComplaintTable
                  complaints={visibleComplaints}
                  departments={departments}
                  loading={loading}
                  filtersActive={filtersActive}
                  onChanged={(message) => {
                    announce(message);
                    refresh();
                  }}
                />

                {complaints.length > 0 && (
                  <Pagination
                    total={complaints.length}
                    page={currentPage}
                    pageSize={pageSize}
                    onPage={setPage}
                    onPageSize={setPageSize}
                  />
                )}
              </section>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

function EmptyPanel({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-xl border border-dashed border-ink/15 bg-surface px-6 py-12 text-center">
      <p className="text-sm font-medium text-ink/80">{title}</p>
      <p className="mx-auto mt-1.5 max-w-md text-xs leading-relaxed text-ink/60">{body}</p>
    </div>
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
      accent: "text-hazard",
    },
    {
      label: "Needs review",
      value: stats?.pending_merges ?? 0,
      accent: "text-ink",
      hint: "Possible duplicates awaiting a human decision",
    },
  ];

  return (
    <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
      {tiles.map((tile) => (
        <div
          key={tile.label}
          className="rounded-xl border border-ink/10 bg-surface px-4 py-3"
          title={tile.hint}
        >
          <p className="text-[11px] uppercase tracking-wide text-ink/60">{tile.label}</p>
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
        <p className="text-xs text-ink/70">
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
        className="rounded-md border border-ink/20 bg-surface px-3 py-1.5 font-mono text-sm outline-none focus:border-signal"
      />
      <button
        type="submit"
        className="rounded-md bg-signal-fill px-3 py-1.5 text-sm font-medium text-on-signal"
      >
        Save
      </button>
    </form>
  );
}
