/**
 * Explainable priority breakdown bar — colocated with the tracker page
 * on purpose (not a shared component) since other tracks build against
 * this same repo in parallel and can't see files outside their own scope.
 * If the admin dashboard (Track D) wants something similar, it should
 * have its own local copy rather than importing this one.
 */

import type { PriorityBreakdown } from "@/lib/api";

// Mirrors the weighted formula in CLAUDE.md:
// priority = 0.40*severity + 0.30*frequency + 0.20*safety + 0.10*sla_age
const SEGMENTS: {
  key: keyof PriorityBreakdown;
  label: string;
  weight: number;
  swatchClassName: string;
}[] = [
  {
    key: "severity",
    label: "Severity",
    weight: 0.4,
    swatchClassName: "bg-critical",
  },
  {
    key: "frequency",
    label: "How often reported",
    weight: 0.3,
    swatchClassName: "bg-signal",
  },
  {
    key: "safety",
    label: "Safety risk",
    weight: 0.2,
    swatchClassName: "bg-ink",
  },
  {
    key: "sla_age",
    label: "Time open",
    weight: 0.1,
    swatchClassName: "bg-calm",
  },
];

function clamp01(n: number): number {
  if (!Number.isFinite(n)) return 0;
  if (n < 0) return 0;
  if (n > 1) return 1;
  return n;
}

export default function PriorityBar({
  breakdown,
  priorityScore,
}: {
  breakdown: PriorityBreakdown;
  priorityScore?: number;
}) {
  const parts = SEGMENTS.map((seg) => {
    const value = clamp01(breakdown?.[seg.key] ?? 0);
    return { ...seg, value, contribution: value * seg.weight };
  });

  const total = parts.reduce((sum, p) => sum + p.contribution, 0);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <p className="font-mono text-xs uppercase tracking-widest text-ink/50">
          Why this priority
        </p>
        {typeof priorityScore === "number" && (
          <p className="font-mono text-xs text-ink/50">
            score {priorityScore.toFixed(2)}
          </p>
        )}
      </div>

      <div className="flex h-3 w-full overflow-hidden rounded-full bg-ink/10">
        {parts.map((p) => (
          <div
            key={p.key}
            className={p.swatchClassName}
            style={{
              width: `${total > 0 ? (p.contribution / total) * 100 : 100 / parts.length}%`,
            }}
            title={`${p.label}: ${p.value.toFixed(2)}`}
          />
        ))}
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-ink/60 sm:grid-cols-4">
        {parts.map((p) => (
          <div key={p.key} className="flex items-center gap-1.5">
            <span className={`h-2 w-2 shrink-0 rounded-full ${p.swatchClassName}`} />
            <span>
              {p.label} · {p.value.toFixed(2)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
