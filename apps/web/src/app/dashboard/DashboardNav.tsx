"use client";

/**
 * Section switcher for the command center.
 *
 * The dashboard used to be one long scroll: stats, clusters, merges, map,
 * digest, queue, in that order. That ordering was right — it runs from "what
 * is on fire" down to "the full list" — but it meant an operator who wanted
 * the queue scrolled past four panels to reach it, every time, on every
 * refresh. Splitting it into sections keeps the same priority order in the
 * rail while making any one of them one click away.
 *
 * Implemented as a real tablist rather than a set of styled links: the
 * panel swaps in place instead of navigating, so arrow-key traversal and
 * `aria-selected` are what a screen reader needs to hear. Home and End jump
 * to the ends, matching the WAI-ARIA tabs pattern.
 *
 * Counts on the rail are the point of putting it on the left at all — an
 * operator can see there are merges waiting without opening that section.
 */

import { useRef } from "react";
import {
  GridIcon,
  ListIcon,
  MailIcon,
  MapIcon,
  MergeIcon,
  RepeatIcon,
} from "@/components/icons";

export type DashboardSection =
  | "overview"
  | "recurring"
  | "review"
  | "map"
  | "digest"
  | "queue";

export const SECTIONS: {
  id: DashboardSection;
  label: string;
  hint: string;
  Icon: (props: { className?: string }) => JSX.Element;
}[] = [
  { id: "overview", label: "Overview", hint: "Counts and what is systemic", Icon: GridIcon },
  { id: "recurring", label: "Recurring", hint: "Problems that keep coming back", Icon: RepeatIcon },
  { id: "review", label: "Review", hint: "Possible duplicates awaiting a decision", Icon: MergeIcon },
  { id: "map", label: "Map", hint: "Where the reports are concentrated", Icon: MapIcon },
  { id: "digest", label: "Digest", hint: "The daily summary the model writes", Icon: MailIcon },
  { id: "queue", label: "Queue", hint: "Every complaint, with the admin actions", Icon: ListIcon },
];

export function DashboardNav({
  active,
  onSelect,
  counts,
}: {
  active: DashboardSection;
  onSelect: (section: DashboardSection) => void;
  /** Undefined means "nothing to say"; 0 renders as a muted zero. */
  counts: Partial<Record<DashboardSection, number>>;
}) {
  const listRef = useRef<HTMLDivElement>(null);

  const onKeyDown = (e: React.KeyboardEvent) => {
    const keys = ["ArrowDown", "ArrowRight", "ArrowUp", "ArrowLeft", "Home", "End"];
    if (!keys.includes(e.key)) return;
    e.preventDefault();

    const index = SECTIONS.findIndex((s) => s.id === active);
    const last = SECTIONS.length - 1;
    const next =
      e.key === "Home"
        ? 0
        : e.key === "End"
          ? last
          : e.key === "ArrowDown" || e.key === "ArrowRight"
            ? Math.min(index + 1, last)
            : Math.max(index - 1, 0);

    onSelect(SECTIONS[next].id);
    // Roving tabindex: the newly selected tab is the only focusable one, so
    // focus has to be moved by hand for the arrow keys to keep working.
    listRef.current
      ?.querySelectorAll<HTMLButtonElement>("[role=tab]")
      [next]?.focus();
  };

  return (
    <div
      ref={listRef}
      role="tablist"
      aria-label="Dashboard sections"
      aria-orientation="vertical"
      onKeyDown={onKeyDown}
      className="flex gap-1 overflow-x-auto pb-1 lg:flex-col lg:overflow-x-visible lg:pb-0"
    >
      {SECTIONS.map((section) => {
        const selected = section.id === active;
        const count = counts[section.id];
        return (
          <button
            key={section.id}
            role="tab"
            id={`tab-${section.id}`}
            aria-selected={selected}
            aria-controls={`panel-${section.id}`}
            tabIndex={selected ? 0 : -1}
            title={section.hint}
            onClick={() => onSelect(section.id)}
            className={`group flex h-11 shrink-0 items-center gap-2.5 rounded-lg px-3 text-left text-sm transition-colors lg:w-full ${
              selected
                ? "bg-ink/[0.07] font-semibold text-ink"
                : "font-medium text-ink/60 hover:bg-ink/[0.04] hover:text-ink"
            }`}
          >
            <span
              aria-hidden="true"
              className={`h-[18px] w-[18px] shrink-0 ${
                selected ? "text-signal-ink" : "text-ink/45 group-hover:text-ink/70"
              }`}
            >
              <section.Icon />
            </span>
            <span className="whitespace-nowrap">{section.label}</span>
            {count !== undefined && (
              <span
                className={`ml-auto hidden rounded-full px-1.5 py-0.5 font-mono text-[10px] tabular-nums lg:inline-block ${
                  count > 0 ? "bg-ink/10 text-ink/70" : "text-ink/35"
                }`}
              >
                {count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
