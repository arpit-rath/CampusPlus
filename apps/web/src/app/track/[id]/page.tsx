"use client";

/**
 * Live status tracker for a single complaint. Polls `api.getComplaint`
 * on an interval so a status change (or a cluster merging into a
 * recurring issue) shows up without a manual refresh — the plan's
 * realtime story, minus the actual websocket wiring which lands
 * elsewhere.
 */

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, type Complaint, type ComplaintStatus } from "@/lib/api";
import PriorityBar from "./PriorityBar";

const POLL_INTERVAL_MS = 4000;

const STATUS_STYLES: Record<
  ComplaintStatus,
  { label: string; className: string }
> = {
  open: {
    label: "Open",
    className: "border-critical/30 bg-critical/10 text-critical",
  },
  in_progress: {
    label: "In progress",
    className: "border-signal/30 bg-signal/10 text-signal",
  },
  resolved: {
    label: "Resolved",
    className: "border-calm/30 bg-calm/10 text-calm",
  },
};

export default function TrackComplaintPage() {
  const { id } = useParams<{ id: string }>();

  const [complaint, setComplaint] = useState<Complaint | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;

    const fetchComplaint = async () => {
      try {
        const result = await api.getComplaint(id);
        if (cancelled) return;
        setComplaint(result);
        setError(null);
      } catch {
        if (cancelled) return;
        setError("Couldn't reach the API — check it's running.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchComplaint();
    const intervalId = setInterval(fetchComplaint, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, [id]);

  if (loading) {
    return (
      <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-start justify-center gap-2 px-6">
        <p className="font-mono text-xs uppercase tracking-widest text-ink/50">
          CampusPluse · Tracking
        </p>
        <p className="text-ink/60">Loading complaint…</p>
      </main>
    );
  }

  if (error && !complaint) {
    return (
      <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-start justify-center gap-3 px-6">
        <p className="font-mono text-xs uppercase tracking-widest text-ink/50">
          CampusPluse · Tracking
        </p>
        <p className="rounded-md border border-critical/30 bg-critical/10 px-3 py-2 text-sm text-critical">
          Couldn&rsquo;t load this complaint — check the API is running.
        </p>
      </main>
    );
  }

  if (!complaint) {
    return null;
  }

  const status = STATUS_STYLES[complaint.status];

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-6 py-16">
      <div>
        <p className="font-mono text-xs uppercase tracking-widest text-ink/50">
          CampusPluse · Tracking #{complaint.id.slice(0, 8)}
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-bold tracking-tight">Status</h1>
          <span
            className={`rounded-full border px-3 py-1 text-xs font-medium uppercase tracking-wide ${status.className}`}
          >
            {status.label}
          </span>
        </div>
      </div>

      {error && (
        <p className="rounded-md border border-signal/30 bg-signal/10 px-3 py-2 text-sm text-signal">
          {error} Showing the last known status.
        </p>
      )}

      {complaint.is_recurring && (
        <p className="w-fit rounded-full border border-signal/30 bg-signal/10 px-3 py-1 text-xs font-medium text-signal">
          Recurring issue — {complaint.cluster_member_count} student
          {complaint.cluster_member_count === 1 ? "" : "s"} reported this
        </p>
      )}

      <div className="flex flex-col gap-1.5 rounded-md border border-ink/10 bg-white/50 p-4">
        <p className="font-mono text-xs uppercase tracking-widest text-ink/50">
          AI summary
        </p>
        <p className="text-ink">
          {complaint.ai_summary ?? complaint.raw_description}
        </p>
        <p className="mt-1 text-xs text-ink/50">
          {complaint.category_slug} · {complaint.department_name}
          {complaint.location_building
            ? ` · ${complaint.location_building}`
            : ""}
          {complaint.location_room ? ` ${complaint.location_room}` : ""}
        </p>
      </div>

      <div className="rounded-md border border-ink/10 bg-white/50 p-4">
        <PriorityBar
          breakdown={complaint.priority_breakdown}
          priorityScore={complaint.priority_score}
        />
      </div>

      {complaint.photo_url && (
        <div className="flex flex-col gap-1.5">
          <p className="font-mono text-xs uppercase tracking-widest text-ink/50">
            Photo
          </p>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={complaint.photo_url}
            alt="Reported issue"
            className="max-h-80 w-full rounded-md border border-ink/10 object-cover"
          />
        </div>
      )}

      <div className="flex flex-col gap-1.5">
        <p className="font-mono text-xs uppercase tracking-widest text-ink/50">
          Original report
        </p>
        <p className="text-sm text-ink/70">{complaint.raw_description}</p>
      </div>
    </main>
  );
}
