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
  collapsed = false,
}: {
  active: DashboardSection;
  onSelect: (section: DashboardSection) => void;
  /** Undefined means "nothing to say"; 0 renders as a muted zero. */
  counts: Partial<Record<DashboardSection, number>>;
  /** Icon-only rail. Desktop only — the mobile layout is a scrolling row,
   *  where there is no width to reclaim. */
  collapsed?: boolean;
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
            // Collapsed, the icon is all there is, so the accessible name has
            // to come from somewhere — and the tooltip has to carry the label
            // a sighted user can no longer read.
            title={collapsed ? `${section.label} — ${section.hint}` : section.hint}
            onClick={() => onSelect(section.id)}
            className={`group relative flex h-11 shrink-0 items-center rounded-lg text-left text-sm transition-colors duration-200 lg:w-full ${
              collapsed
                ? "gap-2.5 px-3 lg:justify-center lg:gap-0 lg:px-0"
                : "gap-2.5 px-3"
            } ${
              selected
                ? "bg-ink/[0.07] font-semibold text-ink"
                : "font-medium text-muted hover:bg-ink/[0.04] hover:text-ink"
            }`}
          >
            {/* The active marker has to survive the collapse: with the label
                gone, a weight change alone is invisible. */}
            {selected && (
              <span
                aria-hidden="true"
                className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-signal-ink"
              />
            )}
            <span
              aria-hidden="true"
              className={`relative h-[18px] w-[18px] shrink-0 ${
                collapsed ? "lg:mx-3" : ""
              } ${selected ? "text-signal-ink" : "text-muted group-hover:text-ink"}`}
            >
              <section.Icon />
              {/* Collapsed, a count cannot be a number in a row that no
                  longer has one — it becomes a dot that says "something is
                  waiting here". */}
              {collapsed && count !== undefined && count > 0 && (
                <span className="absolute -right-1.5 -top-1 hidden h-2 w-2 rounded-full bg-signal-ink ring-2 ring-paper lg:block" />
              )}
            </span>
            <span
              className={
                collapsed ? "whitespace-nowrap lg:sr-only" : "whitespace-nowrap"
              }
            >
              {section.label}
            </span>
            {!collapsed && count !== undefined && (
              <span
                className={`ml-auto hidden rounded-full px-1.5 py-0.5 font-mono text-[10px] tabular-nums lg:inline-block ${
                  count > 0 ? "bg-ink/10 text-ink" : "text-muted"
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
