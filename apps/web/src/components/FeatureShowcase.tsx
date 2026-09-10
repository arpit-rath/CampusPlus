/**
 * Capability cards, laid out like Adobe's "Everything you need to make
 * anything" row: a labelled header, a tall visual, then a headline and a
 * line of copy.
 *
 * The visuals are built rather than photographed, and that is deliberate.
 * Adobe fills those panels with brand art because it sells creative tools;
 * this product's argument is that it can tell two reports apart, so each
 * panel shows the mechanism it is describing — three reports converging
 * into one, a real weighted priority bar, an actual similarity score. Stock
 * photography would say nothing a reader could check.
 *
 * Pure presentation: no client hooks, so this renders on the server and
 * ships no JavaScript.
 */

import { categoryLabel } from "@/lib/campus";
import { BoltIcon, ChatIcon, LayersIcon, ScaleIcon, ShieldIcon } from "./icons";

interface Capability {
  eyebrow: string;
  icon: React.ReactNode;
  title: string;
  body: string;
  visual: React.ReactNode;
}

/** Shared frame so every panel is the same height and radius. */
function Panel({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`relative flex h-64 items-center justify-center overflow-hidden rounded-xl ${className}`}
      aria-hidden="true"
    >
      {children}
    </div>
  );
}

const CAPABILITIES: Capability[] = [
  {
    eyebrow: "Similarity",
    icon: <LayersIcon />,
    title: "Three reports, one problem.",
    body: "Near-identical complaints collapse into a single case instead of three tickets nobody connects.",
    visual: (
      <Panel className="bg-gradient-to-br from-signal/25 via-signal/10 to-transparent">
        <svg viewBox="0 0 200 200" className="h-full w-full">
          <g stroke="rgb(var(--signal))" strokeWidth="1.5" fill="none" opacity="0.5">
            <path d="M52 52 L100 100" />
            <path d="M148 52 L100 100" />
            <path d="M52 148 L100 100" />
          </g>
          {[
            [52, 52],
            [148, 52],
            [52, 148],
          ].map(([cx, cy]) => (
            <circle
              key={`${cx}-${cy}`}
              cx={cx}
              cy={cy}
              r="13"
              fill="rgb(var(--surface))"
              stroke="rgb(var(--signal))"
              strokeWidth="2"
            />
          ))}
          <circle cx="100" cy="100" r="26" fill="rgb(var(--signal))" />
          <text
            x="100"
            y="107"
            textAnchor="middle"
            className="font-mono"
            fontSize="18"
            fontWeight="700"
            fill="rgb(var(--on-signal))"
          >
            1
          </text>
        </svg>
      </Panel>
    ),
  },
  {
    eyebrow: "Recurrence",
    icon: <BoltIcon />,
    title: "Counted by students, not submissions.",
    body: "Three independent people makes it recurring. One person reporting five times does not.",
    visual: (
      <Panel className="bg-gradient-to-br from-critical/25 via-critical/10 to-transparent">
        <div className="flex flex-col items-center gap-3">
          <div className="flex gap-2">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="flex h-11 w-11 items-center justify-center rounded-full border-2 border-critical bg-surface"
              >
                <svg viewBox="0 0 24 24" className="h-5 w-5 text-critical" fill="currentColor">
                  <circle cx="12" cy="8" r="3.6" />
                  <path d="M4.5 20a7.5 7.5 0 0 1 15 0Z" />
                </svg>
              </span>
            ))}
          </div>
          <span className="rounded-full bg-critical px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-on-critical">
            Recurring
          </span>
        </div>
      </Panel>
    ),
  },
  {
    eyebrow: "Priority",
    icon: <ScaleIcon />,
    title: "A score that shows its working.",
    body: "Four weighted terms, drawn to scale. The bar is not a picture of the number — it is the formula.",
    visual: (
      <Panel className="bg-gradient-to-br from-calm/25 via-calm/10 to-transparent">
        <div className="w-4/5">
          <p className="mb-3 text-center font-mono text-4xl font-bold tabular-nums text-ink">
            0.74
          </p>
          <div className="flex h-3 w-full overflow-hidden rounded-full bg-ink/10">
            <span className="bg-critical" style={{ width: "40%" }} />
            <span className="bg-signal" style={{ width: "30%" }} />
            <span className="bg-hazard" style={{ width: "20%" }} />
            <span className="bg-calm" style={{ width: "10%" }} />
          </div>
          <div className="mt-3 flex justify-between font-mono text-[10px] text-ink/70">
            <span>severity</span>
            <span>students</span>
            <span>safety</span>
            <span>age</span>
          </div>
        </div>
      </Panel>
    ),
  },
  {
    eyebrow: "Evidence",
    icon: <ShieldIcon />,
    title: "The photo has to agree.",
    body: "One multimodal call reads the description and the image together, and says whether they match.",
    visual: (
      <Panel className="bg-gradient-to-br from-hazard/20 via-hazard/10 to-transparent">
        <div className="relative">
          <div className="flex h-28 w-36 items-center justify-center rounded-lg border-2 border-ink/20 bg-surface">
            <svg viewBox="0 0 24 24" className="h-10 w-10 text-ink/30" fill="currentColor">
              <path d="M4 5h16v14H4z" opacity="0.25" />
              <path d="M6 17l4.5-5.5 3 3.5L16 12l3 5z" />
              <circle cx="8.5" cy="8.5" r="1.8" />
            </svg>
          </div>
          <span className="absolute -bottom-3 -right-3 flex h-11 w-11 items-center justify-center rounded-full bg-calm">
            <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="rgb(var(--surface))" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
              <path d="m5 13 4 4L19 7" />
            </svg>
          </span>
        </div>
      </Panel>
    ),
  },
  {
    eyebrow: "Ask",
    icon: <ChatIcon />,
    title: "Ask it like a person.",
    body: "Questions become typed filters. The model reads real rows and never writes a query of its own.",
    visual: (
      <Panel className="bg-gradient-to-br from-signal/20 via-calm/10 to-transparent">
        <div className="w-4/5 space-y-2.5">
          <p className="rounded-xl rounded-br-sm bg-ink px-3 py-2 text-[11px] leading-snug text-paper">
            Which hostel has the most urgent recurring problems?
          </p>
          <p className="rounded-xl rounded-bl-sm border border-ink/15 bg-surface px-3 py-2 text-[11px] leading-snug text-ink/80">
            {categoryLabel("electrical")} in Hostel Block B — 3 students,
            priority 0.74.
          </p>
        </div>
      </Panel>
    ),
  },
];

