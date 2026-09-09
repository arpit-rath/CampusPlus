/**
 * Recurring-issue leaderboard — the component that makes the "three tabs
 * merge into one card live" demo moment visible (build-plan.md §1, §7).
 * Kept prominent near the top of the dashboard, not buried in the table.
 *
 * ASSUMPTION: the `/complaints` list endpoint returns one row per
 * complaint, not one row per cluster — a recurring cluster of 3 reports
 * shows up as 3 rows all carrying the same `cluster_member_count`. Since
 * there's no dedicated `/clusters` endpoint in api.ts yet, this component
 * approximates cluster grouping client-side by (category_slug +
 * location_building) and keeps one representative row per group. If the
 * backend later exposes real cluster ids, swap the dedupe key for that —
 * flagging this for the integration pass.
 */

"use client";

import Link from "next/link";
import type { Complaint } from "@/lib/api";

interface RecurringLeaderboardProps {
  complaints: Complaint[];
  limit?: number;
}

function formatCategory(slug: string): string {
  return slug
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function RecurringLeaderboard({
  complaints,
  limit = 6,
}: RecurringLeaderboardProps) {
  const byCluster = new Map<string, Complaint>();
  for (const c of complaints) {
    if (!c.is_recurring) continue;
    const key = `${c.category_slug ?? "other"}__${c.location_building ?? "unspecified"}`;
    const existing = byCluster.get(key);
    if (
      !existing ||
      c.cluster_member_count > existing.cluster_member_count ||
      (c.cluster_member_count === existing.cluster_member_count &&
        c.priority_score > existing.priority_score)
    ) {
      byCluster.set(key, c);
    }
  }

  const top = Array.from(byCluster.values())
    .sort((a, b) => b.cluster_member_count - a.cluster_member_count)
    .slice(0, limit);

  return (
    <section className="rounded-lg border border-ink/10 bg-white p-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-ink">
            Recurring issues
          </h2>
          <p className="mt-0.5 text-xs text-ink/50">
            Clusters of 3+ independent reports, ranked by size
          </p>
        </div>
        <span className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-widest text-critical">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-critical" />
          Live
        </span>
      </div>

      {top.length === 0 ? (
        <p className="mt-4 rounded-md bg-ink/5 px-3 py-6 text-center text-sm text-ink/50">
          No recurring issues yet — this card fills in live as duplicate
          reports merge into a cluster.
        </p>
      ) : (
        <ol className="mt-3 flex flex-col gap-2">
          {top.map((c, i) => (
            <li key={`${c.category_slug}-${c.location_building}-${c.id}`}>
              <Link
                href={`/track/${c.id}`}
                className={`flex items-center gap-3 rounded-md border px-3 py-2 transition-colors hover:bg-ink/5 ${
                  i === 0
                    ? "border-critical/30 bg-critical/5"
                    : "border-ink/10 bg-transparent"
                }`}
              >
                <span className="w-5 shrink-0 text-center font-mono text-xs text-ink/40">
                  {i + 1}
                </span>
                <span className="flex-1 min-w-0">
                  <span className="block truncate text-sm font-medium text-ink">
                    {formatCategory(c.category_slug ?? "other")}
                  </span>
                  <span className="block truncate text-xs text-ink/50">
                    {c.location_building ?? "Unspecified building"}
                  </span>
                </span>
                <span className="shrink-0 text-right">
                  <span className="block font-mono text-lg font-bold leading-none text-critical">
                    {c.cluster_member_count}
                  </span>
                  <span className="block text-[10px] uppercase tracking-wide text-ink/40">
                    reports
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
