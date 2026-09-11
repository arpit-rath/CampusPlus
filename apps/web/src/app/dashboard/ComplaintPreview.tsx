"use client";

/**
 * The card that trails the cursor when an operator hovers a complaint title.
 *
 * Borrowed from the studio-portfolio pattern where hovering a project title
 * plays its reel beside the cursor. The same move earns its keep here for a
 * different reason: triage is a scanning job. The queue shows a truncated
 * summary per row, and the thing that most often decides whether a row needs
 * attention — the photograph the student attached — is two clicks away inside
 * the expanded row. Putting it under the cursor lets an operator sweep a page
 * of twenty and stop only on the ones that look serious.
 *
 * Three constraints shaped the implementation:
 *
 * - It is an accelerator, never the only path. Everything in the card is also
 *   in the expanded row, which opens on click and is reachable by keyboard.
 *   Hover-only information would fail anyone not using a pointer.
 * - It never renders on a device without hover. On a touch screen the hover
 *   fires on tap and the card would fight the tap that expands the row, so a
 *   `(hover: hover)` check gates it entirely.
 * - It does not re-render React on pointer movement. Position is written
 *   straight to the transform inside a rAF loop; a setState per mousemove
 *   would re-render the card sixty times a second while the table underneath
 *   is also being updated by the websocket.
 *
 * The trailing ease is the effect: the card catches up to the cursor rather
 * than being nailed to it. Under `prefers-reduced-motion` it snaps instead,
 * because an element that chases the pointer is exactly the kind of motion
 * that setting asks us to stop.
 */

import { useEffect, useRef } from "react";
import { photoUrl, type Complaint, type ComplaintStatus } from "@/lib/api";
import { categoryLabel } from "@/lib/campus";
import { PriorityBar } from "@/components/PriorityBar";

const CARD_W = 320;
/** Only a starting guess: the real height varies with the summary and
 *  whether the complaint is clustered, so it is measured once mounted. */
const CARD_H = 430;
/** Distance from the pointer, far enough that the card never sits under it. */
const OFFSET = 22;
/** Per-frame catch-up. Lower trails further behind. */
const EASE = 0.18;

const STATUS_LABEL: Record<ComplaintStatus, string> = {
  open: "Open",
  in_progress: "In progress",
  resolved: "Resolved",
};

const STATUS_CLASS: Record<ComplaintStatus, string> = {
  open: "bg-critical/10 text-critical",
  in_progress: "bg-signal/10 text-signal-ink",
  resolved: "bg-calm/10 text-calm",
};

/**
 * The same pills, but sitting on a photograph. A 10%-opacity tint over an
 * unknown image is unreadable — the photo decides the contrast — so over a
 * photo they get a near-opaque page-coloured plate instead, which puts them
 * back on a measured background.
 */
const STATUS_ON_PHOTO: Record<ComplaintStatus, string> = {
  open: "bg-paper/90 text-critical",
  in_progress: "bg-paper/90 text-signal-ink",
  resolved: "bg-paper/90 text-calm",
};

/** True when the pointer can actually hover — false on touch screens. */
export function canHover(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(hover: hover) and (pointer: fine)").matches;
}

/**
 * Where the card sits for a pointer at (x, y): offset from the cursor, and
 * flipped across it near the right or bottom edge so it is never clipped.
 */
function place(clientX: number, clientY: number, height = CARD_H) {
  const flipX = clientX + OFFSET + CARD_W > window.innerWidth - 12;
  const flipY = clientY + OFFSET + height > window.innerHeight - 12;
  return {
    x: flipX ? Math.max(12, clientX - OFFSET - CARD_W) : clientX + OFFSET,
    y: flipY ? Math.max(12, clientY - OFFSET - height) : clientY + OFFSET,
  };
}

/** Where the pointer was when the hover started. */
export interface HoverOrigin {
  x: number;
  y: number;
}