export function FeatureShowcase() {
  return (
    <section aria-labelledby="capabilities-heading" className="w-full">
      <div className="mx-auto max-w-6xl text-center">
        <h2
          id="capabilities-heading"
          className="text-balance text-3xl font-bold tracking-tight sm:text-5xl"
        >
          Everything you need to fix a campus.
        </h2>
        <p className="mx-auto mt-4 max-w-2xl text-base leading-relaxed text-ink/75 sm:text-lg">
          Whether you are a student with a leaking ceiling or the facilities
          lead deciding what gets fixed first, CampusPlus turns scattered
          reports into one ranked, explainable queue.
        </p>
      </div>

      {/* Five across on a wide screen, scrolling horizontally below that —
          five columns squeezed onto a phone would make every card unreadable. */}
      <ul className="mt-12 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-5">
        {CAPABILITIES.map((item) => (
          <li
            key={item.title}
            className="flex flex-col overflow-hidden rounded-bento border border-ink/10 bg-surface/70 backdrop-blur transition-transform duration-200 hover:-translate-y-1"
          >
            <div className="flex items-center gap-2 px-4 py-3">
              <span className="h-5 w-5 shrink-0 text-signal-ink">{item.icon}</span>
              <span className="text-sm font-semibold text-ink">{item.eyebrow}</span>
            </div>

            <div className="px-4">{item.visual}</div>

            <div className="flex flex-1 flex-col px-4 pb-5 pt-4">
              <h3 className="text-balance font-semibold leading-snug text-ink">
                {item.title}
              </h3>
              <p className="mt-1.5 text-sm leading-relaxed text-ink/70">
                {item.body}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default FeatureShowcase;
