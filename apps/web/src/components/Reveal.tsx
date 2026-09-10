"use client";

/**
 * Entrance animation on scroll, with a stagger.
 *
 * An IntersectionObserver flips `data-shown` and CSS does the rest (see the
 * `.reveal` rules in globals.css). No animation library: the motion is a
 * fade/rise/scale, which CSS handles natively, and pulling in a ~70 KB
 * runtime for it would be a poor trade.
 *
 * Two details that matter more than the effect itself:
 *
 * - Content is never *withheld* by animation. The observer disconnects after
 *   firing once, `prefers-reduced-motion` short-circuits to the final state
 *   in CSS, and if IntersectionObserver is missing entirely everything is
 *   shown immediately. A visitor should never end up staring at an
 *   invisible page because a script did not run.
 * - `once` is the default. Re-animating on every scroll-by is a distraction,
 *   not delight.
 */

import { useEffect, useRef, useState } from "react";

export function Reveal({
  children,
  delay = 0,
  className = "",
  as: Tag = "div",
}: {
  children: React.ReactNode;
  /** Stagger offset in ms. The skill's Standard preset is ~60ms per item. */
  delay?: number;
  className?: string;
  as?: "div" | "section" | "li" | "article" | "header";
}) {
  const ref = useRef<HTMLElement | null>(null);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    if (typeof IntersectionObserver === "undefined") {
      setShown(true);
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setShown(true);
            observer.disconnect();
          }
        }
      },
      // A small negative bottom margin means the animation starts just
      // before the card is fully in view, so it reads as already in motion
      // rather than popping once it lands.
      { threshold: 0.1, rootMargin: "0px 0px -8% 0px" },
    );

    observer.observe(node);

    // Deadline. Intersection callbacks are throttled to a standstill in a
    // hidden or background tab, which is a real state — open the site in a
    // background tab and switch to it later — and observed in testing as
    // every element stuck at opacity 0. After this the content shows
    // regardless of whether the observer ever had anything to say.
    const deadline = window.setTimeout(() => {
      setShown(true);
      observer.disconnect();
    }, 1500);

    return () => {
      observer.disconnect();
      window.clearTimeout(deadline);
    };
  }, []);

  return (
    <Tag
      ref={ref as never}
      className={`reveal ${className}`}
      data-shown={shown ? "true" : "false"}
      style={{ "--reveal-delay": `${delay}ms` } as React.CSSProperties}
    >
      {children}
    </Tag>
  );
}

export default Reveal;
