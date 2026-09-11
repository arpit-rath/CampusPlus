"use client";

/**
 * Light / dark / system theme control.
 *
 * Three states rather than two, because "follow my OS" is a real preference
 * and collapsing it into a boolean silently overrides the system setting the
 * first time someone clicks. The chosen value is written to `data-theme` on
 * <html>, which is the only thing globals.css keys off; `system` clears the
 * attribute so the `prefers-color-scheme` media query takes over again.
 *
 * The initial paint is handled by an inline script in layout.tsx, not here —
 * a React effect runs after first paint, which is exactly when a
 * light-to-dark flash would be visible.
 */

import { useEffect, useState } from "react";

type Theme = "light" | "dark" | "system";

const STORAGE_KEY = "campusplus.theme";

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === "system") {
    root.removeAttribute("data-theme");
  } else {
    root.setAttribute("data-theme", theme);
  }
  try {
    if (theme === "system") window.localStorage.removeItem(STORAGE_KEY);
    else window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    /* private browsing: the choice just will not persist */
  }
}

const OPTIONS: { value: Theme; label: string; icon: React.ReactNode }[] = [
  {
    value: "light",
    label: "Light",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <circle cx="12" cy="12" r="4" />
        <path
          strokeLinecap="round"
          d="M12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32l1.41 1.41M2 12h2m16 0h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"
        />
      </svg>
    ),
  },
  {
    value: "system",
    label: "System",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <rect x="2" y="4" width="20" height="13" rx="2" />
        <path strokeLinecap="round" d="M8 21h8m-4-4v4" />
      </svg>
    ),
  },
  {
    value: "dark",
    label: "Dark",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"
        />
      </svg>
    ),
  },
];

/**
 * `standalone` carries its own pill (the dashboard header, where it floats on
 * its own). `inline` drops the border and background so it can sit inside a
 * larger grouped bar without drawing a pill inside a pill.
 */
export function ThemeToggle({
  className = "",
  variant = "standalone",
}: {
  className?: string;
  variant?: "standalone" | "inline";
}) {
  const [theme, setTheme] = useState<Theme>("system");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored === "light" || stored === "dark") setTheme(stored);
    } catch {
      /* ignore */
    }
  }, []);

  const choose = (next: Theme) => {
    setTheme(next);
    applyTheme(next);
  };

  return (
    <div
      role="radiogroup"
      aria-label="Colour theme"
      className={`inline-flex items-center gap-0.5 rounded-full ${
        variant === "standalone"
          ? "border border-ink/15 bg-surface/70 p-0.5 backdrop-blur"
          : ""
      } ${className}`}
    >
      {OPTIONS.map((option) => {
        // Before mount every button renders unselected, so the server and
        // client markup agree and React does not warn about a mismatch.
        const active = mounted && theme === option.value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={option.label}
            title={`${option.label} theme`}
            onClick={() => choose(option.value)}
            // 36px tall inside a 44px-tall parent row keeps the tap target
            // within reach of the 44x44 minimum without a chunky control.
            className={`flex h-9 w-9 items-center justify-center rounded-full transition-colors ${
              active
                ? "bg-ink text-paper"
                : "text-ink/55 hover:bg-ink/10 hover:text-ink"
            }`}
          >
            <span className="h-4 w-4">{option.icon}</span>
          </button>
        );
      })}
    </div>
  );
}

export default ThemeToggle;
