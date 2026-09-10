import Link from "next/link";
import { Reveal } from "@/components/Reveal";
import { ThemeToggle } from "@/components/ThemeToggle";
import {
  BoltIcon,
  ChatIcon,
  LayersIcon,
  RouteIcon,
  ScaleIcon,
  ShieldIcon,
  SparkIcon,
} from "@/components/icons";

/**
 * Landing page.
 *
 * Says what the product actually is — an intelligence layer, not a form —
 * because that framing is the entire pitch and it should be visible before
 * anyone clicks anything.
 *
 * The feature grid is a bento layout generated from `FEATURES` rather than
 * hand-placed markup: each entry carries its own column/row span, so adding
 * or reordering a capability is a data edit and the mosaic re-flows itself.
 * Spans collapse 4 -> 2 -> 1 across breakpoints.
 *
 * Every figure quoted below is a real constant from the system (0.92, three
 * students, 768 dimensions, 14 days), not marketing rounding.
 */

interface Feature {
  title: string;
  body: string;
  icon: React.ReactNode;
  /** Bento span at the 4-column breakpoint. */
  span: string;
  accent: "signal" | "calm" | "critical";
  stat?: { value: string; label: string };
}

const FEATURES: Feature[] = [
  {
    title: "Duplicate detection that actually merges",
    body: "Every report becomes a 768-dimension vector built from the AI's normalized summary, not the raw text. pgvector finds the nearest existing complaint in the same category and building. Above 0.92 cosine similarity it merges on the spot; between 0.75 and 0.92 it waits for a human.",
    icon: <LayersIcon />,
    span: "lg:col-span-2 lg:row-span-2",
    accent: "signal",
    stat: { value: "0.92", label: "auto-merge threshold" },
  },
  {
    title: "Recurring problems, counted honestly",
    body: "Three independent students on one cluster makes it recurring. Submissions are not students — one person reporting the same broken cooler five times never manufactures a campus-wide trend.",
    icon: <BoltIcon />,
    span: "lg:col-span-2",
    accent: "critical",
    stat: { value: "3", label: "independent students" },
  },
  {
    title: "Priority you can argue with",
    body: "Four weighted terms — severity, how many students, safety risk, age — stored per complaint and drawn to scale. The bar is not a picture of the score; it is the formula.",
    icon: <ScaleIcon />,
    span: "lg:col-span-1",
    accent: "calm",
  },
  {
    title: "Photo verification",
    body: "One multimodal call reads the description and the image together, and reports whether they actually agree.",
    icon: <ShieldIcon />,
    span: "lg:col-span-1",
    accent: "signal",
  },
  {
    title: "Deterministic routing, human override",
    body: "Category maps to department on fixed rules, not model whim. An admin can re-route in one click, and the decision sticks.",
    icon: <RouteIcon />,
    span: "lg:col-span-2",
    accent: "calm",
  },
  {
    title: "Ask in plain English",
    body: "“Which hostel has the most urgent recurring problems this week?” Questions become typed filters — the model never writes a query, and every cited complaint id is checked against the rows actually fetched.",
    icon: <ChatIcon />,
    span: "lg:col-span-2",
    accent: "signal",
  },
];

const ACCENT_RING: Record<Feature["accent"], string> = {
  signal: "text-signal-ink",
  calm: "text-calm",
  critical: "text-critical",
};

