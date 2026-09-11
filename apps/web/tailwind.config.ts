import type { Config } from "tailwindcss";

/**
 * Colours resolve through CSS variables so a theme swap is a variable swap,
 * not a class rewrite across 200-odd usages. The `<alpha-value>` placeholder
 * is what keeps Tailwind's opacity modifiers (`text-ink/70`, `bg-surface/60`)
 * working against variable-driven colours.
 *
 * `white` is deliberately left as Tailwind's real white: `text-white` labels
 * sit on saturated fills in nine places, and repointing it at a surface
 * colour would turn every one of those labels invisible in dark mode. Use
 * `surface` for panels and the `on-*` tokens for labels instead.
 */
export default {
  content: ["./src/**/*.{ts,tsx}"],
  darkMode: ["selector", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        paper: "rgb(var(--paper) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        "surface-raised": "rgb(var(--surface-raised) / <alpha-value>)",
        ink: "rgb(var(--ink) / <alpha-value>)",
        // Secondary text. A measured colour rather than `ink` at 40-50%
        // opacity: that opacity was doing the work of a colour and failing
        // at it — ink/50 on the light ground measures 3.32:1 and ink/40 on
        // the dark surface 3.41:1, both under the 4.5:1 floor. This clears
        // it in both themes with headroom (4.67:1 light, 5.92:1 dark).
        muted: "rgb(var(--ink-muted) / <alpha-value>)",

        // Decorative fills, bars and borders only — fails 4.5:1 as text on a
        // light ground, which is what `signal-ink` is for.
        signal: "rgb(var(--signal) / <alpha-value>)",
        "signal-ink": "rgb(var(--signal-ink) / <alpha-value>)",
        "signal-fill": "rgb(var(--signal-fill) / <alpha-value>)",
        "on-signal": "rgb(var(--on-signal) / <alpha-value>)",

        calm: "rgb(var(--calm) / <alpha-value>)",
        critical: "rgb(var(--critical) / <alpha-value>)",
        "on-critical": "rgb(var(--on-critical) / <alpha-value>)",
        hazard: "rgb(var(--hazard) / <alpha-value>)",
        "map-bg": "rgb(var(--map-bg) / <alpha-value>)",
      },
      borderRadius: {
        bento: "var(--card-radius)",
      },
      boxShadow: {
        card: "var(--shadow-card)",
        "card-hover": "var(--shadow-card-hover)",
      },
      fontFamily: {
        // Bound to the next/font variables set in layout.tsx. Fira Sans /
        // Fira Code is the skill's typography match for a data-dense
        // operations product.
        sans: ["var(--font-fira-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-fira-code)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
