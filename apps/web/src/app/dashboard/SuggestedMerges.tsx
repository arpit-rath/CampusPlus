"use client";

/**
 * The 0.75-0.92 similarity band, waiting on a human.
 *
 * This card is the visible half of a rule that would otherwise be invisible:
 * the system auto-merges only what it is confident about, and everything it
 * merely suspects lands here instead of being applied silently. Showing the
 * actual similarity score next to both texts is the point — an admin can see
 * why the system hesitated and decide in about two seconds.
 */

import { useState } from "react";
import Link from "next/link";
import { api, ApiError, type SuggestedMerge } from "@/lib/api";
import { categoryLabel } from "@/lib/campus";

export function SuggestedMerges({
  merges,
  onResolved,
}: {
  merges: SuggestedMerge[];
  onResolved: (message: string) => void;
}) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const decide = async (merge: SuggestedMerge, accept: boolean) => {
    setBusyId(merge.complaint.id);
    setError(null);
    try {
      await api.resolveSuggestedMerge(merge.complaint.id, accept);
      onResolved(
        accept
          ? `Merged #${merge.complaint.id.slice(0, 8)} into the existing case.`
          : `Dismissed the merge suggestion for #${merge.complaint.id.slice(0, 8)}.`,
      );
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "This needs an admin token."
          : "Couldn't apply that decision — try again.",
      );
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section className="rounded-xl border border-signal/30 bg-signal/[0.04] p-4">
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-ink">
            Possible duplicates · needs review
          </h2>
          <p className="mt-0.5 text-xs text-ink/55">
            Similar enough to flag, not similar enough to merge automatically.
            Your call.
          </p>
        </div>
        <span className="shrink-0 font-mono text-lg font-bold tabular-nums text-signal">
          {merges.length}
        </span>
      </div>

      {error && (
        <p className="mt-2 rounded-md border border-critical/25 bg-critical/5 px-2.5 py-1.5 text-xs text-critical">
          {error}
        </p>
      )}

      <ul className="mt-3 flex flex-col gap-2">
        {merges.map((merge) => {
          const busy = busyId === merge.complaint.id;
          return (
            <li
              key={merge.complaint.id}
              className="rounded-lg border border-ink/10 bg-surface p-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full bg-signal/15 px-2 py-0.5 font-mono text-[11px] font-semibold text-signal">
                  {(merge.similarity * 100).toFixed(0)}% similar
                </span>
                <span className="text-xs text-ink/50">
                  {categoryLabel(merge.complaint.category_slug)} ·{" "}
                  {merge.complaint.location_building ?? "unspecified"}
                </span>
              </div>

              <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                <MergeSide
                  heading="New report"
                  id={merge.complaint.id}
                  text={merge.complaint.ai_summary ?? merge.complaint.raw_description}
                  student={merge.complaint.student_id}
                />
                <MergeSide
                  heading="Existing case"
                  id={merge.target.id}
                  text={merge.target.ai_summary ?? merge.target.raw_description}
                  student={merge.target.student_id}
                />
              </div>

              <div className="mt-2.5 flex gap-2">
                <button
                  onClick={() => decide(merge, true)}
                  disabled={busy}
                  className="rounded-md bg-ink px-3 py-1.5 text-xs font-medium text-paper disabled:opacity-40"
                >
                  {busy ? "Working…" : "Same problem — merge"}
                </button>
                <button
                  onClick={() => decide(merge, false)}
                  disabled={busy}
                  className="rounded-md border border-ink/20 px-3 py-1.5 text-xs font-medium text-ink hover:bg-ink/5 disabled:opacity-40"
                >
                  Different — keep separate
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function MergeSide({
  heading,
  id,
  text,
  student,
}: {
  heading: string;
  id: string;
  text: string;
  student: string | null;
}) {
  return (
    <div className="rounded-md border border-ink/10 bg-ink/[0.02] p-2">
      <p className="flex items-center justify-between gap-2 text-[10px] uppercase tracking-wide text-ink/40">
        {heading}
        <Link href={`/track/${id}`} className="font-mono normal-case hover:text-ink">
          #{id.slice(0, 8)}
        </Link>
      </p>
      <p className="mt-1 line-clamp-3 text-xs text-ink/75">{text}</p>
      <p className="mt-1 font-mono text-[10px] text-ink/35">
        {student ?? "anonymous"}
      </p>
    </div>
  );
}
