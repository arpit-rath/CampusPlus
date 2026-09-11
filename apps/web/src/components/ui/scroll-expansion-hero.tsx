"use client";

/**
 * ScrollExpandMedia — media that grows from a card to full-bleed as you
 * scroll, holding the page until the expansion finishes.
 *
 * Adapted from the supplied component. The structure, props and behaviour
 * are kept; four things were changed because the original would have failed
 * the accessibility bar the rest of this app is held to:
 *
 * 1. `prefers-reduced-motion` now short-circuits the whole effect. The
 *    original locked the page and animated regardless, which is precisely
 *    the case that setting exists to prevent. Reduced-motion visitors get
 *    the expanded state immediately and a page that scrolls normally.
 * 2. Escape, End, or Page Down releases the lock. Holding scroll hostage
 *    with no keyboard escape traps anyone not using a wheel — the original
 *    listened only for `wheel` and `touch`, so a keyboard user could not
 *    get past the hero at all.
 * 3. The lock releases itself after a few seconds of no input. If the
 *    wheel handler never fires (a trackpad quirk, a script error) the
 *    original left the page permanently stuck at the top.
 * 4. Colours come from the project's design tokens instead of hardcoded
 *    `text-blue-200`, so it works in both themes.
 *
 * Scroll-jacking is worth using sparingly and this is the one place it
 * earns its keep: the expansion *is* the point of the hero. Everything
 * below it scrolls normally.
 */

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import Image from "next/image";
import { motion } from "framer-motion";

interface ScrollExpandMediaProps {
  mediaType?: "video" | "image";
  mediaSrc: string;
  posterSrc?: string;
  bgImageSrc: string;
  title?: string;
  date?: string;
  scrollToExpand?: string;
  textBlend?: boolean;
  children?: ReactNode;
}

