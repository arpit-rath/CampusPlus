/**
 * Location heatmap placeholder (nice-to-have per the task brief) — groups
 * open complaint counts by `location_building`. No map library: a grid of
 * divs whose background opacity scales with count. Good enough to point at
 * on stage; a real map is a stretch goal.
 */

import type { Complaint } from "@/lib/api";

interface LocationHeatmapProps {
  complaints: Complaint[];
}

export function LocationHeatmap({ complaints }: LocationHeatmapProps) {
  const counts = new Map<string, number>();
  for (const c of complaints) {
    if (c.status !== "open") continue;
    const key = c.location_building ?? "Unspecified";
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }

  const entries = Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
  const max = entries.length > 0 ? entries[0][1] : 0;

  return (
    <section className="rounded-lg border border-ink/10 bg-white p-4">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-ink">
        Open complaints by building
      </h2>
      <p className="mt-0.5 text-xs text-ink/50">
        Darker = more open complaints right now
      </p>

      {entries.length === 0 ? (
        <p className="mt-4 text-sm text-ink/40">No open complaints.</p>
      ) : (
        <div className="mt-3 flex flex-wrap gap-2">
          {entries.map(([building, count]) => {
            const intensity = max > 0 ? 0.12 + 0.68 * (count / max) : 0.12;
            return (
              <div
                key={building}
                className="flex min-w-[7rem] flex-col gap-1 rounded-md border border-critical/20 px-3 py-2"
                style={{ backgroundColor: `rgba(180, 64, 47, ${intensity})` }}
                title={`${building}: ${count} open`}
              >
                <span className="truncate text-xs font-medium text-ink">
                  {building}
                </span>
                <span className="font-mono text-lg font-bold leading-none text-ink">
                  {count}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