export function ComplaintPreview({
  complaint,
  origin,
}: {
  complaint: Complaint | null;
  origin: HoverOrigin | null;
}) {
  const cardRef = useRef<HTMLDivElement>(null);
  const target = useRef({ x: 0, y: 0 });
  const current = useRef({ x: 0, y: 0 });
  const frame = useRef<number | null>(null);

  useEffect(() => {
    if (!complaint || !origin) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // Start at the pointer that opened the card rather than easing in from
    // the last hover — or, worse, from the top-left corner if the pointer
    // comes to rest on the title and never fires another move.
    target.current = place(origin.x, origin.y);
    current.current = { ...target.current };

    const onMove = (e: PointerEvent) => {
      target.current = place(
        e.clientX,
        e.clientY,
        cardRef.current?.offsetHeight ?? CARD_H,
      );
    };
    window.addEventListener("pointermove", onMove, { passive: true });

    const tick = () => {
      const node = cardRef.current;
      if (node) {
        const k = reduced ? 1 : EASE;
        current.current.x += (target.current.x - current.current.x) * k;
        current.current.y += (target.current.y - current.current.y) * k;
        const x = Math.round(current.current.x);
        const y = Math.round(current.current.y);
        node.style.transform = "translate3d(" + x + "px, " + y + "px, 0)";
      }
      frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);

    return () => {
      window.removeEventListener("pointermove", onMove);
      if (frame.current !== null) cancelAnimationFrame(frame.current);
    };
  }, [complaint, origin]);

  if (!complaint || !origin) return null;

  const photo = photoUrl(complaint.photo_url);
  const summary = complaint.ai_summary ?? complaint.raw_description;
  // Painted at the right place on the very first frame, before the effect
  // and its animation loop have had a chance to run.
  const initial = place(origin.x, origin.y);

  return (
    <div
      ref={cardRef}
      // A decorative duplicate of the row it describes: the row is what
      // assistive technology reads, so this is hidden from it entirely.
      aria-hidden="true"
      className="pointer-events-none fixed left-0 top-0 z-40 w-80 overflow-hidden rounded-xl border border-ink/15 bg-surface shadow-card-hover"
      style={{
        willChange: "transform",
        transform: `translate3d(${initial.x}px, ${initial.y}px, 0)`,
      }}
    >
      {/* A complaint with no photo gets a strip rather than an empty 16:9
          box. Reserving picture-sized space for a picture that does not
          exist makes every unphotographed report look like a loading
          failure — and most reports have no photo. */}
      {photo ? (
        <div className="relative aspect-[16/9] w-full overflow-hidden bg-ink/[0.06]">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={photo} alt="" className="h-full w-full object-cover" />
          <span
            className={`absolute left-2.5 top-2.5 rounded-full px-2 py-0.5 text-[10px] font-semibold backdrop-blur ${STATUS_ON_PHOTO[complaint.status]}`}
          >
            {STATUS_LABEL[complaint.status]}
          </span>
          {complaint.photo_matches_text && (
            <span className="absolute right-2.5 top-2.5 rounded-full bg-paper/90 px-2 py-0.5 text-[10px] font-semibold text-calm backdrop-blur">
              Photo corroborates
            </span>
          )}
        </div>
      ) : (
        <div className="flex items-center justify-between gap-2 border-b border-ink/10 bg-ink/[0.04] px-3 py-2">
          <span
            className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${STATUS_CLASS[complaint.status]}`}
          >
            {STATUS_LABEL[complaint.status]}
          </span>
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
            No photo
          </span>
        </div>
      )}

      <div className="p-3.5">
        <div className="flex items-baseline justify-between gap-2">
          <p className="text-sm font-semibold text-ink">
            {categoryLabel(complaint.category_slug)}
          </p>
          <p className="font-mono text-[10px] text-muted">#{complaint.id.slice(0, 8)}</p>
        </div>

        <p className="mt-1.5 line-clamp-3 text-xs leading-relaxed text-ink/75">{summary}</p>

        <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2">
          <div>
            <dt className="text-[10px] uppercase tracking-wide text-muted">Where</dt>
            <dd className="truncate text-xs text-ink/80">
              {complaint.location_building ?? "—"}
              {complaint.location_room ? ` · ${complaint.location_room}` : ""}
            </dd>
          </div>
          <div>
            <dt className="text-[10px] uppercase tracking-wide text-muted">Severity</dt>
            <dd className="font-mono text-xs tabular-nums text-ink/80">
              {complaint.severity ?? "—"}/5
              {complaint.safety_flag && (
                <span className="ml-1.5 font-sans text-[10px] font-bold uppercase text-hazard">
                  Safety
                </span>
              )}
            </dd>
          </div>
        </dl>

        <div className="mt-3">
          <p className="text-[10px] uppercase tracking-wide text-muted">Priority</p>
          <div className="mt-1">
            <PriorityBar
              breakdown={complaint.priority_breakdown}
              score={complaint.priority_score}
              compact
            />
          </div>
        </div>

        {complaint.reporter_name && (
          <p className="mt-2.5 truncate text-[11px] text-muted">
            Reported by{" "}
            <span className="font-medium text-ink">{complaint.reporter_name}</span>
            {complaint.reporter_role ? ` (${complaint.reporter_role})` : ""}
          </p>
        )}

        {complaint.cluster_id && (
          <p className="mt-2.5 border-t border-ink/10 pt-2 text-[11px] text-ink/70">
            {complaint.is_recurring ? "Recurring · " : "Clustered · "}
            {complaint.independent_student_count} independent student
            {complaint.independent_student_count === 1 ? "" : "s"},{" "}
            {complaint.cluster_member_count} report
            {complaint.cluster_member_count === 1 ? "" : "s"}
          </p>
        )}
      </div>
    </div>
  );
}