const ScrollExpandMedia = ({
  mediaType = "image",
  mediaSrc,
  posterSrc,
  bgImageSrc,
  title,
  date,
  scrollToExpand,
  textBlend,
  children,
}: ScrollExpandMediaProps) => {
  const [scrollProgress, setScrollProgress] = useState(0);
  const [showContent, setShowContent] = useState(false);
  const [mediaFullyExpanded, setMediaFullyExpanded] = useState(false);
  const [isMobileState, setIsMobileState] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);

  const touchStartY = useRef(0);
  const sectionRef = useRef<HTMLDivElement | null>(null);

  // Set once the intro has played through. The idle failsafe below reads it
  // so that deliberately scrolling back up to replay the animation is not
  // immediately undone by the timer snapping the media open again.
  const hasExpandedOnce = useRef(false);

  // Progress is mirrored in a ref because `advance` runs from a listener
  // that closes over the state value. Several wheel events inside one React
  // batch would all read the same stale progress and only the last would
  // count, so a fast flick moved the animation about as far as a single
  // tick. The ref always holds the live value.
  const progressRef = useRef(0);

  const expandNow = useCallback(() => {
    hasExpandedOnce.current = true;
    progressRef.current = 1;
    setScrollProgress(1);
    setMediaFullyExpanded(true);
    setShowContent(true);
  }, []);

  // Reduced motion: skip the sequence entirely rather than animate anyway.
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => {
      setReducedMotion(query.matches);
      if (query.matches) expandNow();
    };
    apply();
    query.addEventListener("change", apply);
    return () => query.removeEventListener("change", apply);
  }, [expandNow]);

  // Viewport is tracked, not just a mobile boolean, because the card's size
  // has to be computed against the real available height to keep its aspect
  // ratio (see `mediaWidth` below).
  const [viewport, setViewport] = useState({ w: 1280, h: 800 });

  useEffect(() => {
    const measure = () => {
      setIsMobileState(window.innerWidth < 768);
      setViewport({ w: window.innerWidth, h: window.innerHeight });
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  useEffect(() => {
    if (reducedMotion) return;

    let idleTimer: number | undefined;

    // Failsafe for the *first* pass only: if nothing moves the progress for
    // a while, stop holding the page. A hero that will not let go is worse
    // than one that does not animate.
    //
    // It deliberately stops arming once the intro has played, otherwise
    // scrolling back up to watch the animation in reverse would be fought
    // by a timer forcing the media open again six seconds later.
    const armIdleRelease = () => {
      if (hasExpandedOnce.current) return;
      window.clearTimeout(idleTimer);
      idleTimer = window.setTimeout(() => {
        if (!mediaFullyExpanded) expandNow();
      }, 6000);
    };
    armIdleRelease();

    const advance = (delta: number) => {
      const next = Math.min(Math.max(progressRef.current + delta, 0), 1);
      progressRef.current = next;
      setScrollProgress(next);
      if (next >= 1) {
        // Also marks the intro as seen. Only `expandNow` used to do this,
        // so an expansion completed by scrolling — the normal path — left
        // the idle failsafe armed. Rewinding then got snapped back to fully
        // open six seconds later, which looked like the reverse was broken.
        hasExpandedOnce.current = true;
        setMediaFullyExpanded(true);
        setShowContent(true);
      } else if (next < 0.75) {
        setShowContent(false);
      }
      armIdleRelease();
    };

    const handleWheel = (e: globalThis.WheelEvent) => {
      // Scrolling up while already at the very top re-enters the animation,
      // which then plays in reverse as `advance` takes negative deltas.
      //
      // The `scrollY <= 2` guard is what makes this safe. An earlier version
      // used a looser check and, combined with the scrollTo(0, 0) below,
      // would grab a reader who was halfway down the page and yank them back
      // to the hero. Re-entry has to require actually being at the top.
      if (mediaFullyExpanded) {
        if (e.deltaY < 0 && window.scrollY <= 2) {
          setMediaFullyExpanded(false);
          e.preventDefault();
        }
        return;
      }
      e.preventDefault();
      advance(e.deltaY * 0.0009);
    };

    const handleTouchStart = (e: globalThis.TouchEvent) => {
      touchStartY.current = e.touches[0].clientY;
    };

    const handleTouchMove = (e: globalThis.TouchEvent) => {
      if (!touchStartY.current) return;
      const touchY = e.touches[0].clientY;
      const deltaY = touchStartY.current - touchY;

      // Same re-entry rule as the wheel: an upward swipe while already at
      // the top rewinds the intro.
      if (mediaFullyExpanded) {
        if (deltaY < -20 && window.scrollY <= 2) {
          setMediaFullyExpanded(false);
          e.preventDefault();
        }
        return;
      }
      e.preventDefault();
      advance(deltaY * (deltaY < 0 ? 0.008 : 0.005));
      touchStartY.current = touchY;
    };

    const handleTouchEnd = () => {
      touchStartY.current = 0;
    };

    // Keyboard escape hatch. Without this the hero is a wall for anyone
    // navigating by keyboard.
    const handleKey = (e: globalThis.KeyboardEvent) => {
      if (mediaFullyExpanded) return;
      if (["Escape", "End", "PageDown", "Enter", " "].includes(e.key)) {
        e.preventDefault();
        expandNow();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        advance(0.15);
      }
    };

    const handleScroll = () => {
      if (!mediaFullyExpanded) window.scrollTo(0, 0);
    };

    window.addEventListener("wheel", handleWheel, { passive: false });
    window.addEventListener("scroll", handleScroll);
    window.addEventListener("touchstart", handleTouchStart, { passive: false });
    window.addEventListener("touchmove", handleTouchMove, { passive: false });
    window.addEventListener("touchend", handleTouchEnd);
    window.addEventListener("keydown", handleKey);

    return () => {
      window.clearTimeout(idleTimer);
      window.removeEventListener("wheel", handleWheel);
      window.removeEventListener("scroll", handleScroll);
      window.removeEventListener("touchstart", handleTouchStart);
      window.removeEventListener("touchmove", handleTouchMove);
      window.removeEventListener("touchend", handleTouchEnd);
      window.removeEventListener("keydown", handleKey);
    };
  }, [mediaFullyExpanded, reducedMotion, expandNow]);

  // The card holds a 16:9 aspect at every stage of the expansion, rather
  // than morphing from portrait to landscape as the original did. The media
  // is a wide campus map: a portrait card would `object-cover` it down to a
  // narrow slice, hiding most of the campus during the part of the
  // animation the visitor actually watches.
  //
  // The ceiling is computed from both viewport axes rather than left to CSS
  // `max-width`/`max-height`. Those clamp one dimension independently, which
  // silently breaks the ratio — measured at 1.659 instead of 1.778 on a
  // short window, i.e. the map cropped after all. Capping the width by
  // whichever axis binds first keeps 16:9 exact at every size.
  const MEDIA_RATIO = 16 / 9;
  const widthCeiling = Math.min(
    viewport.w * 0.95,
    viewport.h * 0.85 * MEDIA_RATIO,
  );
  const mediaWidth = Math.min(
    340 + scrollProgress * (isMobileState ? 620 : 1400),
    widthCeiling,
  );
  const mediaHeight = mediaWidth / MEDIA_RATIO;
  const textTranslateX = scrollProgress * (isMobileState ? 180 : 150);

  const firstWord = title ? title.split(" ")[0] : "";
  const restOfTitle = title ? title.split(" ").slice(1).join(" ") : "";

  return (
    <div
      ref={sectionRef}
      className="overflow-x-hidden transition-colors duration-700 ease-in-out"
    >
      <section className="relative flex min-h-[100dvh] flex-col items-center justify-start">
        <div className="relative flex min-h-[100dvh] w-full flex-col items-center">
          <motion.div
            className="absolute inset-0 z-0 h-full"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 - scrollProgress }}
            transition={{ duration: 0.1 }}
          >
            <Image
              src={bgImageSrc}
              alt=""
              width={1920}
              height={1080}
              className="h-screen w-screen"
              style={{ objectFit: "cover", objectPosition: "center" }}
              priority
            />
            {/* Scrim: the hero text sits on a photograph, and a photograph
                is not a contrast guarantee. */}
            <div className="absolute inset-0 bg-black/45" />
          </motion.div>

          <div className="container relative z-10 mx-auto flex flex-col items-center justify-start">
            <div className="relative flex h-[100dvh] w-full flex-col items-center justify-center">
              <div
                className="absolute left-1/2 top-1/2 z-0 -translate-x-1/2 -translate-y-1/2 rounded-2xl transition-none"
                style={{
                  width: `${mediaWidth}px`,
                  height: `${mediaHeight}px`,
                  // No maxWidth/maxHeight here on purpose: the ceiling is
                  // already applied to `mediaWidth` against both axes, and a
                  // CSS clamp on one dimension alone would reintroduce the
                  // ratio break it exists to prevent.
                  boxShadow: "0px 0px 50px rgba(0, 0, 0, 0.3)",
                }}
              >
                {mediaType === "video" ? (
                  <div className="pointer-events-none relative h-full w-full">
                    <video
                      src={mediaSrc}
                      poster={posterSrc}
                      autoPlay
                      muted
                      loop
                      playsInline
                      preload="auto"
                      className="h-full w-full rounded-xl object-cover"
                      controls={false}
                      disablePictureInPicture
                    />
                    <motion.div
                      className="absolute inset-0 rounded-xl bg-black/30"
                      initial={{ opacity: 0.7 }}
                      animate={{ opacity: 0.5 - scrollProgress * 0.3 }}
                      transition={{ duration: 0.2 }}
                    />
                  </div>
                ) : (
                  <div className="relative h-full w-full">
                    {/* Intrinsic size matches the 16:9 source, and the card
                        holds the same ratio, so `object-cover` has nothing
                        to crop — the whole campus stays visible throughout
                        the expansion. */}
                    <Image
                      src={mediaSrc}
                      alt={title || "Media content"}
                      width={1672}
                      height={941}
                      sizes="(max-width: 768px) 95vw, 1600px"
                      className="h-full w-full rounded-xl bg-surface object-cover"
                      priority
                    />
                    {/* Fades off as the media expands, so the map is fully
                        legible once it is the focus of the screen. */}
                    <motion.div
                      className="absolute inset-0 rounded-xl bg-black/50"
                      initial={{ opacity: 0.7 }}
                      animate={{ opacity: Math.max(0, 0.6 - scrollProgress * 0.85) }}
                      transition={{ duration: 0.2 }}
                    />
                  </div>
                )}

                <div className="relative z-10 mt-4 flex flex-col items-center text-center transition-none">
                  {date && (
                    <p
                      className="text-2xl font-medium text-white/90"
                      style={{ transform: `translateX(-${textTranslateX}vw)` }}
                    >
                      {date}
                    </p>
                  )}
                  {scrollToExpand && (
                    <p
                      className="text-center font-medium text-white/80"
                      style={{ transform: `translateX(${textTranslateX}vw)` }}
                    >
                      {scrollToExpand}
                    </p>
                  )}
                </div>
              </div>

              <div
                className={`relative z-10 flex w-full flex-col items-center justify-center gap-4 text-center transition-none ${
                  textBlend ? "mix-blend-difference" : "mix-blend-normal"
                }`}
              >
                <motion.h1
                  className="text-4xl font-bold text-white [text-shadow:0_2px_18px_rgb(0_0_0/0.55)] transition-none md:text-5xl lg:text-6xl"
                  style={{ transform: `translateX(-${textTranslateX}vw)` }}
                >
                  {firstWord}
                </motion.h1>
                <motion.h1
                  className="text-center text-4xl font-bold text-white [text-shadow:0_2px_18px_rgb(0_0_0/0.55)] transition-none md:text-5xl lg:text-6xl"
                  style={{ transform: `translateX(${textTranslateX}vw)` }}
                >
                  {restOfTitle}
                </motion.h1>
              </div>

              {/* Visible, focusable way past the hero. Also the only way
                  through for anyone whose input the wheel handler misses. */}
              {!mediaFullyExpanded && !reducedMotion && (
                <button
                  type="button"
                  onClick={expandNow}
                  className="absolute bottom-10 z-20 rounded-full border border-white/40 bg-black/40 px-4 py-2 text-sm font-medium text-white backdrop-blur transition-colors hover:bg-black/60"
                >
                  Skip intro
                </button>
              )}
            </div>

            <motion.section
              className="flex w-full flex-col"
              initial={{ opacity: 0 }}
              animate={{ opacity: showContent ? 1 : 0 }}
              transition={{ duration: 0.7 }}
              aria-hidden={!showContent}
            >
              {children}
            </motion.section>
          </div>
        </div>
      </section>
    </div>
  );
};

export default ScrollExpandMedia;
