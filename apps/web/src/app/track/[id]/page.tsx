"use client";

/**
 * Live status tracker for one complaint.
 *
 * Subscribes to the realtime feed rather than polling, and filters events
 * down to this complaint and its cluster — so if two more students report
 * the same problem while a student is watching this page, they see their
 * report become a recurring issue and its priority climb, live.
 *
 * A refetch on every reconnect covers the gap: an event missed while the
 * socket was down is picked up as soon as it comes back, so the page
 * self-heals instead of showing stale data forever.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  api,
  photoUrl,
  subscribeToRealtime,
  type Complaint,
  type ComplaintStatus,
  type StatusEvent,
} from "@/lib/api";
import { categoryLabel } from "@/lib/campus";
import { PriorityBar } from "@/components/PriorityBar";
import { LiveIndicator, type ConnectionStatus } from "@/components/LiveIndicator";

const STATUS_STYLES: Record<ComplaintStatus, { label: string; className: string }> = {
  open: { label: "Open", className: "border-critical/30 bg-critical/10 text-critical" },
  in_progress: { label: "In progress", className: "border-signal/30 bg-signal/10 text-signal" },
  resolved: { label: "Resolved", className: "border-calm/30 bg-calm/10 text-calm" },
};

export default function TrackComplaintPage() {
  const { id } = useParams<{ id: string }>();

  const [complaint, setComplaint] = useState<Complaint | null>(null);
  const [events, setEvents] = useState<StatusEvent[]>([]);
  const [connection, setConnection] = useState<ConnectionStatus>("connecting");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [justUpdated, setJustUpdated] = useState(false);

  const refresh = useCallback(async () => {
    if (!id) return;
    try {
      const [next, nextEvents] = await Promise.all([
        api.getComplaint(id),
        api.listStatusEvents(id).catch(() => [] as StatusEvent[]),
      ]);
      setComplaint((previous) => {
        if (previous && previous.priority_score !== next.priority_score) {
          setJustUpdated(true);
          setTimeout(() => setJustUpdated(false), 2000);
        }
        return next;
      });
      setEvents(nextEvents);
      setError(null);
    } catch {
      setError("Couldn't reach the API — showing the last known status.");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!id) return;
    return subscribeToRealtime(
      (event) => {
        // Anything that could change this complaint — its own update, or a
        // cluster gaining a member — triggers a refetch. Cheap, and it
        // avoids reconstructing derived fields client-side.
        if (
          event.type === "complaint.updated" ||
          event.type === "complaint.created" ||
          event.type === "cluster.updated" ||
          event.type === "cluster.recurring"
        ) {
          refresh();
        }
      },
      (status) => {
        setConnection(status);
        if (status === "live") refresh();
      },
    );
  }, [id, refresh]);

  if (loading) {
    return (
      <Shell>
        <div className="h-8 w-40 animate-pulse rounded bg-ink/10" />
        <div className="h-28 w-full animate-pulse rounded-xl bg-ink/5" />
        <div className="h-20 w-full animate-pulse rounded-xl bg-ink/5" />
      </Shell>
    );
  }

  if (!complaint) {
    return (
      <Shell>
        <p className="rounded-lg border border-critical/30 bg-critical/10 px-3 py-2 text-sm text-critical">
          Couldn&rsquo;t load this complaint. Check that the API is running, or{" "}
          <Link href="/report" className="underline">
            file a new report
          </Link>
          .
        </p>
      </Shell>
    );
  }

  const status = STATUS_STYLES[complaint.status];
  const photo = photoUrl(complaint.photo_url);

  return (
    <Shell>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-mono text-xs uppercase tracking-widest text-ink/50">
            Tracking #{complaint.id.slice(0, 8)}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <h1 className="text-3xl font-bold tracking-tight">
              {categoryLabel(complaint.category_slug)}
            </h1>
            <span
              className={`rounded-full border px-3 py-1 text-xs font-medium uppercase tracking-wide ${status.className}`}
            >
              {status.label}
            </span>
          </div>
        </div>
        <LiveIndicator status={connection} />
      </div>

      {error && (
        <p className="rounded-lg border border-signal/30 bg-signal/10 px-3 py-2 text-sm text-signal">
          {error}
        </p>
      )}

      {complaint.is_recurring && (
        <div className="rounded-xl border border-critical/30 bg-critical/5 p-4">
          <p className="text-sm font-semibold text-critical">
            Recurring issue — {complaint.independent_student_count} independent
            students have reported this
          </p>
          <p className="mt-1 text-sm text-ink/70">
            Your report was merged with {complaint.cluster_member_count - 1} other
            {complaint.cluster_member_count - 1 === 1 ? "" : "s"} instead of
            opening a duplicate ticket. That raised its priority automatically.
          </p>
        </div>
      )}

      <section className="rounded-xl border border-ink/10 bg-white p-5">
        <h2 className="font-mono text-xs uppercase tracking-widest text-ink/50">
          AI summary
        </h2>
        <p className="mt-2 text-ink">{complaint.ai_summary ?? complaint.raw_description}</p>
        <p className="mt-2 text-xs text-ink/50">
          {categoryLabel(complaint.category_slug)}
          {complaint.department_name ? ` · ${complaint.department_name}` : ""}
          {complaint.location_building ? ` · ${complaint.location_building}` : ""}
          {complaint.location_room ? ` ${complaint.location_room}` : ""}
        </p>
      </section>

      <section
        className={`rounded-xl border bg-white p-5 transition-colors ${
          justUpdated ? "border-signal bg-signal/5" : "border-ink/10"
        }`}
      >
        <div className="flex items-center justify-between">
          <h2 className="font-mono text-xs uppercase tracking-widest text-ink/50">
            Why this priority
          </h2>
          {justUpdated && (
            <span className="font-mono text-[10px] uppercase tracking-widest text-signal">
              Just updated
            </span>
          )}
        </div>
        <div className="mt-3">
          <PriorityBar
            breakdown={complaint.priority_breakdown}
            score={complaint.priority_score}
            showLegend
          />
        </div>
      </section>

      {photo && (
        <section className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <h2 className="font-mono text-xs uppercase tracking-widest text-ink/50">
              Photo
            </h2>
            {complaint.photo_matches_text !== null && (
              <span
                className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                  complaint.photo_matches_text
                    ? "bg-calm/10 text-calm"
                    : "bg-signal/10 text-signal"
                }`}
              >
                {complaint.photo_matches_text ? "Verified against description" : "Unverified"}
              </span>
            )}
          </div>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={photo}
            alt="Reported issue"
            className="max-h-80 w-full rounded-xl border border-ink/10 object-cover"
          />
        </section>
      )}

      <section>
        <h2 className="font-mono text-xs uppercase tracking-widest text-ink/50">
          Timeline
        </h2>
        <ol className="mt-3 flex flex-col gap-3 border-l border-ink/15 pl-4">
          {events.map((event) => (
            <li key={event.id} className="relative">
              <span className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-ink/30" />
              <p className="text-sm font-medium text-ink">
                {STATUS_STYLES[event.status]?.label ?? event.status}
              </p>
              {event.note && <p className="text-sm text-ink/60">{event.note}</p>}
              <p className="font-mono text-[11px] text-ink/35">
                {new Date(event.created_at).toLocaleString()}
                {event.actor ? ` · ${event.actor}` : ""}
              </p>
            </li>
          ))}
          {events.length === 0 && (
            <li className="text-sm text-ink/40">No status changes yet.</li>
          )}
        </ol>
      </section>

      <section>
        <h2 className="font-mono text-xs uppercase tracking-widest text-ink/50">
          Original report
        </h2>
        <p className="mt-2 text-sm text-ink/70">{complaint.raw_description}</p>
      </section>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-6 py-12">
      <Link
        href="/"
        className="font-mono text-xs uppercase tracking-widest text-ink/50 hover:text-ink"
      >
        CampusPluse
      </Link>
      {children}
    </main>
  );
}
