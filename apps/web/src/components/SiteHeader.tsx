/**
 * The landing-page bar.
 *
 * Fixed rather than in flow because the hero holds the page while the map
 * expands: an in-flow header would be scrolled away by a page that is not
 * scrolling yet, and the two destinations that matter — report something,
 * open the command center — would be unreachable until the intro finished.
 *
 * Shaped after the grouped-capsule pattern the AI-infrastructure sites have
 * converged on (Cerebrium et al): mark and wordmark hard left, one capsule
 * on the right holding every control, the primary action filled in the
 * accent colour, labels in small uppercase mono with wide tracking.
 *
 * Two deliberate departures from that reference:
 *
 * - It spans the viewport instead of sitting in a centred container. A
 *   max-width container pushed both ends inward and left the middle empty.
 * - The wordmark keeps a surface behind it. Those sites are dark-only, so
 *   white-on-hero always works; this bar floats over a photograph in both
 *   themes, and a bare wordmark cannot be guaranteed a contrast ratio
 *   against whatever pixels the photo puts underneath it.
 */

import Link from "next/link";
import { ThemeToggle } from "@/components/ThemeToggle";
import { BrandMark } from "@/components/icons";

/** Every control in the capsule is 36px tall inside 44px of capsule. */
const ITEM =
  "inline-flex h-9 items-center rounded-full px-2.5 font-mono text-[10px] uppercase tracking-[0.08em] transition-colors sm:px-4 sm:text-[11px] sm:tracking-[0.14em]";

export function SiteHeader() {
  return (
    <header className="fixed inset-x-0 top-0 z-50">
      {/* Wraps rather than clips: below roughly 370px the wordmark and the
          capsule stop fitting one line, and the capsule drops beneath. */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-3 sm:px-6">
        <Link
          href="/"
          className="inline-flex h-11 items-center gap-2 rounded-full border border-ink/10 bg-surface/70 px-2.5 backdrop-blur transition-transform hover:scale-[1.02] sm:gap-2.5 sm:px-4"
        >
          <BrandMark className="h-4 w-4 text-signal-ink sm:h-[18px] sm:w-[18px]" />
          <span className="text-sm font-semibold tracking-tight text-ink sm:text-base">
            CampusPlus
          </span>
        </Link>

        <nav
          aria-label="Primary"
          className="ml-auto flex h-11 items-center gap-1 rounded-full border border-ink/10 bg-surface/70 p-1 backdrop-blur"
        >
          <Link
            href="/dashboard"
            className={`${ITEM} font-medium text-ink/70 hover:bg-ink/10 hover:text-ink`}
          >
            {/* Short label first, so the bar still fits a small phone. */}
            <span className="sm:hidden">Admin</span>
            <span className="hidden sm:inline">Admin login</span>
          </Link>

          <Link
            href="/report"
            className={`${ITEM} bg-signal-fill font-semibold text-on-signal hover:brightness-105`}
          >
            <span className="sm:hidden">Report</span>
            <span className="hidden sm:inline">Report a problem</span>
          </Link>

          <span aria-hidden="true" className="mx-0.5 h-5 w-px bg-ink/15" />

          <ThemeToggle variant="inline" />
        </nav>
      </div>
    </header>
  );
}

export default SiteHeader;
