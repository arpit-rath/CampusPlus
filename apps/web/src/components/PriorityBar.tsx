/**
 * The explainable priority bar.
 *
 * There were two near-identical copies of this — one for the dashboard, one
 * for the tracker — which is the sort of duplication that ends with the
 * student and the admin looking at subtly different explanations of the same
 * number. One component, two densities.
 *
 * The whole point of the design is that the score is never shown alone. Each
 * segment's width *is* that term's weighted contribution (the four sum to the
 * score), so the bar is not a visualization of the score — it is the formula,
 * drawn.
 */

import type { PriorityBreakdown } from "@/lib/api";

const SEGMENTS = [
  {
    key: "severity" as const,
    label: "Severity",
    className: "bg-critical",
    swatch: "bg-critical",
    explain: "How bad the AI judged this issue to be, 1-5.",
  },
  {
    key: "frequency" as const,
    label: "Recurrence",
    className: "bg-signal",
    swatch: "bg-signal",
    explain: "How many independent students have reported it.",
  },
  {
    key: "safety" as const,
    label: "Safety",
    className: "bg-[#8B2E8B]",
    swatch: "bg-[#8B2E8B]",
    explain: "All-or-nothing: flagged as a physical safety risk.",
  },
  {
    key: "sla_age" as const,
    label: "Age",
    className: "bg-calm",
    swatch: "bg-calm",
    explain: "How long it has been sitting open against the SLA clock.",
  },
];

export function priorityLabel(score: number): string {
  if (score >= 0.7) return "Critical";
  if (score >= 0.5) return "High";
  if (score >= 0.3) return "Medium";
  return "Low";
}

export function PriorityBar({
  breakdown,
  score,
  compact = false,
  showLegend = false,
}: {
  breakdown: PriorityBreakdown;
  score: number;
  compact?: boolean;
  showLegend?: boolean;
}) {
  // The bar is drawn against a full scale of 1.0 rather than being
  // normalized to the score, so a low-priority complaint genuinely looks
  // low-priority next to a high one instead of every bar looking full.
  const filled = Math.max(0, Math.min(1, score));

  return (
    <div className={compact ? "w-40" : "w-full"}>
      <div className="flex items-baseline justify-between gap-2">
        <span
          className={`font-mono font-semibold tabular-nums ${
            compact ? "text-sm" : "text-2xl"
          }`}
        >
          {score.toFixed(2)}
        </span>
        <span
          className={`text-[10px] font-medium uppercase tracking-wide ${
            filled >= 0.7 ? "text-critical" : filled >= 0.5 ? "text-signal" : "text-ink/45"
          }`}
        >
          {priorityLabel(score)}
        </span>
      </div>

      <div
        className={`mt-1 flex w-full overflow-hidden rounded-full bg-ink/10 ${
          compact ? "h-1.5" : "h-2.5"
        }`}
        role="img"
        aria-label={
          `Priority ${score.toFixed(2)} of 1.00: ` +
          SEGMENTS.map(
            (s) => `${s.label} ${breakdown[s.key].toFixed(2)}`,
          ).join(", ")
        }
      >
        {SEGMENTS.map((segment) => {
          const value = breakdown[segment.key] ?? 0;
          if (value <= 0) return null;
          return (
            <div
              key={segment.key}
              className={segment.className}
              style={{ width: `${value * 100}%` }}
              title={`${segment.label}: ${value.toFixed(3)} — ${segment.explain}`}
            />
          );
        })}
      </div>

      {showLegend && (
        <dl className="mt-3 flex flex-col gap-1.5">
          {SEGMENTS.map((segment) => {
            const value = breakdown[segment.key] ?? 0;
            const share = score > 0 ? Math.round((value / score) * 100) : 0;
            return (
              <div key={segment.key} className="flex items-center gap-2 text-xs">
                <span className={`h-2.5 w-2.5 shrink-0 rounded-sm ${segment.swatch}`} />
                <span className="w-20 shrink-0 font-medium text-ink">{segment.label}</span>
                <span className="font-mono tabular-nums text-ink/70">
                  {value.toFixed(3)}
                </span>
                <span className="font-mono text-[10px] tabular-nums text-ink/35">
                  {share}%
                </span>
                <span className="hidden flex-1 truncate text-ink/45 sm:block">
                  {segment.explain}
                </span>
              </div>
            );
          })}
        </dl>
      )}
    </div>
  );
}

export default PriorityBar;
