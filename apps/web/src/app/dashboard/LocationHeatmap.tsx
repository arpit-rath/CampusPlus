"use client";

/**
 * Campus map, marker size scaled by priority.
 *
 * The plan asks for a heatmap where "marker size represents priority", which
 * a per-building count grid does not do — a building with twelve trivial
 * complaints outranked one with a live electrical hazard. Here each marker's
 * radius follows the highest priority score at that building and its colour
 * follows severity of state (recurring / safety / ordinary), so the eye lands
 * on what is actually urgent.
 *
 * The layout is a hand-drawn schematic from `lib/campus.ts`, not real
 * geography — a deliberate choice over fabricating plausible coordinates for
 * a campus that does not exist.
 */

import { useState } from "react";
import type { Cluster, Complaint } from "@/lib/api";
import { CAMPUS_BUILDINGS, categoryLabel } from "@/lib/campus";

interface BuildingState {
  name: string;
  x: number;
  y: number;
  openCount: number;
  maxPriority: number;
  recurring: boolean;
  safety: boolean;
  topSummary: string | null;
  topCategory: string | null;
}

const MIN_RADIUS = 10;
const MAX_RADIUS = 34;

export function LocationHeatmap({
  complaints,
  clusters,
}: {
  complaints: Complaint[];
  clusters: Cluster[];
}) {
  const [hovered, setHovered] = useState<string | null>(null);

  const recurringBuildings = new Set(
    clusters.filter((c) => c.is_recurring).map((c) => c.location_building ?? ""),
  );

  const byBuilding = new Map<string, BuildingState>();
  for (const building of CAMPUS_BUILDINGS) {
    byBuilding.set(building.name, {
      name: building.name,
      x: building.x,
      y: building.y,
      openCount: 0,
      maxPriority: 0,
      recurring: recurringBuildings.has(building.name),
      safety: false,
      topSummary: null,
      topCategory: null,
    });
  }

  for (const complaint of complaints) {
    if (complaint.status === "resolved") continue;
    const state = byBuilding.get(complaint.location_building ?? "");
    if (!state) continue;
    state.openCount += 1;
    state.safety ||= complaint.safety_flag;
    if (complaint.priority_score > state.maxPriority) {
      state.maxPriority = complaint.priority_score;
      state.topSummary = complaint.ai_summary ?? complaint.raw_description;
      state.topCategory = complaint.category_slug;
    }
  }

  const active = [...byBuilding.values()].filter((b) => b.openCount > 0);
  const hoveredState = active.find((b) => b.name === hovered) ?? null;

  return (
    <section className="rounded-xl border border-ink/10 bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-ink">
            Campus map
          </h2>
          <p className="mt-0.5 text-xs text-ink/50">
            Marker size scales with the highest open priority at each location
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-[11px] text-ink/50">
          <Legend className="bg-critical" label="Recurring" />
          <Legend className="bg-[#8B2E8B]" label="Safety flagged" />
          <Legend className="bg-signal" label="Open" />
        </div>
      </div>

      {active.length === 0 ? (
        <p className="mt-6 rounded-lg border border-dashed border-ink/15 bg-ink/[0.02] px-4 py-10 text-center text-sm text-ink/45">
          No open complaints anywhere on campus.
        </p>
      ) : (
        <div className="relative mt-3 aspect-[16/9] w-full overflow-hidden rounded-lg border border-ink/10 bg-[#F4F6F3]">
          {/* Faint zone bands, purely to give the markers spatial context. */}
          <div className="absolute inset-x-0 top-0 h-[38%] bg-ink/[0.02]" />
          <div className="absolute inset-x-0 bottom-0 h-[34%] bg-ink/[0.03]" />

          {CAMPUS_BUILDINGS.map((building) => {
            const state = byBuilding.get(building.name);
            const isActive = (state?.openCount ?? 0) > 0;
            if (isActive) return null;
            return (
              <span
                key={building.name}
                className="absolute -translate-x-1/2 -translate-y-1/2 whitespace-nowrap text-[9px] text-ink/25"
                style={{ left: `${building.x}%`, top: `${building.y}%` }}
              >
                {building.name}
              </span>
            );
          })}

          {active.map((state) => {
            const radius =
              MIN_RADIUS + (MAX_RADIUS - MIN_RADIUS) * Math.min(1, state.maxPriority);
            const color = state.recurring
              ? "rgba(180, 64, 47, 0.75)"
              : state.safety
                ? "rgba(139, 46, 139, 0.7)"
                : "rgba(201, 113, 31, 0.65)";
            return (
              <button
                key={state.name}
                type="button"
                onMouseEnter={() => setHovered(state.name)}
                onMouseLeave={() => setHovered(null)}
                onFocus={() => setHovered(state.name)}
                onBlur={() => setHovered(null)}
                className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full outline-none ring-offset-2 transition-transform hover:scale-110 focus:ring-2 focus:ring-ink/40"
                style={{
                  left: `${state.x}%`,
                  top: `${state.y}%`,
                  width: radius * 2,
                  height: radius * 2,
                  backgroundColor: color,
                }}
                aria-label={`${state.name}: ${state.openCount} open, highest priority ${state.maxPriority.toFixed(2)}`}
              >
                <span className="font-mono text-xs font-bold text-white">
                  {state.openCount}
                </span>
                {state.recurring && (
                  <span
                    className="pointer-events-none absolute inset-0 animate-ping rounded-full border-2 border-critical/50"
                    aria-hidden
                  />
                )}
              </button>
            );
          })}

          {active.map((state) => (
            <span
              key={`${state.name}-label`}
              className="pointer-events-none absolute -translate-x-1/2 whitespace-nowrap text-[10px] font-medium text-ink/70"
              style={{
                left: `${state.x}%`,
                top: `calc(${state.y}% + ${MIN_RADIUS + (MAX_RADIUS - MIN_RADIUS) * Math.min(1, state.maxPriority) + 4}px)`,
              }}
            >
              {state.name}
            </span>
          ))}
        </div>
      )}

      {hoveredState && (
        <div className="mt-3 rounded-lg border border-ink/10 bg-ink/[0.02] px-3 py-2">
          <p className="text-sm font-medium text-ink">
            {hoveredState.name}
            <span className="ml-2 font-mono text-xs font-normal text-ink/50">
              {hoveredState.openCount} open · peak priority{" "}
              {hoveredState.maxPriority.toFixed(2)}
            </span>
          </p>
          {hoveredState.topSummary && (
            <p className="mt-0.5 truncate text-xs text-ink/60">
              {categoryLabel(hoveredState.topCategory)} — {hoveredState.topSummary}
            </p>
          )}
        </div>
      )}
    </section>
  );
}

function Legend({ className, label }: { className: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={`h-2.5 w-2.5 rounded-full ${className}`} />
      {label}
    </span>
  );
}
