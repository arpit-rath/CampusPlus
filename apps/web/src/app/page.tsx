import fs from "node:fs";
import path from "node:path";
import Link from "next/link";
import ScrollExpandMedia from "@/components/ui/scroll-expansion-hero";
import { FeatureShowcase } from "@/components/FeatureShowcase";
import { SiteHeader } from "@/components/SiteHeader";

/**
 * Landing page.
 *
 * Reads top to bottom as: what this is (hero, the campus map expanding under
 * the scroll) -> what the product actually does (a paragraph, plainly) ->
 * what it can do (capability cards) -> where to go next (report, or admin).
 *
 * Every number quoted is a real constant from the system — 0.92, three
 * students, 768 dimensions, 14 days — not marketing rounding.
 */

/**
 * The hero background.
 *
 * Accepts any of the common extensions for `public/campus-quad.*` so
 * swapping the photo does not mean editing code. Falls back to the campus
 * map — a local asset that is definitely present — rather than a remote
 * URL: a stock fallback would mean shipping a remote-image allowlist for a
 * request that never happens once the real photo is committed, and a broken
 * image if the network is down mid-demo.
 *
 * Resolved on the server at render time, so the check costs the client
 * nothing.
 */
function resolveHeroBackground(): string {
  const publicDir = path.join(process.cwd(), "public");
  for (const name of [
    "campus-quad.jpg",
    "campus-quad.jpeg",
    "campus-quad.png",
    "campus-quad.webp",
  ]) {
    try {
      if (fs.existsSync(path.join(publicDir, name))) return `/${name}`;
    } catch {
      /* fs unavailable in some runtimes — fall through */
    }
  }
  return "/campus-map.png";
}

export default function Home() {
  const backgroundSrc = resolveHeroBackground();

  return (
    <main className="relative">
      {/* Floating, so it stays reachable during the scroll-locked hero. */}
      <SiteHeader />

      <ScrollExpandMedia
        mediaType="image"
        mediaSrc="/campus-map.png"
        bgImageSrc={backgroundSrc}
        title="CampusPlus Intelligence"
        date="One campus, one queue"
        scrollToExpand="Scroll to explore the campus"
        // Deliberately not `textBlend`. mix-blend-difference makes the
        // rendered text colour a function of whatever pixels sit behind it,
        // which cannot be measured for contrast — and over a pale campus map
        // it lands in muddy mid-tones. The media carries a dark scrim while
        // the title is over it, so plain white is both predictable and
        // higher contrast.
      >
        <div className="mx-auto w-full max-w-6xl px-5 pb-24 sm:px-8">
          {/* --- what this is ------------------------------------------- */}
          <section className="mx-auto max-w-3xl py-16 text-center sm:py-24">
            <p className="font-mono text-xs uppercase tracking-[0.18em] text-signal-ink">
              What CampusPlus is
            </p>
            <h2 className="mt-4 text-balance text-3xl font-bold leading-tight tracking-tight sm:text-4xl">
              The intelligence layer, not the form, is the product.
            </h2>
            <p className="mt-5 text-base leading-relaxed text-ink/75 sm:text-lg">
              Students report campus problems — a leaking ceiling, a dead
              router, sparking wiring in a basement. Most systems file each one
              as its own ticket and leave a human to notice they are the same
              thing. CampusPlus works that out itself: it reads each report,
              turns it into a vector, and compares it against everything
              recently reported in the same building.
            </p>
            <p className="mt-4 text-base leading-relaxed text-ink/75 sm:text-lg">
              Duplicates merge. Problems that keep coming back get flagged.
              Everything lands in one queue ranked by a score that shows its
              own arithmetic — so the facilities team can see not just what is
              urgent, but why.
            </p>

            <dl className="mt-12 grid grid-cols-2 gap-x-6 gap-y-7 sm:grid-cols-4">
              {[
                { value: "768", label: "vector dimensions" },
                { value: "0.92", label: "auto-merge threshold" },
                { value: "3", label: "students to recur" },
                { value: "14d", label: "matching window" },
              ].map((stat) => (
                <div key={stat.label}>
                  <dt className="font-mono text-2xl font-bold tabular-nums text-ink sm:text-3xl">
                    {stat.value}
                  </dt>
                  <dd className="mt-1 text-xs leading-snug text-ink/70">
                    {stat.label}
                  </dd>
                </div>
              ))}
            </dl>
          </section>

          {/* --- capabilities -------------------------------------------- */}
          <div className="py-8 sm:py-12">
            <FeatureShowcase />
          </div>

          {/* --- where to go next ---------------------------------------- */}
          <section
            aria-labelledby="cta-heading"
            className="glass bento-card mt-20 px-6 py-14 text-center sm:px-12"
          >
            <h2
              id="cta-heading"
              className="text-balance text-3xl font-bold tracking-tight sm:text-4xl"
            >
              Ready when you are.
            </h2>
            <p className="mx-auto mt-4 max-w-xl text-base leading-relaxed text-ink/75">
              Report something that needs fixing, or open the command center to
              see what the campus is dealing with right now.
            </p>

            <div className="mt-9 flex flex-col items-stretch justify-center gap-3 sm:flex-row sm:items-center">
              <Link
                href="/report"
                className="inline-flex h-12 items-center justify-center rounded-full bg-signal-fill px-8 font-medium text-on-signal shadow-card transition-transform hover:scale-[1.03] active:scale-[0.99]"
              >
                Report a problem
              </Link>
              <Link
                href="/dashboard"
                className="inline-flex h-12 items-center justify-center rounded-full border border-ink/25 bg-surface/70 px-8 font-medium text-ink backdrop-blur transition-transform hover:scale-[1.03] active:scale-[0.99]"
              >
                Log in as admin
              </Link>
            </div>

            <p className="mt-6 text-xs text-ink/70">
              Students do not need an account. Admin actions are gated by a
              token when one is configured.
            </p>
          </section>

          <footer className="mt-16 border-t border-ink/10 pt-6 text-center">
            <p className="text-xs text-ink/70">
              CampusPlus — campus problem intelligence.
            </p>
          </footer>
        </div>
      </ScrollExpandMedia>
    </main>
  );
}
