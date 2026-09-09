"use client";

/**
 * Recurring-issue leaderboard — the card the live-merge demo lands in.
 *
 * This reads real `complaint_clusters` rows from `/clusters`. The previous
 * version grouped complaints client-side by `category + building`, which is
 * a different and worse thing: two unrelated WiFi faults in one building
 * looked like a single recurring issue, and the cluster the backend actually
 * built was never shown at all. Cosine similarity decides what belongs
 * together; the UI's job is to display that decision, not re-guess it.
 *
 * Ranking is by *independent students*, not report count, matching the rule
 * that promotes a cluster to recurring in the first place.
 */

import Link from "next/link";
import type { Cluster } from "@/lib/api";
import { categoryLabel } from "@/lib/campus";

export function RecurringLeaderboard({
  clusters,
  loading,
  limit = 6,
}: {
  clusters: Cluster[];
  loading?: boolean;
  limit?: number;
}) {
  const ranked = [...clusters]
    .sort(
      (a, b) =>
        Number(b.is_recurring) - Number(a.is_recurring) ||
        b.independent_student_count - a.independent_student_count ||
        b.max_priority_score - a.max_priority_score,
    )
    .slice(0, limit);

  return (
    <section className="h-full rounded-xl border border-ink/10 bg-white p-4">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-ink">
            Recurring issues
          </h2>
          <p className="mt-0.5 text-xs text-ink/50">
            Clusters built by embedding similarity, ranked by how many
            independent students are affected
          </p>
        </div>
      </div>

      {loading && clusters.length === 0 ? (
        <div className="mt-4 flex flex-col gap-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-12 animate-pulse rounded-lg bg-ink/5" />
          ))}
        </div>
      ) : ranked.length === 0 ? (
        <div className="mt-4 rounded-lg border border-dashed border-ink/15 bg-ink/[0.02] px-4 py-8 text-center">
          <p className="text-sm font-medium text-ink/70">No clusters yet</p>
          <p className="mx-auto mt-1 max-w-xs text-xs text-ink/45">
            When two students report the same problem in the same building,
            they merge into one case here. Three independent students makes it
            a recurring issue.
          </p>
        </div>
      ) : (
        <ol className="mt-3 flex flex-col gap-2">
          {ranked.map((cluster, index) => (
            <li key={cluster.id}>
              <Link
                href={
                  cluster.representative_complaint_id
                    ? `/track/${cluster.representative_complaint_id}`
                    : "/dashboard"
                }
                className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 transition-colors hover:bg-ink/[0.04] ${
                  cluster.is_recurring
                    ? "border-critical/30 bg-critical/5"
                    : "border-ink/10"
                }`}
              >
                <span className="w-4 shrink-0 text-center font-mono text-xs text-ink/35">
                  {index + 1}
                </span>

                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium text-ink">
                      {categoryLabel(cluster.category_slug)}
                    </span>
                    {cluster.is_recurring && (
                      <span className="shrink-0 rounded-full bg-critical px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-white">
                        Recurring
                      </span>
                    )}
                    {cluster.safety_flag && (
                      <span className="shrink-0 rounded-full bg-[#8B2E8B]/15 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-[#8B2E8B]">
                        Safety
                      </span>
                    )}
                  </span>
                  <span className="block truncate text-xs text-ink/55">
                    {cluster.representative_summary ??
                      cluster.location_building ??
                      "Unspecified location"}
                  </span>
                  <span className="block truncate text-[11px] text-ink/35">
                    {cluster.location_building ?? "Unspecified building"} · last report{" "}
                    {new Date(cluster.last_seen).toLocaleTimeString()}
                  </span>
                </span>

                <span className="shrink-0 text-right">
                  <span
                    className={`block font-mono text-xl font-bold leading-none tabular-nums ${
                      cluster.is_recurring ? "text-critical" : "text-ink/70"
                    }`}
                  >
                    {cluster.independent_student_count}
                  </span>
                  <span className="block text-[9px] uppercase tracking-wide text-ink/40">
                    students
                  </span>
                  {cluster.member_count !== cluster.independent_student_count && (
                    <span className="block font-mono text-[10px] text-ink/30">
                      {cluster.member_count} reports
                    </span>
                  )}
                </span>
              </Link>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
