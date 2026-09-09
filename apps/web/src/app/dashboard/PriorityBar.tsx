/**
 * Explainable priority bar — Track D, local to the dashboard on purpose
 * (see CLAUDE.md §"Priority formula": every term is stored per-complaint so
 * the UI never renders a bare score). Four stacked segments, widths
 * proportional to each term's weighted contribution to `priority_score`.
 *
 * Not shared outside apps/web/src/app/dashboard/ — duplicating this in
 * another track's directory is expected, per the track split.
 */

import type { PriorityBreakdown } from "@/lib/api";

export const PRIORITY_SEGMENTS: {
  key: keyof PriorityBreakdown;
  label: string;
  swatch: string;
}[] = [
  { key: "severity", label: "Severity", swatch: "bg-critical" },
  { key: "frequency", label: "Frequency", swatch: "bg-signal" },
  { key: "safety", label: "Safety", swatch: "bg-violet-500" },
  { key: "sla_age", label: "Age", swatch: "bg-calm" },
];

interface PriorityBarProps {
  breakdown: PriorityBreakdown;
  score: number;
  /** Show the labeled legend under the bar. Default: compact, bar only. */
  showLegend?: boolean;
  className?: string;
}

export function PriorityBar({
  breakdown,
  score,
  showLegend = false,
  className = "",
}: PriorityBarProps) {
  const total =
    breakdown.severity + breakdown.frequency + breakdown.safety + breakdown.sla_age;
  const filledWidthPct = Math.max(0, Math.min(1, total)) * 100;

  return (
    <div className={className}>
      <div className="flex items-center gap-2">
        <div className="h-1.5 w-24 overflow-hidden rounded-full bg-ink/10">
          {total > 0 && (
            <div
              className="flex h-full"
              style={{ width: `${filledWidthPct}%` }}
            >
              {PRIORITY_SEGMENTS.map((segment) => {
                const value = breakdown[segment.key];
                const widthPct = (value / total) * 100;
                return (
                  <div
                    key={segment.key}
                    className={segment.swatch}
                    style={{ width: `${widthPct}%` }}
                    title={`${segment.label}: ${value.toFixed(2)}`}
                  />
                );
              })}
            </div>
          )}
        </div>
        <span className="font-mono text-xs tabular-nums text-ink/70">
          {score.toFixed(2)}
        </span>
      </div>
      {showLegend && (
        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
          {PRIORITY_SEGMENTS.map((segment) => (
            <span
              key={segment.key}
              className="flex items-center gap-1 font-mono text-[10px] uppercase tracking-wide text-ink/50"
            >
              <span className={`h-1.5 w-1.5 rounded-full ${segment.swatch}`} />
              {segment.label} {breakdown[segment.key].toFixed(2)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
