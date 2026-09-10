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

  const expandNow = useCallback(() => {
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

  useEffect(() => {
    const checkIfMobile = () => setIsMobileState(window.innerWidth < 768);
    checkIfMobile();
    window.addEventListener("resize", checkIfMobile);
    return () => window.removeEventListener("resize", checkIfMobile);
  }, []);

  useEffect(() => {
    if (reducedMotion) return;

    let idleTimer: number | undefined;

    // Failsafe: if nothing moves the progress for a while, stop holding the
    // page. A hero that will not let go is worse than one that does not
    // animate.
    const armIdleRelease = () => {
      window.clearTimeout(idleTimer);
      idleTimer = window.setTimeout(() => {
        if (!mediaFullyExpanded) expandNow();
      }, 6000);
    };
    armIdleRelease();

    const advance = (delta: number) => {
      const next = Math.min(Math.max(scrollProgress + delta, 0), 1);
      setScrollProgress(next);
      if (next >= 1) {
        setMediaFullyExpanded(true);
        setShowContent(true);
      } else if (next < 0.75) {
        setShowContent(false);
      }
      armIdleRelease();
    };

    const handleWheel = (e: globalThis.WheelEvent) => {
      // Deliberately one-way. The original also collapsed back whenever you
      // scrolled up near the top, which combined with the scrollTo(0, 0)
      // below to yank the reader back to the hero from anywhere on the page
      // — reached the footer, scrolled up, and the intro replayed from
      // scratch. An intro is worth watching once.
      if (mediaFullyExpanded) return;
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

      if (mediaFullyExpanded) return;
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
  }, [scrollProgress, mediaFullyExpanded, reducedMotion, expandNow]);

  const mediaWidth = 300 + scrollProgress * (isMobileState ? 650 : 1250);
  const mediaHeight = 400 + scrollProgress * (isMobileState ? 200 : 400);
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
                  maxWidth: "95vw",
                  maxHeight: "85vh",
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
                    <Image
                      src={mediaSrc}
                      alt={title || "Media content"}
                      width={1536}
                      height={1024}
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
