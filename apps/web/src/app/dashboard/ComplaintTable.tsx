"use client";

/**
 * The operational queue: every complaint, with the actions an admin takes.
 *
 * A row expands in place rather than navigating away, because the work is
 * always the same short loop — read the summary, change the status, maybe
 * re-route it — and a page transition per complaint turns a two-minute
 * triage pass into a five-minute one.
 *
 * Status and routing controls write through the admin API and report
 * failures inline; nothing here mutates local state optimistically, so what
 * is on screen is always what the database said.
 */

import { Fragment, useState } from "react";
import Link from "next/link";
import {
  api,
  ApiError,
  photoUrl,
  type Complaint,
  type ComplaintStatus,
  type Department,
} from "@/lib/api";
import { categoryLabel, CATEGORY_SLUGS } from "@/lib/campus";
import { PriorityBar } from "@/components/PriorityBar";

const STATUS_STYLES: Record<ComplaintStatus, { label: string; className: string }> = {
  open: { label: "Open", className: "bg-critical/10 text-critical" },
  in_progress: { label: "In progress", className: "bg-signal/10 text-signal" },
  resolved: { label: "Resolved", className: "bg-calm/10 text-calm" },
};

const NEXT_STATUS: Record<ComplaintStatus, ComplaintStatus[]> = {
  open: ["in_progress", "resolved"],
  in_progress: ["resolved", "open"],
  resolved: ["open"],
};

