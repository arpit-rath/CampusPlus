import Link from "next/link";

/**
 * Landing page. Says what the product actually is — an intelligence layer,
 * not a form — because that framing is the entire pitch and it should be
 * visible before anyone clicks anything.
 */

const PIPELINE = [
  {
    step: "01",
    title: "Understand",
    body: "One multimodal call reads the description and the photo, and returns a category, a 1-5 severity, a safety flag and a normalized summary.",
  },
  {
    step: "02",
    title: "Embed",
    body: "The normalized summary — not the raw text — becomes a 768-dimension vector, so two students phrasing the same problem differently still land close together.",
  },
  {
    step: "03",
    title: "Match",
    body: "pgvector cosine search, scoped to the same category, the same building and a 14-day window. Above 0.92 it merges; between 0.75 and 0.92 a human decides.",
  },
  {
    step: "04",
    title: "Escalate",
    body: "Three independent students on one cluster makes it a recurring issue, and every member's priority rises with it.",
  },
];

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col justify-center gap-12 px-6 py-16">
      <section>
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-ink/50">
          CampusPluse
        </p>
        <h1 className="mt-3 max-w-2xl text-4xl font-bold leading-tight tracking-tight sm:text-5xl">
          The intelligence layer, not the form, is the product.
        </h1>
        <p className="mt-4 max-w-xl text-lg text-ink/70">
          Students report campus problems. CampusPluse works out which reports
          are the <em>same</em> problem, which problems keep coming back, and
          which ones actually deserve attention first — and explains every one
          of those decisions.
        </p>

        <div className="mt-7 flex flex-wrap gap-3">
          <Link
            href="/report"
            className="rounded-lg bg-signal px-5 py-2.5 font-medium text-white transition-opacity hover:opacity-90"
          >
            Report a problem
          </Link>
          <Link
            href="/dashboard"
            className="rounded-lg border border-ink/20 px-5 py-2.5 font-medium transition-colors hover:bg-ink/5"
          >
            Admin command center
          </Link>
        </div>
      </section>

      <section>
        <h2 className="font-mono text-xs uppercase tracking-widest text-ink/45">
          What happens when you press submit
        </h2>
        <ol className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          {PIPELINE.map((stage) => (
            <li
              key={stage.step}
              className="rounded-xl border border-ink/10 bg-white/60 p-4"
            >
              <p className="font-mono text-xs text-signal">{stage.step}</p>
              <h3 className="mt-1 font-semibold text-ink">{stage.title}</h3>
              <p className="mt-1 text-sm leading-relaxed text-ink/65">{stage.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="rounded-xl border border-ink/10 bg-white/60 p-5">
        <h2 className="font-mono text-xs uppercase tracking-widest text-ink/45">
          Priority is never a black box
        </h2>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-ink/70">
          Every score is the sum of four visible terms — severity, how many
          independent students reported it, whether it is a safety risk, and how
          long it has sat open. The bar in the UI is not a picture of the score;
          it is the formula, drawn to scale.
        </p>
        <p className="mt-3 font-mono text-xs text-ink/45">
          0.40·severity + 0.30·log1p(students)/log1p(cap) + 0.20·safety +
          0.10·age
        </p>
      </section>
    </main>
  );
}