export default function Home() {
  return (
    <main className="relative min-h-screen overflow-hidden">
      <Aurora />

      <div className="relative mx-auto max-w-6xl px-5 pb-24 pt-6 sm:px-8">
        {/* --- top bar ------------------------------------------------- */}
        <header className="flex items-center justify-between gap-4">
          <span className="font-mono text-xs uppercase tracking-[0.2em] text-ink/70">
            CampusPlus
          </span>
          <ThemeToggle />
        </header>

        {/* --- hero ---------------------------------------------------- */}
        <section className="pb-16 pt-14 sm:pt-20">
          <Reveal>
            <p className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-surface/60 px-3 py-1 font-mono text-[11px] uppercase tracking-[0.16em] text-ink/70 backdrop-blur">
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-calm opacity-70" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-calm" />
              </span>
              Campus problem intelligence
            </p>
          </Reveal>

          <Reveal delay={80}>
            <h1 className="mt-6 max-w-3xl text-balance text-4xl font-bold leading-[1.08] tracking-tight sm:text-6xl">
              The intelligence layer,{" "}
              <span className="text-signal-ink">not the form</span>, is the
              product.
            </h1>
          </Reveal>

          <Reveal delay={160}>
            <p className="mt-6 max-w-2xl text-lg leading-relaxed text-ink/75">
              Students report campus problems. CampusPlus works out which
              reports are the <em className="not-italic font-semibold text-ink">same</em>{" "}
              problem, which problems keep coming back, and which ones deserve
              attention first — and explains every one of those decisions.
            </p>
          </Reveal>

          <Reveal delay={240}>
            <div className="mt-9 flex flex-wrap items-center gap-3">
              <Link
                href="/report"
                className="inline-flex h-12 items-center rounded-full bg-signal-fill px-6 font-medium text-on-signal shadow-card transition-transform hover:scale-[1.03] active:scale-[0.99]"
              >
                Report a problem
              </Link>
              <Link
                href="/dashboard"
                className="glass inline-flex h-12 items-center rounded-full px-6 font-medium text-ink transition-transform hover:scale-[1.03] active:scale-[0.99]"
              >
                Admin command center
              </Link>
            </div>
          </Reveal>

          <Reveal delay={320}>
            <dl className="mt-14 grid max-w-2xl grid-cols-2 gap-x-6 gap-y-6 sm:grid-cols-4">
              {[
                { value: "768", label: "vector dimensions" },
                { value: "0.92", label: "merge threshold" },
                { value: "3", label: "students to recur" },
                { value: "14d", label: "matching window" },
              ].map((item) => (
                <div key={item.label}>
                  <dt className="font-mono text-2xl font-semibold tabular-nums text-ink sm:text-3xl">
                    {item.value}
                  </dt>
                  <dd className="mt-1 text-xs leading-snug text-ink/70">
                    {item.label}
                  </dd>
                </div>
              ))}
            </dl>
          </Reveal>
        </section>

        {/* --- bento feature grid -------------------------------------- */}
        <section aria-labelledby="features-heading" className="pt-4">
          <Reveal>
            <h2
              id="features-heading"
              className="font-mono text-xs uppercase tracking-[0.16em] text-ink/70"
            >
              What happens when you press submit
            </h2>
          </Reveal>

          <div className="mt-5 grid auto-rows-[minmax(0,auto)] grid-cols-1 gap-[var(--grid-gap)] sm:grid-cols-2 lg:grid-cols-4">
            {FEATURES.map((feature, index) => (
              <Reveal
                key={feature.title}
                as="article"
                delay={index * 60}
                className={`${feature.span} glass bento-card flex flex-col p-6`}
              >
                <span className={`h-6 w-6 ${ACCENT_RING[feature.accent]}`}>
                  {feature.icon}
                </span>
                {/* text-balance stops a narrow bento cell orphaning the last
                    word of a heading onto its own line. */}
                <h3 className="mt-4 text-balance text-lg font-semibold leading-snug text-ink">
                  {feature.title}
                </h3>
                <p className="mt-2 flex-1 text-sm leading-relaxed text-ink/70">
                  {feature.body}
                </p>
                {feature.stat && (
                  <p className="mt-5 flex items-baseline gap-2">
                    <span
                      className={`font-mono text-3xl font-bold tabular-nums ${ACCENT_RING[feature.accent]}`}
                    >
                      {feature.stat.value}
                    </span>
                    <span className="text-xs text-ink/70">
                      {feature.stat.label}
                    </span>
                  </p>
                )}
              </Reveal>
            ))}
          </div>
        </section>

        {/* --- formula ------------------------------------------------- */}
        <Reveal as="section" className="glass bento-card mt-[var(--grid-gap)] p-6 sm:p-8">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 h-6 w-6 shrink-0 text-signal-ink">
              <SparkIcon />
            </span>
            <div>
              <h2 className="text-lg font-semibold text-ink">
                Priority is never a black box
              </h2>
              <p className="mt-2 max-w-3xl text-sm leading-relaxed text-ink/70">
                Every score is the sum of four visible terms. All four are
                stored per complaint, so the interface can show its working
                instead of asking anyone to trust a number.
              </p>
            </div>
          </div>

          <div className="mt-6 overflow-x-auto">
            <p className="w-max font-mono text-xs text-ink/75 sm:text-sm">
              <span className="text-critical">0.40·severity</span>
              {"  +  "}
              <span className="text-signal-ink">
                0.30·log1p(students)/log1p(cap)
              </span>
              {"  +  "}
              <span className="text-calm">0.20·safety</span>
              {"  +  "}
              <span className="text-ink/70">0.10·age</span>
            </p>
          </div>

          {/* A real 4-segment bar at the same weights the formula states. */}
          <div
            className="mt-4 flex h-2.5 w-full overflow-hidden rounded-full bg-ink/10"
            role="img"
            aria-label="Priority bar: severity 40 percent, recurrence 30 percent, safety 20 percent, age 10 percent"
          >
            <span className="bg-critical" style={{ width: "40%" }} />
            <span className="bg-signal" style={{ width: "30%" }} />
            <span className="bg-calm" style={{ width: "20%" }} />
            <span className="bg-ink/40" style={{ width: "10%" }} />
          </div>
        </Reveal>

        <footer className="mt-16 border-t border-ink/10 pt-6">
          <p className="text-xs text-ink/70">
            Report flow and admin console are both live —{" "}
            <Link href="/report" className="text-signal-ink underline underline-offset-2">
              file a report
            </Link>{" "}
            or{" "}
            <Link href="/dashboard" className="text-signal-ink underline underline-offset-2">
              open the dashboard
            </Link>
            .
          </p>
        </footer>
      </div>
    </main>
  );
}

/**
 * Ambient gradient wash behind the glass.
 *
 * Glassmorphism only reads as glass when there is something worth blurring
 * behind it — the style's own guidance calls for a vibrant backdrop. These
 * blobs are `aria-hidden` and sit under `pointer-events-none` so they are
 * decoration only, and their opacity is kept low enough that text on the
 * glass above still clears 4.5:1 over the brightest point.
 */
function Aurora() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      <div
        className="aurora-blob absolute -left-[15%] -top-[20%] h-[46rem] w-[46rem] rounded-full blur-3xl"
        style={{
          background:
            "radial-gradient(circle, rgb(var(--aurora-1) / var(--aurora-alpha)) 0%, transparent 68%)",
        }}
      />
      <div
        className="aurora-blob absolute -right-[18%] top-[6%] h-[40rem] w-[40rem] rounded-full blur-3xl"
        style={{
          animationDelay: "-6s",
          background:
            "radial-gradient(circle, rgb(var(--aurora-2) / var(--aurora-alpha)) 0%, transparent 68%)",
        }}
      />
      <div
        className="aurora-blob absolute bottom-[-15%] left-[25%] h-[38rem] w-[38rem] rounded-full blur-3xl"
        style={{
          animationDelay: "-12s",
          background:
            "radial-gradient(circle, rgb(var(--aurora-3) / var(--aurora-alpha)) 0%, transparent 70%)",
        }}
      />
    </div>
  );
}