export function ComplaintTable({
  complaints,
  departments,
  loading,
  filtersActive,
  onChanged,
}: {
  complaints: Complaint[];
  departments: Department[];
  loading: boolean;
  filtersActive: boolean;
  onChanged: (message: string) => void;
}) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const act = async (id: string, run: () => Promise<unknown>, message: string) => {
    setBusyId(id);
    setError(null);
    try {
      await run();
      onChanged(message);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "That action needs an admin token."
          : err instanceof ApiError
            ? err.message
            : "Couldn't reach the API.",
      );
    } finally {
      setBusyId(null);
    }
  };

  if (loading && complaints.length === 0) {
    return (
      <div className="flex flex-col gap-2 p-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-12 animate-pulse rounded-lg bg-ink/5" />
        ))}
      </div>
    );
  }

  if (complaints.length === 0) {
    return (
      <div className="px-4 py-12 text-center">
        <p className="text-sm font-medium text-ink/70">
          {filtersActive ? "Nothing matches these filters" : "No complaints yet"}
        </p>
        <p className="mx-auto mt-1 max-w-sm text-xs text-ink/45">
          {filtersActive ? (
            "Try clearing a filter."
          ) : (
            <>
              Submit one from the{" "}
              <Link href="/report" className="underline">
                report form
              </Link>
              , or seed the demo data with{" "}
              <code className="font-mono">python scripts/seed_demo.py --post</code>.
            </>
          )}
        </p>
      </div>
    );
  }

  return (
    <>
      {error && (
        <p className="mx-4 mt-3 rounded-md border border-critical/25 bg-critical/5 px-2.5 py-1.5 text-xs text-critical">
          {error}
        </p>
      )}

      <div className="overflow-x-auto">
        <table className="w-full min-w-[860px] text-left text-sm">
          <thead>
            <tr className="border-b border-ink/10 text-[11px] uppercase tracking-wide text-ink/40">
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 font-medium">Issue</th>
              <th className="px-4 py-2 font-medium">Location</th>
              <th className="px-4 py-2 font-medium">Department</th>
              <th className="px-4 py-2 font-medium">Priority</th>
              <th className="px-4 py-2 font-medium">Cluster</th>
              <th className="px-4 py-2 font-medium">Reported</th>
            </tr>
          </thead>
          <tbody>
            {complaints.map((complaint) => {
              const expanded = expandedId === complaint.id;
              const status = STATUS_STYLES[complaint.status];
              return (
                <Fragment key={complaint.id}>
                  <tr
                    onClick={() => setExpandedId(expanded ? null : complaint.id)}
                    className={`cursor-pointer border-b border-ink/5 transition-colors hover:bg-ink/[0.03] ${
                      expanded ? "bg-ink/[0.03]" : ""
                    } ${complaint.safety_flag ? "border-l-2 border-l-[#8B2E8B]" : ""}`}
                  >
                    <td className="px-4 py-3">
                      <span
                        className={`inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${status.className}`}
                      >
                        {status.label}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        <span className="font-medium text-ink">
                          {categoryLabel(complaint.category_slug)}
                        </span>
                        {complaint.safety_flag && (
                          <span className="rounded bg-[#8B2E8B]/15 px-1 py-0.5 text-[9px] font-bold uppercase tracking-wider text-[#8B2E8B]">
                            Safety
                          </span>
                        )}
                        {complaint.photo_matches_text && (
                          <span
                            className="rounded bg-calm/15 px-1 py-0.5 text-[9px] font-bold uppercase tracking-wider text-calm"
                            title="A photo was attached and the model judged it to corroborate the description"
                          >
                            Photo ✓
                          </span>
                        )}
                      </div>
                      <div className="max-w-xs truncate text-xs text-ink/50">
                        {complaint.ai_summary ?? complaint.raw_description}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-ink/70">
                      {complaint.location_building ?? "—"}
                      {complaint.location_room && (
                        <span className="text-ink/40"> · {complaint.location_room}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-ink/70">
                      {complaint.department_name ?? "—"}
                      {complaint.department_overridden && (
                        <span
                          className="ml-1 text-ink/35"
                          title="Manually re-routed by an admin"
                        >
                          (override)
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <PriorityBar
                        breakdown={complaint.priority_breakdown}
                        score={complaint.priority_score}
                        compact
                      />
                    </td>
                    <td className="px-4 py-3">
                      {complaint.cluster_id ? (
                        <span
                          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${
                            complaint.is_recurring
                              ? "bg-critical/10 text-critical"
                              : "bg-ink/5 text-ink/60"
                          }`}
                          title={`${complaint.cluster_member_count} reports from ${complaint.independent_student_count} independent students`}
                        >
                          {complaint.independent_student_count} student
                          {complaint.independent_student_count === 1 ? "" : "s"}
                        </span>
                      ) : complaint.suggested_match_complaint_id ? (
                        <span className="rounded-full bg-signal/10 px-2 py-0.5 text-xs font-medium text-signal">
                          review
                        </span>
                      ) : (
                        <span className="text-ink/20">—</span>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-ink/50">
                      {new Date(complaint.created_at).toLocaleString()}
                    </td>
                  </tr>

                  {expanded && (
                    <tr className="border-b border-ink/5 bg-ink/[0.02]">
                      <td colSpan={7} className="px-4 py-4">
                        <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
                          <div className="lg:col-span-2">
                            <p className="text-[11px] uppercase tracking-wide text-ink/40">
                              Original report
                            </p>
                            <p className="mt-1 text-sm text-ink/80">
                              {complaint.raw_description}
                            </p>
                            <p className="mt-1 font-mono text-[11px] text-ink/35">
                              #{complaint.id.slice(0, 8)} ·{" "}
                              {complaint.student_id ?? "anonymous"} · severity{" "}
                              {complaint.severity ?? "—"}/5
                            </p>

                            {complaint.photo_url && (
                              /* eslint-disable-next-line @next/next/no-img-element */
                              <img
                                src={photoUrl(complaint.photo_url) ?? ""}
                                alt="Reported issue"
                                className="mt-3 max-h-44 rounded-lg border border-ink/10 object-cover"
                              />
                            )}

                            <div className="mt-4 max-w-md">
                              <p className="text-[11px] uppercase tracking-wide text-ink/40">
                                Why this priority
                              </p>
                              <div className="mt-1.5">
                                <PriorityBar
                                  breakdown={complaint.priority_breakdown}
                                  score={complaint.priority_score}
                                  showLegend
                                />
                              </div>
                            </div>
                          </div>

                          <div className="flex flex-col gap-4">
                            <div>
                              <p className="text-[11px] uppercase tracking-wide text-ink/40">
                                Status
                              </p>
                              <div className="mt-1.5 flex flex-wrap gap-1.5">
                                {NEXT_STATUS[complaint.status].map((next) => (
                                  <button
                                    key={next}
                                    disabled={busyId === complaint.id}
                                    onClick={() =>
                                      act(
                                        complaint.id,
                                        () => api.updateStatus(complaint.id, { status: next }),
                                        `#${complaint.id.slice(0, 8)} marked ${STATUS_STYLES[next].label.toLowerCase()}.`,
                                      )
                                    }
                                    className="rounded-md border border-ink/20 px-2.5 py-1 text-xs font-medium text-ink hover:bg-ink/5 disabled:opacity-40"
                                  >
                                    Mark {STATUS_STYLES[next].label.toLowerCase()}
                                  </button>
                                ))}
                              </div>
                            </div>

                            <div>
                              <p className="text-[11px] uppercase tracking-wide text-ink/40">
                                Re-route
                              </p>
                              <select
                                value={complaint.department_id ?? ""}
                                disabled={busyId === complaint.id}
                                onChange={(e) =>
                                  act(
                                    complaint.id,
                                    () =>
                                      api.overrideRoute(complaint.id, {
                                        department_id: e.target.value,
                                      }),
                                    `#${complaint.id.slice(0, 8)} re-routed.`,
                                  )
                                }
                                className="mt-1.5 w-full rounded-md border border-ink/15 bg-white px-2 py-1.5 text-xs outline-none focus:border-signal disabled:opacity-40"
                              >
                                <option value="">Unassigned</option>
                                {departments.map((department) => (
                                  <option key={department.id} value={department.id}>
                                    {department.name}
                                  </option>
                                ))}
                              </select>

                              <select
                                value={complaint.category_slug ?? ""}
                                disabled={busyId === complaint.id}
                                onChange={(e) =>
                                  act(
                                    complaint.id,
                                    () =>
                                      api.overrideRoute(complaint.id, {
                                        category_slug: e.target.value,
                                      }),
                                    `#${complaint.id.slice(0, 8)} re-categorized.`,
                                  )
                                }
                                className="mt-1.5 w-full rounded-md border border-ink/15 bg-white px-2 py-1.5 text-xs outline-none focus:border-signal disabled:opacity-40"
                              >
                                <option value="">Uncategorized</option>
                                {CATEGORY_SLUGS.map((slug) => (
                                  <option key={slug} value={slug}>
                                    {categoryLabel(slug)}
                                  </option>
                                ))}
                              </select>
                            </div>

                            {complaint.cluster_id && (
                              <button
                                disabled={busyId === complaint.id}
                                onClick={() =>
                                  act(
                                    complaint.id,
                                    () => api.unmergeComplaint(complaint.id),
                                    `#${complaint.id.slice(0, 8)} removed from its cluster.`,
                                  )
                                }
                                className="w-full rounded-md border border-ink/20 px-2.5 py-1.5 text-xs font-medium text-ink/70 hover:bg-ink/5 disabled:opacity-40"
                                title="Undo an automatic merge that grouped unrelated problems"
                              >
                                Remove from cluster
                              </button>
                            )}

                            <Link
                              href={`/track/${complaint.id}`}
                              className="text-center text-xs text-ink/50 underline hover:text-ink"
                            >
                              Open the student-facing view
                            </Link>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
